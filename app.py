
import streamlit as st

from database.db_manager import (
    initialize_db,
    get_verdicts,
    get_action_requests,
    get_test_results,
    get_database_summary
)

from security.output_validator import validate_output


# ----------------------------------
# PAGE CONFIGURATION
# ----------------------------------

st.set_page_config(
    page_title="University Email Security",
    page_icon="🛡️",
    layout="wide"
)


# ----------------------------------
# INITIALIZE DATABASE
# ----------------------------------

initialize_db()


# ----------------------------------
# PAGE HEADER
# ----------------------------------

st.title("🛡️ University Email Security Dashboard")

st.write(
    "Review incoming university emails, security verdicts, "
    "generated drafts and security audit records."
)

st.divider()


# ----------------------------------
# LOAD DATABASE RECORDS
# ----------------------------------

summary = get_database_summary()

verdicts = get_verdicts()
actions = get_action_requests()
tests = get_test_results()


# ----------------------------------
# DASHBOARD STATISTICS
# ----------------------------------

st.subheader("Security Overview")

total_verdicts = summary["total_verdicts"]

passed = sum(
    1 for item in verdicts
    if item["verdict"].upper() == "PASS"
)

review = sum(
    1 for item in verdicts
    if item["verdict"].upper() == "REVIEW"
)

blocked = sum(
    1 for item in verdicts
    if item["verdict"].upper() == "BLOCK"
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Emails", total_verdicts)
col2.metric("Passed", passed)
col3.metric("Under Review", review)
col4.metric("Blocked", blocked)

st.divider()


# ----------------------------------
# EMAIL REVIEW SECTION
# ----------------------------------

st.subheader("Email Security Review")

if not verdicts:

    st.info(
        "No email verdicts have been recorded yet. "
        "Process an email through the security pipeline first."
    )

else:

    for item in verdicts:

        verdict = item["verdict"].upper()

        if verdict == "PASS":
            status = "🟢 PASS"

        elif verdict == "REVIEW":
            status = "🟡 REVIEW"

        elif verdict == "BLOCK":
            status = "🔴 BLOCK"

        else:
            status = f"⚪ {verdict}"

        with st.expander(
            f"Email: {item['email_id'] or item['id']} | {status}"
        ):

            st.write("**Verdict:**", verdict)

            st.write(
                "**Reason:**",
                item["reason"] or "No reason recorded."
            )

            st.write("**Evidence:**")

            st.code(
                item["evidence"] or "No evidence recorded."
            )

            st.caption(
                f"Recorded: {item['timestamp']}"
            )


st.divider()


# ----------------------------------
# DRAFT OUTPUT VALIDATOR
# ----------------------------------

st.subheader("Draft Output Validation")

st.write(
    "Test a generated email draft before it is displayed "
    "to a university staff member."
)

draft = st.text_area(
    "Enter an email draft:",
    placeholder="Enter the generated email response here..."
)

if st.button("Validate Draft"):

    result = validate_output(draft)

    if result["approved"]:

        st.success("Draft approved by the output validator.")

    else:

        st.error("Draft rejected. Potential disclosure detected.")

    st.write("**Reason:**", result["reason"])

    st.write(
        "**Detected Issues:**",
        result["detected_issues"]
    )


st.divider()


# ----------------------------------
# ACTION REQUEST AUDIT LOG
# ----------------------------------

st.subheader("Mock Action Audit Log")

if not actions:

    st.info("No mock action requests have been recorded.")

else:

    for action in actions:

        with st.expander(
            f"{action['action_type']} | "
            f"{'APPROVED' if action['approved'] else 'DENIED'}"
        ):

            st.write("**Action:**", action["action_type"])

            st.write("**Target:**", action["target"])

            if action["approved"]:
                st.success("Action approved.")
            else:
                st.error("Action denied.")

            st.write("**Reason:**", action["reason"])

            st.caption(action["timestamp"])


st.divider()


# ----------------------------------
# TEST RESULTS
# ----------------------------------

st.subheader("System Test Results")

if not tests:

    st.info("No test results have been recorded.")

else:

    for test in tests:

        with st.expander(
            f"{test['test_name']} | {test['status']}"
        ):

            st.write("**Status:**", test["status"])

            st.write("**Details:**", test["details"])

            st.caption(test["timestamp"])


st.divider()


# ----------------------------------
# REFRESH DASHBOARD
# ----------------------------------

if st.button("Refresh Dashboard"):

    st.rerun()


st.caption(
    "COMP 3260 | Network Security Project | "
    "University Email Prompt Injection Detection"
)
