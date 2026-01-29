from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from db import DB

# You must provide these in Streamlit secrets or environment.
# Streamlit Cloud: add in App settings -> Secrets:
# SUPABASE_URL="..."
# SUPABASE_ANON_KEY="..."
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing SUPABASE_URL / SUPABASE_ANON_KEY in Streamlit secrets.")
    st.stop()

db = DB(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---- You should refactor your existing logic into scenario.py ----
# Required functions from scenario.py:
#   - generate_scenario(cfg: dict) -> dict
#   - should_generate_followup(cfg: dict) -> bool
#   - pick_random_followup(cfg: dict) -> Optional[str]
#   - render_task_text(scenario: dict, booking_number: str, generated_id: str, followup: Optional[str]) -> str
from scenario import (
    generate_scenario,
    should_generate_followup,
    pick_random_followup,
    render_task_text,
)

# ---- Config defaults/validation ----
# You can use the config_model.py from my previous message.
from config_model import default_config, normalize_config, validate_config


# -------------------- auth helpers --------------------

def _set_session_from_auth(auth_res) -> None:
    """
    Stores tokens/user in session_state.
    Works with supabase-py v2 where auth responses are objects (AuthResponse),
    and also tolerates dict-like shapes.
    """
    def pick(obj, attr: str):
        if obj is None:
            return None
        # object attribute
        val = getattr(obj, attr, None)
        if val is not None:
            return val
        # dict fallback
        if isinstance(obj, dict):
            return obj.get(attr)
        return None

    session = pick(auth_res, "session")
    user = pick(auth_res, "user")

    # Some versions wrap in `.data`
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
    return bool(st.session_state.get("access_token") and st.session_state.get("refresh_token") and st.session_state.get("user_id"))


def logout():
    try:
        db.sign_out(st.session_state["access_token"], st.session_state["refresh_token"])
    except Exception:
        pass
    for k in ["access_token", "refresh_token", "user_id", "user_email", "cfg", "scenario", "generated_id"]:
        st.session_state.pop(k, None)
    st.rerun()


def login_ui():
    st.title("PMS Trainer — Login")

    tab_login, tab_signup = st.tabs(["Login", "Create account"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", type="primary"):
            try:
                res = db.sign_in(email.strip(), password)
                _set_session_from_auth(res)
                st.success("Logged in.")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab_signup:
        email2 = st.text_input("Email", key="signup_email")
        password2 = st.text_input("Password", type="password", key="signup_password")
        if st.button("Create account", type="primary"):
            try:
                res = db.sign_up(email2.strip(), password2)
                # Depending on Supabase settings, email confirmation may be required.
                # If confirmation is required, the session may be None.
                session = getattr(res, "session", None) or res.get("session")
                if session:
                    _set_session_from_auth(res)
                    st.success("Account created and logged in.")
                    st.rerun()
                else:
                    st.info("Account created. Check your email to confirm, then log in.")
            except Exception as e:
                st.error(f"Sign up failed: {e}")


# -------------------- DB-backed config --------------------

def get_authed_sb():
    return db.authed_client(st.session_state["access_token"], st.session_state["refresh_token"])


def load_or_init_config() -> dict:
    sb = get_authed_sb()

    
    try:
        u = sb.auth.get_user()
    except Exception as e:
        st.error(f"DEBUG auth.get_user failed: {repr(e)}")
        st.stop()
    user_id = st.session_state["user_id"]

    cfg = db.get_config(sb, user_id)
    if cfg is None:
        cfg = default_config()
        db.upsert_config(sb, user_id, cfg)

    return normalize_config(cfg)


def save_config(cfg: dict) -> None:
    sb = get_authed_sb()
    user_id = st.session_state["user_id"]
    db.upsert_config(sb, user_id, cfg)


# -------------------- Option B config editor UI --------------------

def config_editor(cfg: dict) -> tuple[dict, bool]:
    cfg = normalize_config(cfg)
    save_clicked = False

    tabs = st.tabs(["General", "Guests", "Room categories", "Services & follow-ups", "Breakfast"])

    # --- General ---
    with tabs[0]:
        bw = dict(cfg.get("booking_window", {}))
        stay = dict(cfg.get("stay_length_nights", {}))

        col1, col2 = st.columns(2)
        with col1:
            bw["earliest_arrival"] = st.text_input("Earliest arrival (YYYY-MM-DD)", bw.get("earliest_arrival", ""))
            stay["min"] = st.number_input("Stay min nights", min_value=1, step=1, value=int(stay.get("min", 1)))
            cfg["max_services"] = st.number_input("Max extra services", min_value=0, step=1, value=int(cfg.get("max_services", 3)))
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
        st.caption("Add/edit guests. min_guests/max_guests control compatibility with room categories.")
        guests_df = pd.DataFrame(cfg.get("guests", []))
        if guests_df.empty:
            guests_df = pd.DataFrame([{"full_name": "", "comment": "", "min_guests": 1, "max_guests": 99}])

        guests_df = guests_df.reindex(columns=["full_name", "comment", "min_guests", "max_guests"])
        
        guests_df = st.data_editor(
            guests_df,
            use_container_width=True,
            num_rows="dynamic",
            key="guests_editor",
            column_config={
                "full_name": st.column_config.TextColumn("Full name", required=True),
                "comment": st.column_config.TextColumn("Comment"),
                "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
            },
        )
        guests_df["full_name"] = guests_df["full_name"].fillna("").astype(str)
        guests_df["comment"] = guests_df.get("comment", "").fillna("").astype(str)
        guests_df["min_guests"] = pd.to_numeric(guests_df["min_guests"], errors="coerce").fillna(1).astype(int)
        guests_df["max_guests"] = pd.to_numeric(guests_df["max_guests"], errors="coerce").fillna(99).astype(int)
        
        cfg["guests"] = guests_df.to_dict(orient="records")

    # --- Room categories ---
    with tabs[2]:
        cats_df = pd.DataFrame(cfg.get("room_categories", []))
        if cats_df.empty:
            cats_df = pd.DataFrame([{"name": "", "min_guests": 1, "max_guests": 99}])

        # ✅ force UI column order
        cats_df = cats_df.reindex(columns=["name", "min_guests", "max_guests"])
        
        cats_df = st.data_editor(
            cats_df,
            use_container_width=True,
            num_rows="dynamic",
            key="roomcats_editor",
            column_config={
                "name": st.column_config.TextColumn("Category name", required=True),
                "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
            },
        )
    
        # ✅ keep numeric columns numeric
        cats_df["name"] = cats_df["name"].fillna("").astype(str)
        cats_df["min_guests"] = pd.to_numeric(cats_df["min_guests"], errors="coerce").fillna(1).astype(int)
        cats_df["max_guests"] = pd.to_numeric(cats_df["max_guests"], errors="coerce").fillna(99).astype(int)
    
        cfg["room_categories"] = cats_df.to_dict(orient="records")

    # --- Services & follow-ups ---
    with tabs[3]:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Extra services")
            services_txt = st.text_area(
                "One per line",
                "\n".join(cfg.get("extra_services", [])),
                height=240,
                key="cfg_extra_services_textarea",
                )
            cfg["extra_services"] = [s.strip() for s in services_txt.splitlines() if s.strip()]
        with col2:
            st.subheader("Follow-up tasks")
            followups_txt = st.text_area(
                "One per line",
                "\n".join(cfg.get("follow_up_tasks", [])),
                height=240,
                key="cfg_followups_textarea",
                )   
            cfg["follow_up_tasks"] = [s.strip() for s in followups_txt.splitlines() if s.strip()]

    # --- Breakfast ---
    with tabs[4]:
        pol = dict(cfg.get("breakfast_policy", {}))
        pol["enabled"] = st.checkbox("Enable breakfast", bool(pol.get("enabled", False)))
        pol["probability_any_breakfast"] = st.slider("Probability any breakfast", 0.0, 1.0, float(pol.get("probability_any_breakfast", 0.7)))
        pol["probability_full_group_if_any"] = st.slider("Probability full group if any", 0.0, 1.0, float(pol.get("probability_full_group_if_any", 0.7)))

        types_txt = st.text_area(
                "Breakfast types (one per line)",
                "\n".join(cfg.get("breakfast_types", [])),
                height=160,
                key="cfg_breakfast_types_textarea",
            )
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


# -------------------- main UI --------------------

st.set_page_config(page_title="PMS Trainer", layout="wide")

if not is_logged_in():
    login_ui()
    st.stop()

# Top bar
with st.sidebar:
    st.write(f"**Logged in:** {st.session_state.get('user_email', '')}")
    if st.button("Logout"):
        logout()

# Load config once per session (or when missing)
if "cfg" not in st.session_state:
    st.session_state["cfg"] = load_or_init_config()

cfg = st.session_state["cfg"]

st.title("PMS Scenario Generator")

page = st.radio("Menu", ["Scenario", "Config", "Task history"], horizontal=True)

if page == "Config":
    updated_cfg, save_clicked = config_editor(cfg)
    st.session_state["cfg"] = updated_cfg
    if save_clicked:
        try:
            save_config(updated_cfg)
            st.success("Saved config to database.")
        except Exception as e:
            st.error(f"Save failed: {e}")

elif page == "Scenario":
    col1, col2 = st.columns([2, 1], gap="large")

    with col1:
        if st.button("New task", type="primary"):
            st.session_state["scenario"] = generate_scenario(cfg)
            st.session_state["generated_id"] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            st.session_state["followup"] = None

        scenario = st.session_state.get("scenario")
        if scenario:
            st.subheader("Scenario")
            
            guest_comment = scenario.get("Guest comment", "").strip()
            extra_services = scenario.get("Extra services", "(none)")
            
            with st.container(border=True):
            
                # Guest
                st.markdown(f"**Guest name**  \n{scenario.get('Guest name', '')}")
                if guest_comment:
                    st.caption(guest_comment)
            
                st.divider()
            
                # Core booking info (label-value rows)
                def row(label, value):
                    c1, c2 = st.columns([1, 3])
                    c1.markdown(f"**{label}**")
                    c2.markdown(str(value) if value is not None else "")
            
                row("Room category", scenario.get("Room category", ""))
                row("Number of guests", scenario.get("Number of guests", ""))
                row("Nights", scenario.get("Nights", ""))
                row("Arrival", scenario.get("Arrival", ""))
                row("Departure", scenario.get("Departure", ""))
            
                st.divider()
            
                # Extra services
                st.markdown("**Extra services**")
                if extra_services and extra_services != "(none)":
                    for s in [x.strip() for x in extra_services.split(",") if x.strip()]:
                        st.markdown(f"- {s}")
                else:
                    st.markdown("- None")
        else:
            st.info("Click **New task** to generate a scenario.")

    with col2:
        st.subheader("Completion")

        with st.form("finish_task"):
            booking_number = st.text_input("Booking number")

            submitted = st.form_submit_button(
                "Mark finished",
                disabled=not st.session_state.get("scenario")
            )

        # handle submit OUTSIDE the form block (cleaner Streamlit pattern)
        if submitted:
            if not booking_number.strip():
                st.error("Please enter a booking number.")
                st.stop()

            followup: Optional[str] = None
            if should_generate_followup(cfg):
                followup = pick_random_followup(cfg)

            try:
                sb = get_authed_sb()
                db.insert_task(
                    sb=sb,
                    user_id=st.session_state["user_id"],
                    generated_id=st.session_state["generated_id"],
                    booking_number=booking_number.strip(),
                    scenario_json=st.session_state["scenario"],
                    followup_text=followup,
                )
                st.success("Saved task result to database.")
            except Exception as e:
                st.error(f"Saving task failed: {e}")
                st.stop()

            txt = render_task_text(
                st.session_state["scenario"],
                booking_number.strip(),
                st.session_state["generated_id"],
                followup,
            )

            st.download_button(
                "Download task TXT",
                data=txt,
                file_name=f"PMS_Task_{st.session_state['generated_id']}_BN-{booking_number.strip()}.txt",
            )

            if followup:
                st.warning(f"Follow-up: {followup}")    
elif page == "Task history":
    st.subheader("Task history (latest 50)")

    try:
        sb = get_authed_sb()
        rows = db.list_tasks(sb, st.session_state["user_id"], limit=50)
    except Exception as e:
        st.error(f"Could not load task history: {e}")
        st.stop()

    if not rows:
        st.info("No tasks saved yet.")
        st.stop()

    # Hide OK tasks by default
    hide_okay = st.checkbox("Hide tasks marked 'okay'", value=True)

    def _date_only(ts: str) -> str:
        try:
            return str(pd.to_datetime(ts).date())
        except Exception:
            return str(ts)[:10]

    # Build table (and keep an index mapping back to the underlying row)
    table_rows = []
    row_map = []  # maps displayed row index -> original rows index

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
                "Room category": sc.get("Room category", ""),
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

    # Map back to the original row
    r = rows[row_map[selected_display_idx]]
    scenario = r.get("scenario_json", {}) or {}
    followup = r.get("followup_text") or ""
    finished = _date_only(r.get("finished_at", ""))

    # --- Trainer review control ---
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
            sb2 = get_authed_sb()
            db.update_task_review_status(sb2, task_id, new_status)
            st.success("Saved trainer review.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save review status: {e}")

    # --- Non-tech friendly details ---
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

        row_line("Room category", scenario.get("Room category", ""))
        row_line("Number of guests", scenario.get("Number of guests", ""))
        row_line("Nights", scenario.get("Nights", ""))
        row_line("Arrival", scenario.get("Arrival", ""))
        row_line("Departure", scenario.get("Departure", ""))

        st.divider()

        st.markdown("**Extra services**")
        if extra_services and extra_services != "(none)":
            for s in [x.strip() for x in str(extra_services).split(",") if x.strip()]:
                st.markdown(f"- {s}")
        else:
            st.markdown("- None")

        if followup:
            st.divider()
            st.markdown("**Follow-up**")
            st.markdown(f"- {followup}")

    # Download TXT still available
    txt = render_task_text(
        scenario,
        r.get("booking_number", ""),
        r.get("generated_id", ""),
        followup if followup else None,
    )
    st.download_button(
        "Download TXT",
        data=txt,
        file_name=f"PMS_Task_{r.get('generated_id','task')}_BN-{r.get('booking_number','')}.txt",
        key=f"dl_{task_id}",
    )
