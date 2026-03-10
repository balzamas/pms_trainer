# app.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Optional

import pandas as pd
import streamlit as st

from db import DB

APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "assets" / "reservodojo-logo.png"

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing SUPABASE_URL / SUPABASE_ANON_KEY in Streamlit secrets.")
    st.stop()

db = DB(SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY)

from scenario import (
    generate_scenario,
    should_generate_followup,
    pick_random_followup,
    render_task_text,
)
from config_model import default_config, normalize_config, validate_config
from help_ui import render_help_tab, render_login_explanation


# -------------------- auth helpers --------------------


def _set_session_from_auth(auth_res) -> None:
    def pick(obj, attr: str):
        if obj is None:
            return None
        val = getattr(obj, attr, None)
        if val is not None:
            return val
        if isinstance(obj, dict):
            return obj.get(attr)
        return None

    session = pick(auth_res, "session")
    user = pick(auth_res, "user")

    if session is None or user is None:
        data = pick(auth_res, "data")
        session = session or pick(data, "session")
        user = user or pick(data, "user")

    if session is None or user is None:
        raise RuntimeError("Could not read session/user from Supabase auth response.")

    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user_id"] = user.id
    st.session_state["user_email"] = user.email


def is_logged_in() -> bool:
    return bool(
        st.session_state.get("access_token")
        and st.session_state.get("refresh_token")
        and st.session_state.get("user_id")
    )


def get_authed_sb():
    return db.authed_client(st.session_state["access_token"], st.session_state["refresh_token"])


def require_auth_or_login() -> None:
    """
    Enforces a *valid* Supabase session (not just tokens present).
    If expired/invalid, show login UI and stop WITHOUT clearing scenario.
    """
    if not is_logged_in():
        login_ui()
        st.stop()

    try:
        sb = get_authed_sb()
        sb.auth.get_user()
    except Exception:
        st.warning("Your session expired. Please log in again.")
        login_ui()
        st.stop()


def ensure_membership_loaded() -> None:
    if st.session_state.get("accommodation_id") and st.session_state.get("role"):
        return

    sb = get_authed_sb()
    mem = db.get_my_membership(sb, st.session_state["user_id"])

    if not mem:
        st.error("This user is not linked to any accommodation yet.")
        st.info(
            "Log in with the admin user (the one who created the accommodation) "
            "and create this user from the Users tab."
        )
        st.stop()

    st.session_state["accommodation_id"] = mem["accommodation_id"]
    st.session_state["role"] = mem["role"]


def logout():
    try:
        db.sign_out(st.session_state["access_token"], st.session_state["refresh_token"])
    except Exception:
        pass

    for k in [
        "access_token",
        "refresh_token",
        "user_id",
        "user_email",
        "accommodation_id",
        "role",
        "cfg",
        "scenario",
        "generated_id",
        "scenario_cfg",
        "scenario_difficulty",
        "followup",
        "finish_booking_number",
        "is_saving_finish",
        "finish_save_message",
        "finish_save_message_type",
        "finish_followup_message",
    ]:
        st.session_state.pop(k, None)

    for k in ["guests_editor_df", "roomcats_editor_df"]:
        st.session_state.pop(k, None)

    st.rerun()


def login_ui():
    col1, col2 = st.columns([1, 4], vertical_alignment="center")

    with col1:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=150)

    with col2:
        st.markdown("## ReservoDojo")
        st.caption("Practice real reservations")

    st.divider()

    render_login_explanation()

    tab_login, tab_signup = st.tabs(["Login", "Create accommodation (admin)"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            login_submitted = st.form_submit_button("Login", type="primary")

        if login_submitted:
            try:
                res = db.sign_in(email.strip(), password)
                _set_session_from_auth(res)

                require_auth_or_login()
                ensure_membership_loaded()

                st.success("Logged in.")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab_signup:
        with st.form("signup_form", clear_on_submit=False):
            accommodation_name = st.text_input("Hostel / accommodation name", key="signup_accommodation_name")
            email2 = st.text_input("Admin email", key="signup_email")
            password2 = st.text_input("Admin password", type="password", key="signup_password")
            signup_submitted = st.form_submit_button("Create accommodation", type="primary")

        if signup_submitted:
            if not accommodation_name.strip():
                st.error("Please enter a hostel/accommodation name.")
                st.stop()
            try:
                res = db.sign_up(email2.strip(), password2)

                session = getattr(res, "session", None)
                if session is None and isinstance(res, dict):
                    session = res.get("session")
                if session is None:
                    data = getattr(res, "data", None)
                    session = getattr(data, "session", None)
                    if session is None and isinstance(data, dict):
                        session = data.get("session")

                if not session:
                    st.info("Account created. Check your email to confirm, then log in.")
                    st.stop()

                _set_session_from_auth(res)

                sb_admin = db.admin_client()

                acc_res = sb_admin.table("accommodations").insert({"name": accommodation_name.strip()}).execute()
                if acc_res is None or getattr(acc_res, "error", None):
                    raise RuntimeError(f"Could not create accommodation: {getattr(acc_res, 'error', None)}")
                accommodation_id = (acc_res.data or [{}])[0].get("id")
                if not accommodation_id:
                    raise RuntimeError("Accommodation created but no id returned.")

                user_id = st.session_state["user_id"]
                mem_res = (
                    sb_admin.table("memberships")
                    .insert({"accommodation_id": accommodation_id, "user_id": user_id, "role": "admin"})
                    .execute()
                )
                if mem_res is None or getattr(mem_res, "error", None):
                    raise RuntimeError(f"Could not create admin membership: {getattr(mem_res, 'error', None)}")

                cfg0 = default_config()
                cfg_res = (
                    sb_admin.table("configs")
                    .upsert(
                        {"accommodation_id": accommodation_id, "config_json": cfg0},
                        on_conflict="accommodation_id",
                    )
                    .execute()
                )
                if cfg_res is None or getattr(cfg_res, "error", None):
                    raise RuntimeError(f"Could not create default config: {getattr(cfg_res, 'error', None)}")

                st.session_state["accommodation_id"] = accommodation_id
                st.session_state["role"] = "admin"

                st.success("Accommodation created. You are logged in as admin.")
                st.rerun()

            except Exception as e:
                st.error(f"Sign up failed: {e}")


# -------------------- DB-backed config (per accommodation) --------------------


def load_or_init_config() -> dict:
    sb = get_authed_sb()
    accommodation_id = st.session_state["accommodation_id"]

    cfg = db.get_config(sb, accommodation_id)
    if cfg is None:
        cfg = default_config()
        if st.session_state.get("role") == "admin":
            db.upsert_config(sb, accommodation_id, cfg)

    return normalize_config(cfg)


def save_config(cfg: dict) -> None:
    sb = get_authed_sb()
    accommodation_id = st.session_state["accommodation_id"]
    db.upsert_config(sb, accommodation_id, cfg)


# -------------------- Config editor helpers --------------------


def _ensure_df(value, columns: list[str], empty_row: dict) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        df = value.copy()
    elif isinstance(value, list):
        df = pd.DataFrame(value)
    elif isinstance(value, dict):
        df = pd.DataFrame(value)
    else:
        df = pd.DataFrame([])

    if df.empty:
        df = pd.DataFrame([empty_row])

    for c in columns:
        if c not in df.columns:
            df[c] = None
    df = df.reindex(columns=columns)
    return df


def _apply_row_defaults(df: pd.DataFrame, key_col: str, defaults: dict) -> pd.DataFrame:
    out = df.copy()
    if key_col not in out.columns:
        out[key_col] = ""

    key_has_value = out[key_col].fillna("").astype(str).str.strip().ne("")

    for col, default_value in defaults.items():
        if col not in out.columns:
            out[col] = None
        out.loc[key_has_value & out[col].isna(), col] = default_value

    return out


def perfect_icon(count: int) -> str:
    if count >= 3:
        return "🏆"
    return "⭐" * count if count > 0 else ""


def progress_score(completed: str, perfect: str) -> int:
    if perfect == "🏆":
        return 5
    if perfect:
        return 4
    if completed == "✅":
        return 1
    return 0


def build_training_progress_rows(cfg: dict, rows: list[dict]) -> list[dict]:
    progress_rows = []

    # Follow-ups
    configured_followups = [s.strip() for s in cfg.get("follow_up_tasks", []) if str(s).strip()]
    for followup_label in configured_followups:
        matching_rows = [
            r for r in rows
            if (r.get("followup_text") or "").strip() == followup_label
        ]
        done_count = sum(1 for r in matching_rows if (r.get("review_status") or "").strip() == "done")
        perfect_count = sum(1 for r in matching_rows if (r.get("review_status") or "").strip() == "perfect")
        completed = done_count + perfect_count > 0

        progress_rows.append(
            {
                "Type": "Follow-up",
                "Item": followup_label,
                "Completed": "✅" if completed else "⬜",
                "Perfect": perfect_icon(perfect_count),
            }
        )

    # Room types
    configured_room_types = [
        str(r.get("name", "")).strip()
        for r in cfg.get("room_categories", [])
        if str(r.get("name", "")).strip()
    ]
    for room_type in configured_room_types:
        matching_rows = [
            r for r in rows
            if str((r.get("scenario_json") or {}).get("Room category", "")).strip() == room_type
        ]
        done_count = sum(1 for r in matching_rows if (r.get("review_status") or "").strip() == "done")
        perfect_count = sum(1 for r in matching_rows if (r.get("review_status") or "").strip() == "perfect")
        completed = done_count + perfect_count > 0

        progress_rows.append(
            {
                "Type": "Room type",
                "Item": room_type,
                "Completed": "✅" if completed else "⬜",
                "Perfect": perfect_icon(perfect_count),
            }
        )

    # Requests & extras
    configured_extras = [s.strip() for s in cfg.get("extra_services", []) if str(s).strip()]

    room_category_extras = []
    for room_cat in cfg.get("room_categories", []) or []:
        extra_text = str(room_cat.get("category_extras", "") or "").strip()
        if extra_text:
            room_category_extras.extend([x.strip() for x in extra_text.split(";") if x.strip()])

    all_configured_extras = []
    seen = set()
    for item in configured_extras + room_category_extras:
        if item not in seen:
            seen.add(item)
            all_configured_extras.append(item)

    for extra_label in all_configured_extras:
        matching_rows = []

        for r in rows:
            scenario_json = r.get("scenario_json") or {}
            extra_services_raw = str(scenario_json.get("Extra services", "") or "").strip()

            if not extra_services_raw or extra_services_raw == "(none)":
                items = []
            else:
                items = [x.strip() for x in extra_services_raw.split(",") if x.strip()]

            if extra_label in items:
                matching_rows.append(r)

        done_count = sum(1 for r in matching_rows if (r.get("review_status") or "").strip() == "done")
        perfect_count = sum(1 for r in matching_rows if (r.get("review_status") or "").strip() == "perfect")
        completed = done_count + perfect_count > 0

        progress_rows.append(
            {
                "Type": "Request / extra",
                "Item": extra_label,
                "Completed": "✅" if completed else "⬜",
                "Perfect": perfect_icon(perfect_count),
            }
        )

    return progress_rows


def config_editor(cfg: dict) -> tuple[dict, bool]:
    cfg = normalize_config(cfg)
    tabs = st.tabs(["General", "Guest profiles", "Room types", "Requests & follow-ups", "Breakfast"])

    with tabs[0]:
        bw = dict(cfg.get("booking_window", {}))
        stay = dict(cfg.get("stay_length_nights", {}))

        col1, col2 = st.columns(2)
        with col1:
            bw["earliest_arrival"] = st.text_input("Earliest arrival (YYYY-MM-DD)", bw.get("earliest_arrival", ""))
            stay["min"] = st.number_input("Stay min nights", min_value=1, step=1, value=int(stay.get("min", 1)))
            cfg["max_services"] = st.number_input(
                "Max requests & extras",
                min_value=0,
                step=1,
                value=int(cfg.get("max_services", 3)),
                help="Applies to the combined pool of global extras + room-category extras.",
            )
        with col2:
            bw["latest_arrival"] = st.text_input("Latest arrival (YYYY-MM-DD)", bw.get("latest_arrival", ""))
            stay["max"] = st.number_input("Stay max nights", min_value=1, step=1, value=int(stay.get("max", 5)))
            pct = int(round(float(cfg.get("follow_up_probability", 0.33)) * 100))
            pct = st.slider("Follow-up chance (%)", 0, 100, pct)
            cfg["follow_up_probability"] = pct / 100.0

        cfg["booking_window"] = bw
        cfg["stay_length_nights"] = stay

    with tabs[1]:
        st.caption("Add/edit guests. Changes are included when you click **Save config**.")

        GUESTS_KEY = "guests_editor_df"

        if GUESTS_KEY not in st.session_state:
            base = cfg.get("guests", [])
            st.session_state[GUESTS_KEY] = _ensure_df(
                base,
                columns=["full_name", "comment", "min_guests", "max_guests"],
                empty_row={"full_name": "", "comment": "", "min_guests": 1, "max_guests": 99},
            )

        edited = st.data_editor(
            st.session_state[GUESTS_KEY],
            key="guests_editor_widget",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "full_name": st.column_config.TextColumn("Full name", required=False),
                "comment": st.column_config.TextColumn("Comment"),
                "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
            },
        )

        edited = _apply_row_defaults(edited, "full_name", {"min_guests": 1, "max_guests": 99})
        edited["full_name"] = edited["full_name"].fillna("").astype(str).str.strip()

        if "comment" not in edited.columns:
            edited["comment"] = ""
        edited["comment"] = edited["comment"].fillna("").astype(str)

        edited["min_guests"] = pd.to_numeric(edited["min_guests"], errors="coerce").fillna(1).astype(int)
        edited["max_guests"] = pd.to_numeric(edited["max_guests"], errors="coerce").fillna(99).astype(int)

        edited = edited[edited["full_name"] != ""].reset_index(drop=True)

        st.session_state[GUESTS_KEY] = edited
        cfg["guests"] = edited.to_dict(orient="records")

    with tabs[2]:
        st.caption("Add/edit room types. Changes are included when you click **Save config**.")
        st.caption("Type extras will be mixed into the same 'Requests & extras' list during scenario generation.")

        ROOMCATS_KEY = "roomcats_editor_df"

        if ROOMCATS_KEY not in st.session_state:
            base = cfg.get("room_categories", [])
            st.session_state[ROOMCATS_KEY] = _ensure_df(
                base,
                columns=["name", "min_guests", "max_guests", "category_extras"],
                empty_row={"name": "", "min_guests": 1, "max_guests": 99, "category_extras": ""},
            )

        edited = st.data_editor(
            st.session_state[ROOMCATS_KEY],
            key="roomcats_editor_widget",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Type name", required=False),
                "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
                "category_extras": st.column_config.TextColumn(
                    "Category extras (use ';')",
                    help="Optional. Example: Baby bed; Extra bed; 2x Children",
                ),
            },
        )

        edited = _apply_row_defaults(edited, "name", {"min_guests": 1, "max_guests": 99})
        edited["name"] = edited["name"].fillna("").astype(str).str.strip()
        edited["min_guests"] = pd.to_numeric(edited["min_guests"], errors="coerce").fillna(1).astype(int)
        edited["max_guests"] = pd.to_numeric(edited["max_guests"], errors="coerce").fillna(99).astype(int)

        if "category_extras" not in edited.columns:
            edited["category_extras"] = ""
        edited["category_extras"] = edited["category_extras"].fillna("").astype(str)

        edited = edited[edited["name"] != ""].reset_index(drop=True)

        st.session_state[ROOMCATS_KEY] = edited
        cfg["room_categories"] = edited.to_dict(orient="records")

    with tabs[3]:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Requests & extras (global)")
            services_txt = st.text_area("One per line", "\n".join(cfg.get("extra_services", [])), height=240)
            cfg["extra_services"] = [s.strip() for s in services_txt.splitlines() if s.strip()]
        with col2:
            st.subheader("Follow-up tasks")
            followups_txt = st.text_area("One per line", "\n".join(cfg.get("follow_up_tasks", [])), height=240)
            cfg["follow_up_tasks"] = [s.strip() for s in followups_txt.splitlines() if s.strip()]

    with tabs[4]:
        pol = dict(cfg.get("breakfast_policy", {}))
        pol["enabled"] = st.checkbox("Enable breakfast", bool(pol.get("enabled", False)))
        pol["probability_any_breakfast"] = st.slider(
            "Probability any breakfast",
            0.0,
            1.0,
            float(pol.get("probability_any_breakfast", 0.7)),
        )
        pol["probability_full_group_if_any"] = st.slider(
            "Probability full group if any",
            0.0,
            1.0,
            float(pol.get("probability_full_group_if_any", 0.7)),
        )

        types_txt = st.text_area("Breakfast types (one per line)", "\n".join(cfg.get("breakfast_types", [])), height=160)
        cfg["breakfast_types"] = [t.strip() for t in types_txt.splitlines() if t.strip()]
        cfg["breakfast_policy"] = pol

    st.divider()
    errors = validate_config(cfg)
    if errors:
        st.error("Config has issues:\n\n- " + "\n- ".join(errors))
    else:
        st.success("Config looks valid.")

    save_clicked = st.button("Save config", type="primary", disabled=bool(errors))
    return cfg, save_clicked


def apply_difficulty_to_cfg(cfg: dict, difficulty: str) -> dict:
    effective = dict(cfg)
    difficulty = (difficulty or "hard").strip().lower()

    if difficulty in ("medium", "easy"):
        effective["max_services"] = 0
        effective["extra_services"] = []
        effective["breakfast_policy"] = dict(effective.get("breakfast_policy", {}))
        effective["breakfast_policy"]["enabled"] = False
        effective["breakfast_types"] = []

        roomcats = []
        for c in effective.get("room_categories", []) or []:
            c2 = dict(c)
            c2["category_extras"] = ""
            roomcats.append(c2)
        effective["room_categories"] = roomcats

    if difficulty == "easy":
        effective["follow_up_probability"] = 0.0
        effective["follow_up_tasks"] = []

    return effective


# -------------------- main UI --------------------

st.set_page_config(page_title="ReservoDojo", layout="wide")

if "is_saving_finish" not in st.session_state:
    st.session_state["is_saving_finish"] = False

if "finish_save_message" not in st.session_state:
    st.session_state["finish_save_message"] = None

if "finish_save_message_type" not in st.session_state:
    st.session_state["finish_save_message_type"] = None

if "finish_followup_message" not in st.session_state:
    st.session_state["finish_followup_message"] = None

require_auth_or_login()
ensure_membership_loaded()

with st.sidebar:
    st.write(f"**Logged in:** {st.session_state.get('user_email', '')}")
    st.write(f"**Role:** {st.session_state.get('role', '')}")
    if st.button("Logout"):
        logout()

role = st.session_state.get("role", "user")
accommodation_id = st.session_state["accommodation_id"]

if "cfg" not in st.session_state:
    st.session_state["cfg"] = load_or_init_config()

cfg = st.session_state["cfg"]

col_logo, col_title = st.columns([1, 4], vertical_alignment="center")
with col_logo:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=150)
with col_title:
    st.markdown("## ReservoDojo")
    st.caption("Practice real reservations")

menu_options = ["Scenario", "Review", "Help", "Progress"]
if role == "admin":
    menu_options.insert(2, "Config")
    menu_options.insert(3, "Users")

page = st.radio("Menu", menu_options, horizontal=True)

# -------------------- USERS (admin only) --------------------
if page == "Users":
    if role != "admin":
        st.error("Admins only.")
        st.stop()

    st.subheader("User administration")
    if st.session_state.get("clear_new_user_form"):
        st.session_state["new_user_name"] = ""
        st.session_state["new_user_email"] = ""
        st.session_state["new_user_password"] = ""
        st.session_state["new_user_role"] = "user"
        st.session_state.pop("clear_new_user_form", None)

    with st.form("create_user_form"):
        new_name = st.text_input("Name", key="new_user_name")
        new_email = st.text_input("Email", key="new_user_email")
        new_password = st.text_input("Password", type="password", key="new_user_password")
        new_role = st.radio("Role", options=["user", "admin"], index=0, horizontal=True, key="new_user_role")
        submitted = st.form_submit_button("Create user", type="primary")

    if submitted:
        if not new_email.strip():
            st.error("Please enter an email.")
            st.stop()
        if not new_password.strip():
            st.error("Please enter a password.")
            st.stop()

        try:
            new_user_id = db.admin_create_user(new_email.strip(), new_password)

            sb = get_authed_sb()
            db.add_membership(sb, accommodation_id, new_user_id, new_role)

            sb_admin = db.admin_client()
            db.upsert_profile(sb_admin, new_user_id, new_name.strip() or new_email.strip(), new_email.strip())

            st.success(f"Created user {new_email.strip()} with role '{new_role}'.")
            st.session_state["clear_new_user_form"] = True
            st.rerun()

        except Exception as e:
            st.error(f"Could not create user: {e}")

    st.divider()
    st.subheader("Members")

    try:
        sb = get_authed_sb()
        members = db.list_members(sb, accommodation_id)

        if not members:
            st.info("No members yet.")
        else:
            profiles = db.get_profiles_for_accommodation(sb, accommodation_id)

            rows = []
            for m in members:
                uid = str(m.get("user_id") or "")
                prof = profiles.get(uid, {})

                rows.append(
                    {
                        "Name": prof.get("display_name") or "Unknown",
                        "Email": prof.get("email") or "",
                        "Role": m.get("role") or "",
                        "Added": str(m.get("created_at") or "")[:10],
                    }
                )

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Could not load members: {e}")

# -------------------- CONFIG (admin only) --------------------
elif page == "Config":
    if role != "admin":
        st.error("Admins only.")
        st.stop()

    updated_cfg, save_clicked = config_editor(cfg)
    st.session_state["cfg"] = updated_cfg

    if save_clicked:
        try:
            require_auth_or_login()
            save_config(updated_cfg)

            st.session_state.pop("guests_editor_df", None)
            st.session_state.pop("roomcats_editor_df", None)

            st.success("Saved config to database.")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")

# -------------------- SCENARIO --------------------
elif page == "Scenario":
    col1, col2 = st.columns([2, 1], gap="large")

    with col1:
        b1, b2 = st.columns([2, 3], vertical_alignment="bottom")

        with b1:
            new_clicked = st.button("New scenario", type="primary")

        with b2:
            difficulty = st.radio(
                "Difficulty",
                options=["hard", "medium", "easy"],
                index=0,
                horizontal=True,
                key="difficulty_level",
            )

        if new_clicked:
            effective_cfg = apply_difficulty_to_cfg(cfg, difficulty)
            st.session_state["scenario_cfg"] = effective_cfg
            st.session_state["scenario_difficulty"] = difficulty

            st.session_state["scenario"] = generate_scenario(effective_cfg)
            st.session_state["generated_id"] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            st.session_state["followup"] = None

            st.session_state["finish_save_message"] = None
            st.session_state["finish_save_message_type"] = None
            st.session_state["finish_followup_message"] = None

        scenario = st.session_state.get("scenario")
        if scenario:
            st.subheader("Scenario details")

            guest_comment = scenario.get("Guest comment", "").strip()
            extra_services = scenario.get("Extra services", "(none)")

            with st.container(border=True):
                st.markdown(f"**Guest name**  \n{scenario.get('Guest name', '')}")
                if guest_comment:
                    st.markdown(f"**Note**  \n{guest_comment}")

                st.divider()

                st.markdown(
                    dedent(
                        f"""
                    <div style="display:grid; grid-template-columns: 180px 1fr; row-gap:4px; column-gap:10px; line-height:1.25;">
                      <div style="padding:4px;"><strong>Room type</strong></div>
                      <div style="padding:4px;">{scenario.get("Room category","")}</div>

                      <div style="background:rgba(0,0,0,0.03); padding:4px;"><strong>Guests</strong></div>
                      <div style="background:rgba(0,0,0,0.03); padding:4px;">{scenario.get("Number of guests","")}</div>

                      <div style="padding:4px;"><strong>Nights</strong></div>
                      <div style="padding:4px;">{scenario.get("Nights","")}</div>

                      <div style="background:rgba(0,0,0,0.03); padding:4px;"><strong>Arrival</strong></div>
                      <div style="background:rgba(0,0,0,0.03); padding:4px;">{scenario.get("Arrival","")}</div>

                      <div style="padding:4px;"><strong>Departure</strong></div>
                      <div style="padding:4px;">{scenario.get("Departure","")}</div>
                    </div>
                    """
                    ).strip(),
                    unsafe_allow_html=True,
                )

                st.divider()

                items = [x.strip() for x in str(extra_services).split(",") if x.strip()] if extra_services else []
                if not items or extra_services == "(none)":
                    items = ["None"]

                st.markdown("**Requests & extras**")
                st.markdown("\n".join([f"- {s}" for s in items]))
        else:
            st.info("Click **New scenario** to generate a scenario.")

    with col2:
        st.subheader("Finish")

        finish_status = st.empty()
        followup_box = st.empty()

        current_msg = st.session_state.get("finish_save_message")
        current_msg_type = st.session_state.get("finish_save_message_type")
        current_followup = st.session_state.get("finish_followup_message")

        if st.session_state.get("is_saving_finish"):
            finish_status.info("Saving scenario to database...")
        elif current_msg:
            if current_msg_type == "success":
                finish_status.success(current_msg)
            elif current_msg_type == "error":
                finish_status.error(current_msg)
            else:
                finish_status.info(current_msg)

        if current_followup:
            followup_box.warning(f"Follow-up: {current_followup}")

        with st.form("finish_task", clear_on_submit=True):
            booking_number = st.text_input("Booking number", key="finish_booking_number")

            submitted = st.form_submit_button(
                "Mark finished",
                disabled=(
                    not st.session_state.get("scenario")
                    or st.session_state.get("is_saving_finish", False)
                ),
            )

        if submitted:
            booking_number_clean = booking_number.strip()

            if not booking_number_clean:
                st.session_state["finish_save_message"] = "Please enter a booking number."
                st.session_state["finish_save_message_type"] = "error"
                finish_status.error("Please enter a booking number.")
                st.stop()

            st.session_state["is_saving_finish"] = True
            st.session_state["finish_save_message"] = "Saving scenario to database..."
            st.session_state["finish_save_message_type"] = "info"
            st.session_state["finish_followup_message"] = None
            finish_status.info("Saving scenario to database...")
            followup_box.empty()

            require_auth_or_login()
            ensure_membership_loaded()

            effective_cfg = st.session_state.get("scenario_cfg") or cfg

            followup: Optional[str] = None
            if should_generate_followup(effective_cfg):
                followup = pick_random_followup(effective_cfg)

            try:
                sb = get_authed_sb()
                db.insert_task(
                    sb=sb,
                    accommodation_id=accommodation_id,
                    created_by=st.session_state["user_id"],
                    generated_id=st.session_state["generated_id"],
                    booking_number=booking_number_clean,
                    scenario_json=st.session_state["scenario"],
                    followup_text=followup,
                )

                st.session_state["is_saving_finish"] = False
                st.session_state["finish_save_message"] = (
                    f"Saved scenario (Nr.: {booking_number_clean}) result to database."
                )
                st.session_state["finish_save_message_type"] = "success"
                st.session_state["finish_followup_message"] = followup

                finish_status.success(st.session_state["finish_save_message"])
                if followup:
                    followup_box.warning(f"Follow-up: {followup}")

            except Exception as e:
                st.session_state["is_saving_finish"] = False
                st.session_state["finish_save_message"] = f"Saving scenario failed: {e}"
                st.session_state["finish_save_message_type"] = "error"
                st.session_state["finish_followup_message"] = None
                finish_status.error(st.session_state["finish_save_message"])
                followup_box.empty()
                st.stop()

            txt = render_task_text(
                st.session_state["scenario"],
                booking_number_clean,
                st.session_state["generated_id"],
                followup,
            )

            st.download_button(
                "Download scenario (TXT)",
                data=txt,
                file_name=f"PMS_Scenario_{st.session_state['generated_id']}_BN-{booking_number_clean}.txt",
            )

# -------------------- REVIEW --------------------
elif page == "Review":
    st.subheader("Review (latest 50)")

    try:
        require_auth_or_login()
        ensure_membership_loaded()
        sb = get_authed_sb()
        rows = db.list_tasks(sb, accommodation_id, limit=50)
    except Exception as e:
        st.error(f"Could not load scenarios for review: {e}")
        st.stop()

    if not rows:
        st.info("No scenario saved yet.")
        st.stop()

    hide_done_perfect = st.checkbox("Hide scenarios marked 'done' or 'perfect'", value=True)

    def _date_only(ts: str) -> str:
        try:
            return str(pd.to_datetime(ts).date())
        except Exception:
            return str(ts)[:10]

    needed_user_ids = sorted({str(r.get("created_by") or "") for r in rows if r.get("created_by")})
    profiles = db.get_profiles_by_ids(sb, needed_user_ids)

    table_rows = []
    row_map = []

    for i, r in enumerate(rows):
        status = (r.get("review_status") or "new").strip()
        if hide_done_perfect and status in ("done", "perfect"):
            continue

        sc = r.get("scenario_json", {}) or {}

        created_by = str(r.get("created_by") or "")
        created_name = profiles.get(created_by, {}).get("display_name", "Unknown")

        table_rows.append(
            {
                "Finished": _date_only(r.get("finished_at", "")),
                "Status": status.replace("_", " "),
                "Booking number": r.get("booking_number", ""),
                "Guest name": sc.get("Guest name", ""),
                "Room type": sc.get("Room category", ""),
                "Created by": created_name,
                "Follow-up": r.get("followup_text") or "",
            }
        )
        row_map.append(i)

    if not table_rows:
        st.info("Nothing to show with current filter.")
        st.stop()

    df = pd.DataFrame(table_rows)
    st.caption("Click a row to view details and set trainer review below.")

    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tasks_table",
    )

    selected_display_idx = None
    try:
        selected_rows = event.selection.rows
        if selected_rows:
            selected_display_idx = int(selected_rows[0])
    except Exception:
        selected_display_idx = None

    st.divider()
    st.subheader("Details")

    if selected_display_idx is None:
        st.info("Select a row above to see details.")
        st.stop()

    r = rows[row_map[selected_display_idx]]
    scenario = r.get("scenario_json", {}) or {}
    followup = r.get("followup_text") or ""
    finished = _date_only(r.get("finished_at", ""))

    task_id = r.get("id")
    current_status = (r.get("review_status") or "new").strip()

    status_options = ["new", "needs_review", "done", "perfect"]
    new_status = st.radio(
        "Trainer review",
        options=status_options,
        index=status_options.index(current_status) if current_status in status_options else 0,
        horizontal=True,
        key=f"review_status_{task_id}",
    )

    if new_status != current_status:
        try:
            require_auth_or_login()
            sb2 = get_authed_sb()
            db.update_task_review_status(sb2, task_id, new_status)
            st.success("Saved trainer review.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save review status: {e}")

    guest_comment = (scenario.get("Guest comment", "") or "").strip()
    extra_services = scenario.get("Extra services", "(none)")

    with st.container(border=True):
        st.markdown(f"**Finished**  \n{finished}")
        st.markdown(f"**Booking number**  \n{r.get('booking_number','')}")
        st.markdown(f"**Status**  \n{new_status.replace('_', ' ')}")
        st.divider()

        st.markdown(f"**Guest name**  \n{scenario.get('Guest name','')}")
        if guest_comment:
            st.markdown(f"**Note**  \n{guest_comment}")

        st.divider()

        def row_line(label, value):
            c1, c2 = st.columns([1, 3])
            c1.markdown(f"**{label}**")
            c2.markdown(str(value) if value is not None else "")

        row_line("Room type", scenario.get("Room category", ""))
        row_line("Number of guests", scenario.get("Number of guests", ""))
        row_line("Nights", scenario.get("Nights", ""))
        row_line("Arrival", scenario.get("Arrival", ""))
        row_line("Departure", scenario.get("Departure", ""))

        st.divider()

        st.markdown("**Requests & extras**")
        if extra_services and extra_services != "(none)":
            for s in [x.strip() for x in str(extra_services).split(",") if x.strip()]:
                st.markdown(f"- {s}")
        else:
            st.markdown("- None")

        if followup:
            st.divider()
            st.markdown("**Follow-up**")
            st.markdown(f"- {followup}")

    txt = render_task_text(
        scenario,
        r.get("booking_number", ""),
        r.get("generated_id", ""),
        followup if followup else None,
    )
    st.download_button(
        "Download TXT",
        data=txt,
        file_name=f"PMS_Scenario_{r.get('generated_id','task')}_BN-{r.get('booking_number','')}.txt",
        key=f"dl_{task_id}",
    )

# -------------------- PROGRESS --------------------
elif page == "Progress":
    st.subheader("Training progress")

    try:
        require_auth_or_login()
        ensure_membership_loaded()
        sb = get_authed_sb()
        rows = db.list_tasks(sb, accommodation_id, limit=500)
    except Exception as e:
        st.error(f"Could not load progress: {e}")
        st.stop()

    progress_rows = build_training_progress_rows(cfg, rows)

    if not progress_rows:
        st.info("No training items configured yet.")
        st.stop()

    progress_df = pd.DataFrame(progress_rows).sort_values(["Type", "Item"]).reset_index(drop=True)

    current_score = sum(
        progress_score(row["Completed"], row["Perfect"])
        for _, row in progress_df.iterrows()
    )
    max_score = len(progress_df) * 5
    score_ratio = current_score / max_score if max_score else 0.0

    st.metric("Global score", f"{current_score} / {max_score}")
    st.progress(score_ratio)

    row_height = 35
    header_height = 38
    max_height = 2000

    table_height = min(header_height + len(progress_df) * row_height, max_height)

    st.dataframe(
        progress_df,
        use_container_width=True,
        hide_index=True,
        height=table_height,
    )

# -------------------- HELP --------------------
elif page == "Help":
    render_help_tab()
