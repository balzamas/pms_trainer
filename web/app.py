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
        st.info("Log in with the admin user (the one who created the accommodation) and create this user from the Users tab.")
        st.stop()

    st.session_state["accommodation_id"] = mem["accommodation_id"]
    st.session_state["role"] = mem["role"]


def logout():
    try:
        db.sign_out(st.session_state["access_token"], st.session_state["refresh_token"])
    except Exception:
        pass

    # NOTE: We intentionally keep scenario-related keys if you want to preserve local state,
    # but on explicit logout we clear everything.
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
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", type="primary"):
            try:
                res = db.sign_in(email.strip(), password)
                _set_session_from_auth(res)

                # load membership
                require_auth_or_login()
                ensure_membership_loaded()

                st.success("Logged in.")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab_signup:
        accommodation_name = st.text_input("Hostel / accommodation name", key="signup_accommodation_name")
        email2 = st.text_input("Admin email", key="signup_email")
        password2 = st.text_input("Admin password", type="password", key="signup_password")

        if st.button("Create accommodation", type="primary"):
            if not accommodation_name.strip():
                st.error("Please enter a hostel/accommodation name.")
                st.stop()
            try:
                # 1) create auth user
                res = db.sign_up(email2.strip(), password2)
                # If your project requires email confirmation, session might be missing here.
                # We'll handle both cases:
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

                # 2) set session_state from auth
                _set_session_from_auth(res)

                # 3) bootstrap with service role
                sb_admin = db.admin_client()

                # Create accommodation as service role
                acc_res = sb_admin.table("accommodations").insert({"name": accommodation_name.strip()}).execute()
                if acc_res is None or getattr(acc_res, "error", None):
                    raise RuntimeError(f"Could not create accommodation: {getattr(acc_res, 'error', None)}")
                accommodation_id = (acc_res.data or [{}])[0].get("id")
                if not accommodation_id:
                    raise RuntimeError("Accommodation created but no id returned.")

                # Create membership as service role
                user_id = st.session_state["user_id"]
                mem_res = (
                    sb_admin.table("memberships")
                    .insert({"accommodation_id": accommodation_id, "user_id": user_id, "role": "admin"})
                    .execute()
                )
                if mem_res is None or getattr(mem_res, "error", None):
                    raise RuntimeError(f"Could not create admin membership: {getattr(mem_res, 'error', None)}")

                # ------------------ NEW: create default config as service role ------------------
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
                # -------------------------------------------------------------------------------

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
        # only admins can write config under our RLS
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


def config_editor(cfg: dict) -> tuple[dict, bool]:
    cfg = normalize_config(cfg)
    tabs = st.tabs(["General", "Guest profiles", "Room types", "Requests & follow-ups", "Breakfast"])

    # --- General ---
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

    # --- Guests ---
    with tabs[1]:
        st.caption("Add/edit guests. Click **Apply changes** when done editing.")

        GUESTS_KEY = "guests_editor_df"

        if GUESTS_KEY not in st.session_state:
            base = cfg.get("guests", [])
            st.session_state[GUESTS_KEY] = _ensure_df(
                base,
                columns=["full_name", "comment", "min_guests", "max_guests"],
                empty_row={"full_name": "", "comment": "", "min_guests": 1, "max_guests": 99},
            )

        with st.form("guests_form"):
            edited = st.data_editor(
                st.session_state[GUESTS_KEY],
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "full_name": st.column_config.TextColumn("Full name", required=True),
                    "comment": st.column_config.TextColumn("Comment"),
                    "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                    "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
                },
            )
            apply_guests = st.form_submit_button("Apply changes")

        if apply_guests:
            edited = _apply_row_defaults(edited, "full_name", {"min_guests": 1, "max_guests": 99})
            edited["full_name"] = edited["full_name"].fillna("").astype(str)
            if "comment" not in edited.columns:
                edited["comment"] = ""
            edited["comment"] = edited["comment"].fillna("").astype(str)

            edited["min_guests"] = pd.to_numeric(edited["min_guests"], errors="coerce").fillna(1).astype(int)
            edited["max_guests"] = pd.to_numeric(edited["max_guests"], errors="coerce").fillna(99).astype(int)

            st.session_state[GUESTS_KEY] = edited
            cfg["guests"] = edited.to_dict(orient="records")
            st.success("Guests updated in this config (remember to click **Save config**).")
        else:
            guests_cfg = st.session_state[GUESTS_KEY].copy()
            guests_cfg = _apply_row_defaults(guests_cfg, "full_name", {"min_guests": 1, "max_guests": 99})
            guests_cfg["full_name"] = guests_cfg["full_name"].fillna("").astype(str)
            if "comment" not in guests_cfg.columns:
                guests_cfg["comment"] = ""
            guests_cfg["comment"] = guests_cfg["comment"].fillna("").astype(str)
            guests_cfg["min_guests"] = pd.to_numeric(guests_cfg["min_guests"], errors="coerce").fillna(1).astype(int)
            guests_cfg["max_guests"] = pd.to_numeric(guests_cfg["max_guests"], errors="coerce").fillna(99).astype(int)
            cfg["guests"] = guests_cfg.to_dict(orient="records")

    # --- Room categories ---
    with tabs[2]:
        st.caption("Add/edit room types. Click **Apply changes** when done editing.")
        st.caption("Type extras will be mixed into the same 'Requests & extras' list during scenario generation.")

        ROOMCATS_KEY = "roomcats_editor_df"

        if ROOMCATS_KEY not in st.session_state:
            base = cfg.get("room_categories", [])
            st.session_state[ROOMCATS_KEY] = _ensure_df(
                base,
                columns=["name", "min_guests", "max_guests", "category_extras"],
                empty_row={"name": "", "min_guests": 1, "max_guests": 99, "category_extras": ""},
            )

        with st.form("roomcats_form"):
            edited = st.data_editor(
                st.session_state[ROOMCATS_KEY],
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "name": st.column_config.TextColumn("Type name", required=True),
                    "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                    "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
                    "category_extras": st.column_config.TextColumn(
                        "Category extras (use ';')",
                        help="Optional. Example: Baby bed; Extra bed; 2x Children",
                    ),
                },
            )
            apply_roomcats = st.form_submit_button("Apply changes")

        if apply_roomcats:
            edited = _apply_row_defaults(edited, "name", {"min_guests": 1, "max_guests": 99})
            edited["name"] = edited["name"].fillna("").astype(str)
            edited["min_guests"] = pd.to_numeric(edited["min_guests"], errors="coerce").fillna(1).astype(int)
            edited["max_guests"] = pd.to_numeric(edited["max_guests"], errors="coerce").fillna(99).astype(int)
            if "category_extras" not in edited.columns:
                edited["category_extras"] = ""
            edited["category_extras"] = edited["category_extras"].fillna("").astype(str)

            st.session_state[ROOMCATS_KEY] = edited
            cfg["room_categories"] = edited.to_dict(orient="records")
            st.success("Room categories updated in this config (remember to click **Save config**).")
        else:
            cats_cfg = st.session_state[ROOMCATS_KEY].copy()
            cats_cfg = _apply_row_defaults(cats_cfg, "name", {"min_guests": 1, "max_guests": 99})
            cats_cfg["name"] = cats_cfg["name"].fillna("").astype(str)
            cats_cfg["min_guests"] = pd.to_numeric(cats_cfg["min_guests"], errors="coerce").fillna(1).astype(int)
            cats_cfg["max_guests"] = pd.to_numeric(cats_cfg["max_guests"], errors="coerce").fillna(99).astype(int)
            if "category_extras" not in cats_cfg.columns:
                cats_cfg["category_extras"] = ""
            cats_cfg["category_extras"] = cats_cfg["category_extras"].fillna("").astype(str)

            cfg["room_categories"] = cats_cfg.to_dict(orient="records")

    # --- Services & follow-ups ---
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

    # --- Breakfast ---
    with tabs[4]:
        pol = dict(cfg.get("breakfast_policy", {}))
        pol["enabled"] = st.checkbox("Enable breakfast", bool(pol.get("enabled", False)))
        pol["probability_any_breakfast"] = st.slider("Probability any breakfast", 0.0, 1.0, float(pol.get("probability_any_breakfast", 0.7)))
        pol["probability_full_group_if_any"] = st.slider("Probability full group if any", 0.0, 1.0, float(pol.get("probability_full_group_if_any", 0.7)))

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

require_auth_or_login()
ensure_membership_loaded()

with st.sidebar:
    st.write(f"**Logged in:** {st.session_state.get('user_email', '')}")
    st.write(f"**Role:** {st.session_state.get('role', '')}")
    if st.button("Logout"):
        logout()

role = st.session_state.get("role", "user")
accommodation_id = st.session_state["accommodation_id"]

# Config is per accommodation
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

menu_options = ["Scenario", "Review", "Help"]
if role == "admin":
    menu_options.insert(1, "Config")
    menu_options.insert(2, "Users")

page = st.radio("Menu", menu_options, horizontal=True)

# -------------------- USERS (admin only) --------------------
if page == "Users":
    if role != "admin":
        st.error("Admins only.")
        st.stop()

    st.subheader("User administration")

    with st.form("create_user_form"):
        new_email = st.text_input("Email")
        new_password = st.text_input("Password", type="password")
        new_role = st.radio("Role", options=["user", "admin"], index=0, horizontal=True)
        submitted = st.form_submit_button("Create user", type="primary")

    if submitted:
        if not new_email.strip():
            st.error("Please enter an email.")
            st.stop()
        if not new_password.strip():
            st.error("Please enter a password.")
            st.stop()

        try:
            # 1) create auth user (service role)
            new_user_id = db.admin_create_user(new_email.strip(), new_password)

            # 2) create membership (as the logged-in admin, via RLS)
            sb = get_authed_sb()
            db.add_membership(sb, accommodation_id, new_user_id, new_role)

            st.success(f"Created user {new_email.strip()} with role '{new_role}'.")
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
            df = pd.DataFrame(members)
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

        scenario = st.session_state.get("scenario")
        if scenario:
            st.subheader("Scenario details")

            guest_comment = scenario.get("Guest comment", "").strip()
            extra_services = scenario.get("Extra services", "(none)")

            with st.container(border=True):
                st.markdown(f"**Guest name**  \n{scenario.get('Guest name', '')}")
                if guest_comment:
                    st.caption(guest_comment)

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

        with st.form("finish_task"):
            booking_number = st.text_input("Booking number")

            submitted = st.form_submit_button(
                "Mark finished",
                disabled=not st.session_state.get("scenario"),
            )

        if submitted:
            if not booking_number.strip():
                st.error("Please enter a booking number.")
                st.stop()

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
                    booking_number=booking_number.strip(),
                    scenario_json=st.session_state["scenario"],
                    followup_text=followup,
                )
                st.success("Saved scenario result to database.")
            except Exception as e:
                st.error(f"Saving scenario failed: {e}")
                st.stop()

            txt = render_task_text(
                st.session_state["scenario"],
                booking_number.strip(),
                st.session_state["generated_id"],
                followup,
            )

            st.download_button(
                "Download scenario (TXT)",
                data=txt,
                file_name=f"PMS_Scenario_{st.session_state['generated_id']}_BN-{booking_number.strip()}.txt",
            )

            if followup:
                st.warning(f"Follow-up: {followup}")

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

    hide_okay = st.checkbox("Hide scenarios marked 'okay'", value=True)

    def _date_only(ts: str) -> str:
        try:
            return str(pd.to_datetime(ts).date())
        except Exception:
            return str(ts)[:10]

    table_rows = []
    row_map = []

    for i, r in enumerate(rows):
        status = (r.get("review_status") or "new").strip()
        if hide_okay and status == "okay":
            continue

        sc = r.get("scenario_json", {}) or {}
        table_rows.append(
            {
                "Finished": _date_only(r.get("finished_at", "")),
                "Status": status.replace("_", " "),
                "Booking number": r.get("booking_number", ""),
                "Guest name": sc.get("Guest name", ""),
                "Room type": sc.get("Room category", ""),
                "Created by": (r.get("created_by") or "")[:8],
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

    status_options = ["new", "okay", "needs_review"]
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
            st.caption(guest_comment)

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

# -------------------- HELP --------------------
elif page == "Help":
    render_help_tab()
