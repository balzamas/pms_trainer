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
    supabase-py returns different shapes depending on version,
    but session+user is typically accessible as .session / .user.
    """
    session = getattr(auth_res, "session", None) or auth_res.get("session")
    user = getattr(auth_res, "user", None) or auth_res.get("user")

    if not session or not user:
        # Some versions pack in auth_res.data
        data = getattr(auth_res, "data", None) or auth_res.get("data") or {}
        session = session or data.get("session")
        user = user or data.get("user")

    if not session or not user:
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

        guests_df = st.data_editor(
            guests_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "full_name": st.column_config.TextColumn("Full name", required=True),
                "comment": st.column_config.TextColumn("Comment"),
                "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
            },
        )
        cfg["guests"] = guests_df.fillna("").to_dict(orient="records")

    # --- Room categories ---
    with tabs[2]:
        cats_df = pd.DataFrame(cfg.get("room_categories", []))
        if cats_df.empty:
            cats_df = pd.DataFrame([{"name": "", "min_guests": 1, "max_guests": 1}])

        cats_df = st.data_editor(
            cats_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Category name", required=True),
                "min_guests": st.column_config.NumberColumn("Min guests", min_value=1, step=1),
                "max_guests": st.column_config.NumberColumn("Max guests", min_value=1, step=1),
            },
        )
        cfg["room_categories"] = cats_df.fillna("").to_dict(orient="records")

    # --- Services & follow-ups ---
    with tabs[3]:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Extra services")
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

st.title("PMS Training Scenario Generator (Web)")

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
            st.json(scenario)
        else:
            st.info("Click **New task** to generate a scenario.")

    with col2:
        st.subheader("Completion")
        booking_number = st.text_input("Booking number")

        can_finish = bool(st.session_state.get("scenario")) and booking_number.strip()

        if st.button("Mark finished", disabled=not can_finish):
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
    else:
        # Friendly table
        df = pd.DataFrame(
            [
                {
                    "finished_at": r.get("finished_at"),
                    "booking_number": r.get("booking_number"),
                    "generated_id": r.get("generated_id"),
                    "followup": r.get("followup_text") or "",
                }
                for r in rows
            ]
        )
        st.dataframe(df, use_container_width=True)

        # Expand details + download from stored JSON
        st.divider()
        st.subheader("Details")
        for r in rows[:10]:
            with st.expander(f"{r.get('finished_at')} — BN {r.get('booking_number')} — {r.get('generated_id')}"):
                st.json(r.get("scenario_json", {}))
                txt = render_task_text(
                    r.get("scenario_json", {}),
                    r.get("booking_number", ""),
                    r.get("generated_id", ""),
                    r.get("followup_text"),
                )
                st.download_button(
                    "Download TXT",
                    data=txt,
                    file_name=f"PMS_Task_{r.get('generated_id')}_BN-{r.get('booking_number')}.txt",
                    key=f"dl_{r.get('id')}",
                )
