import streamlit as st


def render_login_explanation() -> None:
    st.markdown("### What this tool is for")
    st.write(
        "PMS Trainer creates realistic booking scenarios for training. "
        "Trainees create the booking in the real PMS. "
        "Trainers then review the result and mark it as Okay or Needs review."
    )

    with st.expander("How the training workflow works", expanded=False):
        st.markdown("**Step 1 — Generate a scenario**")
        st.write("The tool generates a booking request (guest, dates, room category, special requests etc.).")
        st.markdown("**Step 2 — Create the booking in the PMS**")
        st.write("The trainee creates the booking in the real PMS according to the scenario.")
        st.markdown("**Step 3 — Review**")
        st.write("The trainer compares scenario vs. booking and marks the task as Okay or Needs review.")


def render_help_tab() -> None:
    st.markdown("## Help")
    st.write(
        "This page explains the workflow and the main options in PMS Trainer. "
        "It is written for trainees and trainers."
    )

    st.markdown("### Workflow (from start to feedback)")
    st.markdown("**1) Scenario is generated**")
    st.write(
        "A new task is created with a realistic booking request. "
        "This is the description of what should be entered into the PMS."
    )

    st.markdown("**2) Trainee creates the booking in the PMS**")
    st.write(
        "The trainee opens the real PMS and creates the booking exactly as described: "
        "dates, room category, number of guests, guest details, and any special requests."
    )

    st.markdown("**3) Trainer reviews the booking**")
    st.write(
        "The trainer checks the booking in the PMS, compares it with the scenario, "
        "and then marks the task:"
    )
    st.markdown("- New: not reviewed yet")
    st.markdown("- Okay: correct booking")
    st.markdown("- Needs review: mistakes found or improvements needed")

    st.divider()

    st.markdown("### Tabs and what they do")

    st.markdown("**Generate task**")
    st.write(
        "Creates a new scenario. The scenario text is what the trainee should follow "
        "when creating the booking in the PMS."
    )

    st.markdown("**Task history**")
    st.write(
        "Shows previously generated tasks and their status. "
        "Click a row to see details in a readable format."
    )

    st.divider()

    st.markdown("### Common checks when reviewing")
    st.markdown("- Dates and length of stay")
    st.markdown("- Room category and number of guests")
    st.markdown("- Guest data and special requests")
