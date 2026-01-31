import streamlit as st

def render_login_explanation() -> None:
    """Shown on the login screen, above or next to the login form."""
    st.markdown("### What this tool is for")
    st.write(
        "PMS Trainer creates realistic booking scenarios for training. "
        "Trainees create the booking in the real PMS. "
        "Trainers then review the result and mark it as Okay or Needs review."
    )

    with st.expander("How the training workflow works", expanded=False):
        st.markdown("**Step 1 — Generate a scenario**")
        st.write("The tool generates a booking request (guest, dates, room category, guests, special requests).")
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

    # -------------------- workflow --------------------
    st.markdown("### Workflow (from scenario to feedback)")

    st.markdown("**1) Scenario is generated**")
    st.write(
        "A new task is created with a realistic booking request. "
        "This is the description of what should be entered into the PMS."
    )

    st.markdown("**2) Trainee creates the booking in the PMS**")
    st.write(
        "The trainee opens the real PMS and creates the booking exactly as described: "
        "dates, room type, number of guests, guest details, and any special requests."
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

    # -------------------- navigation --------------------
    st.markdown("### Pages and what they do")

    st.markdown("**Scenario**")
    st.write(
        "Generate a new scenario and use it as the instruction for the trainee. "
        "After the trainee created the booking in the PMS, enter the booking number and mark the task as finished."
    )

    st.markdown("**Task history**")
    st.write(
        "Shows previously finished tasks. Click a row to see the scenario details in a readable format. "
        "Trainers can mark each task as Okay or Needs review."
    )

    st.markdown("**Config**")
    st.write(
        "This controls what kind of scenarios can be generated. "
        "You can think of it as the training setup: which guests exist, which room types exist, "
        "what requests/extras are possible, and what the date range should be."
    )

    st.divider()

    # -------------------- config explained --------------------
    st.markdown("### Config explained (what each section changes)")

    st.markdown("**General**")
    st.write(
        "Controls the timeframe and basic limits for generated scenarios."
    )
    st.markdown("- **Earliest arrival / Latest arrival**: scenarios will use arrival dates within this range.")
    st.markdown("- **Stay min nights / Stay max nights**: scenarios will use a stay length within this range.")
    st.markdown(
        "- **Max requests & extras**: maximum number of requests/extras that can appear in a scenario. "
        "This applies to the combined pool of global extras and room-type extras."
    )
    st.markdown("- **Follow-up chance**: probability that a follow-up task is generated when a task is finished.")

    st.markdown("**Guest profiles**")
    st.write(
        "Defines the guest names that can appear in scenarios. "
        "Each guest can include a short comment (example: 'VIP', 'returning guest', 'allergic to nuts')."
    )
    st.markdown(
        "- **Min guests / Max guests**: how many guests this profile can represent. "
        "Example: a profile can be restricted to 1–2 guests."
    )

    st.markdown("**Room types**")
    st.write(
        "Defines the room types that can appear in scenarios."
    )
    st.markdown(
        "- **Min guests / Max guests**: occupancy range for that room type. "
        "This helps generate realistic pairings between room type and number of guests."
    )
    st.markdown(
        "- **Category extras**: optional extras specific to this room type. Use ';' to separate items. "
        "These extras are mixed into the scenario's requests/extras."
    )

    st.markdown("**Requests & follow-ups**")
    st.write(
        "Controls what kinds of extras and follow-up tasks can appear."
    )
    st.markdown(
        "- **Requests & extras (global)**: one item per line. These can be selected for any room type."
    )
    st.markdown(
        "- **Follow-up tasks**: one item per line. These can appear as an additional training task after finishing."
    )

    st.markdown("**Breakfast**")
    st.write(
        "Controls whether pre order breakfast can be part of scenarios."
    )
    st.markdown("- **Enable breakfast**: allows breakfast items to appear in scenarios.")
    st.markdown(
        "- **Probability any breakfast**: chance that breakfast is included at all."
    )
    st.markdown(
        "- **Probability full group if any**: if breakfast is included, chance it applies to all guests."
    )
    st.markdown("- **Breakfast types**: one type per line (example: 'Buffet', 'Continental', 'Vegan').")

    st.divider()

    # -------------------- practical tips --------------------
    st.markdown("### Practical tips")

    st.markdown("**For trainees**")
    st.markdown("- Read the scenario carefully before starting in the PMS.")
    st.markdown("- Double-check: dates, room type, number of guests, and requests.")
    st.markdown("- Use notes/remarks fields for special requests when appropriate.")

    st.markdown("**For trainers**")
    st.markdown("- Review tasks in Task history and focus on New / Needs review.")
    st.markdown("- When marking Needs review, discuss the booking together and explain what to change next time.")

    st.divider()

    st.markdown("### Troubleshooting")
    with st.expander("I cannot find a generated task", expanded=False):
        st.write("Check the Task history filter and make sure tasks are not hidden by the status filter.")

    st.markdown("### Dev")
    st.markdown("d.berger@dontsniff.co.uk")
    st.markdown("https://github.com/balzamas/pms_trainer/")

    
