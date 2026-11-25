"""Public-facing review UI for the university email assistant."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import tomllib

import streamlit as st

from email_assistant.drafting import TRUWebDrafter
from email_assistant.ingest import parse_eml
from email_assistant.pipeline import process_message
from email_assistant.screening import full_detector


ROOT = Path(__file__).resolve().parent
DEMO_DIR = ROOT / "integration_test"


def _local_secrets() -> dict:
    """Read the project-local secrets file without exposing secret values."""
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}

    try:
        with secrets_path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _secret(name: str) -> str | None:
    """Read a secret from Streamlit, then fall back to the local TOML file."""
    value = None

    try:
        value = st.secrets.get(name)
    except Exception:
        pass

    if value is None:
        value = _local_secrets().get(name)

    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _configure_openai() -> bool:
    """Load OpenAI configuration and report whether an API key is available."""
    api_key = _secret("OPENAI_API_KEY")
    model = _secret("OPENAI_MODEL")

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if model:
        os.environ["OPENAI_MODEL"] = model

    return bool(os.getenv("OPENAI_API_KEY"))


def _parse_uploaded_email(uploaded_file):
    data = uploaded_file.getvalue()
    if len(data) > 1024 * 1024:
        raise ValueError("Uploaded email is larger than the supported limit")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as handle:
            handle.write(data)
            temp_path = Path(handle.name)

        message = parse_eml(temp_path)
        return replace(message, source_id=uploaded_file.name)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _friendly_status(result) -> None:
    if result.verdict == "pass":
        st.success("Ready for review")
        st.caption("Security checks passed and a draft was prepared.")
    elif result.verdict == "block":
        st.error("Message blocked")
        st.caption("The message was stopped by the security controls.")
    else:
        st.warning("Manual review required")
        if result.reason.startswith("Drafting failed"):
            st.caption(
                "A safe draft could not be prepared. Check the service configuration "
                "or review the message manually."
            )
        else:
            st.caption("No draft was released for this message.")


st.set_page_config(
    page_title="University Email Assistant",
    page_icon="✉️",
    layout="centered",
)

st.title("University Email Assistant")
st.write(
    "Review an incoming email and prepare a reply using information from the "
    "official Thompson Rivers University website."
)
st.caption(
    "Prototype only. Drafts are for staff review and are never sent automatically."
)

source_mode = st.radio(
    "Email source",
    ["Sample email", "Upload .eml"],
    horizontal=True,
)

message = None

if source_mode == "Sample email":
    demo_files = sorted(DEMO_DIR.glob("*.eml")) if DEMO_DIR.exists() else []

    if not demo_files:
        st.info("No sample emails are available.")
    else:
        selected_name = st.selectbox(
            "Choose a sample",
            [path.name for path in demo_files],
            label_visibility="collapsed",
        )
        try:
            message = parse_eml(DEMO_DIR / selected_name)
        except (OSError, ValueError):
            st.error("The selected email could not be opened.")
else:
    uploaded = st.file_uploader(
        "Upload an email file",
        type=["eml"],
        help="Maximum size: 1 MB",
    )

    if uploaded is not None:
        try:
            message = _parse_uploaded_email(uploaded)
        except (OSError, ValueError):
            st.error("The uploaded email could not be processed.")

if message is not None:
    st.divider()
    st.subheader("Incoming email")
    st.markdown(f"**From:** {message.sender or 'Unknown sender'}")
    st.markdown(f"**Subject:** {message.subject or '(No subject)'}")
    st.text_area(
        "Message",
        value=message.student_text,
        height=180,
        disabled=True,
    )

    if st.button("Review and draft reply", type="primary", use_container_width=True):
        configured = _configure_openai()

        if not configured:
            secrets_path = ROOT / ".streamlit" / "secrets.toml"
            st.error(
                "The drafting service is not configured. "
                "Check that .streamlit/secrets.toml contains OPENAI_API_KEY."
            )
            if not secrets_path.exists():
                st.caption("No local secrets file was found for this project.")
            st.stop()

        try:
            drafter = TRUWebDrafter()
        except RuntimeError:
            st.error("The drafting service could not be initialized.")
            st.stop()

        with st.spinner("Reviewing email and checking official TRU information..."):
            result = process_message(
                message,
                detector=full_detector,
                drafter=drafter,
                policy_text="",
                output_check=True,
                audit=True,
            )

        st.divider()
        st.subheader("Review result")
        _friendly_status(result)

        if result.draft:
            st.subheader("Suggested reply")
            st.text_area(
                "Draft reply",
                value=result.draft,
                height=240,
                disabled=True,
                label_visibility="collapsed",
            )

            if drafter.last_sources:
                st.markdown("**Official sources used**")
                for index, source in enumerate(drafter.last_sources[:5], start=1):
                    label = source.get("title") or f"TRU source {index}"
                    st.link_button(
                        label,
                        source["url"],
                        use_container_width=True,
                    )

            st.caption("Review the draft before using it.")
