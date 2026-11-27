"""Protected live TRU draft-only demonstration for local and shared Streamlit use.

All email inputs must be fictional. No real inbox or student records.
Normal 650-case replay retains its own fixed evaluation policy.
"""
from __future__ import annotations

import os

import streamlit as st

from email_assistant.ingest import _html_text
from email_assistant.models import IncomingEmail
from email_assistant.pipeline import process_message
from email_assistant.screening import full_detector
from email_assistant.tru_web_drafting import TRUWebDrafter


def _configure_secret_settings() -> bool:
    # In local development st.secrets reads ignored .streamlit/secrets.toml.
    # On Streamlit Community Cloud it reads secrets from deployment settings.
    # Never display or persist secret values.
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        try:
            value = st.secrets.get(name)
        except Exception:
            # Streamlit raises a custom exception if the local secrets file is absent.
            value = None
        if value:
            os.environ[name] = str(value).strip()
    return bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


st.set_page_config(page_title="Live TRU Drafting | COMP 3260", page_icon="🛡️",
                   layout="centered")

st.title("🛡️ Live TRU drafting test")
st.caption("Protected mode only · official tru.ca web search · human review only")

st.warning(
    "Use fictional student questions only. No actual student records, grades, "
    "student IDs, passwords or other sensitive information. The app does not send email."
)

with st.expander("How this differs from the 650-case benchmark"):
    st.write(
        "This screen uses a real OpenAI model and official TRU website search "
        "for a SINGLE fictional enquiry. The 650-email experiment uses a frozen "
        "fictional university policy for repeatable comparisons. These outcomes "
        "must be reported separately."
    )

configured = _configure_secret_settings()
if not configured:
    st.info(
        "OpenAI is not configured on this server. A developer must set "
        "OPENAI_API_KEY and OPENAI_MODEL in local .streamlit/secrets.toml "
        "or the private deployment's Secrets settings."
    )
else:
    st.caption("OpenAI credentials and model are configured on this server; "
               "the key is never displayed in the interface.")

sender = st.text_input("Fictional sender", value="student@example.test")
subject = st.text_input("Subject", value="Registration enquiry")
format_choice = st.radio("Email format", ("Plain text", "HTML"), horizontal=True)
body = st.text_area(
    "Fictional student email",
    value="Hello Enrolment Services, where can I find the registration deadlines on the official TRU website?",
    height=200,
)
if format_choice == "HTML":
    st.caption("Raw HTML is examined by the detector; only extracted visible text "
               "is passed to the drafting model.")

consent = st.checkbox("This contains only fictional data and I approve one billable OpenAI request.")
if st.button("Screen and prepare draft", type="primary",
             disabled=not (configured and consent and bool(body.strip()) and bool(subject.strip()))):
    mime = "text/html" if format_choice == "HTML" else "text/plain"
    try:
        if mime == "text/html":
            all_html_text, visible_text = _html_text(body)
            inspection = body + "\n" + all_html_text
        else:
            visible_text = body
            inspection = body

        message = IncomingEmail(
            source_id="synthetic-live-tru-form",
            sender=sender,
            subject=subject,
            raw_body=body,
            inspection_text=inspection,
            student_text=visible_text,
            content_type=mime,
        )
        drafter = TRUWebDrafter()
        with st.spinner("Screening and consulting official TRU pages..."):
            result = process_message(
                message, detector=full_detector,
                drafter=drafter, policy_text="", output_check=True,
            )
        st.subheader("Review result")
        if result.verdict == "pass":
            st.success("PASS — draft available for staff review")
        elif result.verdict == "block":
            st.error("BLOCK — suspicious email stopped; no draft")
        else:
            st.warning("REVIEW — drafting held for human inspection")
        st.write(f"**Reason:** {result.reason}")
        if result.evidence:
            st.code(result.evidence)
        if result.draft:
            st.text_area("Unsent draft", result.draft, height=240, disabled=True)
            if drafter.last_sources:
                st.markdown("**Official TRU sources**")
                for reference in drafter.last_sources[:5]:
                    st.link_button(
                        reference["title"], reference["url"],
                        use_container_width=True,
                    )
        else:
            st.info("No draft was released.")
        st.caption("Never use the draft without human verification. No email was sent.")
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        # Never display a secret or raw provider traceback to Streamlit viewers.
        st.error(f"Live drafting could not complete ({type(exc).__name__}). "
                 "Check the deployment logs and provider configuration.")

st.page_link("streamlit_app.py", label="Return to the main evaluation app", icon="⬅️")
