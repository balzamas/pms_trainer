# app.py
import streamlit as st
import pandas as pd
from config_model import normalize_config, validate_config

def config_editor(cfg: dict) -> tuple[dict, bool]:
    """
    Returns (updated_cfg, save_clicked)
    """
    cfg = normalize_config(cfg)
    save_clicked = False

    tabs = st.tabs(["General", "Guests", "Room categories", "Services & follow-ups", "Breakfast"])

    # --- General ---
    with tabs[0]:
        bw = cfg["booking_window"]
        stay = cfg["stay_length_nights"]

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
            key="guests_editor",
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
            key="cats_editor",
        )
        cfg["room_categories"] = cats_df.fillna("").to_dict(orient="records")

    # --- Services & follow-ups ---
    with tabs[3]:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Extra services")
            services = cfg.get("extra_services", [])
            services_txt = st.text_area("One per line", "\n".join(services), height=220, key="services_txt")
            cfg["extra_services"] = [s.strip() for s in services_txt.splitlines() if s.strip()]

        with col2:
            st.subheader("Follow-up tasks")
            followups = cfg.get("follow_up_tasks", [])
            followups_txt = st.text_area("One per line", "\n".join(followups), height=220, key="followups_txt")
            cfg["follow_up_tasks"] = [s.strip() for s in followups_txt.splitlines() if s.strip()]

    # --- Breakfast ---
    with tabs[4]:
        pol = cfg.get("breakfast_policy", {})
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
