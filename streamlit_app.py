"""Public-facing review UI for the university email assistant."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import tomllib

import streamlit as st

from email_assistant.drafting import DEFAULT_WEB_MODEL, OpenAIDrafter, TRUWebDrafter
from email_assistant.ingest import parse_eml
from email_assistant.models import IncomingEmail
from email_assistant.pipeline import process_message
from email_assistant.screening import full_detector
from generate_dataset import load_csv, read_policy


ROOT = Path(__file__).resolve().parent
DEMO_DIR = ROOT / "integration_test"
DATASET_PATH = ROOT / "university_email_650.csv"
POLICY_PATH = ROOT / "university_test_policy.json"


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


@st.cache_data(show_spinner=False)
def _dataset_rows() -> list[dict]:
    return load_csv(DATASET_PATH)


@st.cache_data(show_spinner=False)
def _evaluation_policy() -> dict:
    return read_policy(POLICY_PATH)


def _message_from_dataset(row: dict) -> IncomingEmail:
    return IncomingEmail(
        source_id=row["case_id"],
        sender=row["sender"],
        subject=row["subject"],
        raw_body=row["raw_body"],
        inspection_text=row["inspection_text"],
        student_text=row["visible_text"],
        content_type=row["content_type"],
    )


def _message_from_form(sender: str, subject: str, body: str) -> IncomingEmail:
    return IncomingEmail(
        source_id="typed-live-email",
        sender=sender.strip() or "Unknown sender",
        subject=subject.strip(),
        raw_body=body,
        inspection_text=body,
        student_text=body,
        content_type="text/plain",
    )


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
    "Review an incoming email and prepare a reply using controlled university information."
)
st.caption(
    "Prototype only. Drafts are for staff review and are never sent automatically."
)

source_mode = st.radio(
    "Email source",
    ["650-email test set", "Type an email", "Upload .eml", "Demo sample"],
    horizontal=True,
)

message = None
dataset_case = None
uses_fixed_policy = False

if source_mode == "650-email test set":
    if not DATASET_PATH.exists():
        st.info("The 650-email test dataset is not available in this checkout.")
    else:
        try:
            rows = _dataset_rows()
        except (OSError, ValueError):
            rows = []
            st.error("The test dataset could not be loaded.")

        if rows:
            st.caption(
                "Controlled evaluation mode: these synthetic cases use the fixed fictional "
                "policy so results stay comparable across the benchmark."
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                label_choice = st.selectbox(
                    "Case type",
                    ["All", "Genuine", "Attack"],
                )
            with col2:
                disguises = sorted({row["disguise"] for row in rows})
                disguise_choice = st.selectbox(
                    "Disguise",
                    ["All"] + disguises,
                )
            with col3:
                topics = sorted({row["topic"] for row in rows})
                topic_choice = st.selectbox(
                    "Topic",
                    ["All"] + topics,
                )

            filtered_rows = rows
            if label_choice != "All":
                filtered_rows = [
                    row for row in filtered_rows
                    if row["label"].lower() == label_choice.lower()
                ]
            if disguise_choice != "All":
                filtered_rows = [
                    row for row in filtered_rows
                    if row["disguise"] == disguise_choice
                ]
            if topic_choice != "All":
                filtered_rows = [
                    row for row in filtered_rows
                    if row["topic"] == topic_choice
                ]

            if not filtered_rows:
                st.info("No test cases match those filters.")
            else:
                case_by_id = {row["case_id"]: row for row in filtered_rows}

                def _case_label(case_id: str) -> str:
                    row = case_by_id[case_id]
                    kind = row["label"].replace("_", " ").title()
                    disguise = row["disguise"].replace("_", " ").title()
                    return f"{case_id} · {kind} · {disguise} · {row['subject']}"

                selected_case_id = st.selectbox(
                    f"Choose a case ({len(filtered_rows)} shown)",
                    list(case_by_id),
                    format_func=_case_label,
                )
                dataset_case = case_by_id[selected_case_id]
                message = _message_from_dataset(dataset_case)
                uses_fixed_policy = True

elif source_mode == "Type an email":
    st.caption(
        "Live testing mode: type a plain-text email below. Approved factual answers are "
        "grounded in the official TRU website."
    )
    typed_sender = st.text_input("From", value="student@example.test")
    typed_subject = st.text_input("Subject")
    typed_body = st.text_area(
        "Message",
        height=220,
        placeholder="Type the email body here...",
    )
    if typed_body.strip():
        message = _message_from_form(typed_sender, typed_subject, typed_body)

elif source_mode == "Upload .eml":
    st.caption(
        "Live testing mode: uploaded messages use official TRU web information after "
        "security screening."
    )
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

else:
    st.caption(
        "Demo samples use official TRU web information after security screening."
    )
    demo_files = sorted(DEMO_DIR.glob("*.eml")) if DEMO_DIR.exists() else []

    if not demo_files:
        st.info("No demo sample emails are available.")
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

if message is not None:
    st.divider()
    st.subheader("Incoming email")
    st.markdown(f"**From:** {message.sender or 'Unknown sender'}")
    st.markdown(f"**Subject:** {message.subject or '(No subject)'}")
    st.text_area(
        "Message preview",
        value=message.student_text,
        height=180,
        disabled=True,
        label_visibility="collapsed",
    )

    if dataset_case is not None:
        st.caption(
            f"Benchmark case: {dataset_case['label'].title()} · "
            f"{dataset_case['disguise'].replace('_', ' ').title()} · "
            f"{dataset_case['topic'].replace('_', ' ').title()}"
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
            if uses_fixed_policy:
                policy_text = _evaluation_policy()["approved_policy"]
                drafter = OpenAIDrafter(
                    model=_secret("OPENAI_MODEL") or DEFAULT_WEB_MODEL
                )
                spinner_text = "Reviewing benchmark email against the fixed evaluation policy..."
            else:
                policy_text = ""
                drafter = TRUWebDrafter()
                spinner_text = "Reviewing email and checking official TRU information..."
        except (OSError, ValueError, RuntimeError):
            st.error("The drafting service could not be initialized.")
            st.stop()

        with st.spinner(spinner_text):
            result = process_message(
                message,
                detector=full_detector,
                drafter=drafter,
                policy_text=policy_text,
                output_check=True,
                audit=True,
            )

        st.divider()
        st.subheader("Review result")
        _friendly_status(result)

        if dataset_case is not None:
            expected = "Genuine enquiry" if dataset_case["label"] == "genuine" else "Attack case"
            st.caption(
                f"Dataset label: {expected}. This label is for benchmark evaluation, "
                "not an instruction to the detector."
            )

        if result.draft:
            st.subheader("Suggested reply")
            st.text_area(
                "Draft reply",
                value=result.draft,
                height=240,
                disabled=True,
                label_visibility="collapsed",
            )

            if uses_fixed_policy:
                st.caption(
                    "Draft facts were restricted to the synthetic fixed policy used by "
                    "the 650-case benchmark."
                )
            elif getattr(drafter, "last_sources", None):
                st.markdown("**Official sources used**")
                for index, source in enumerate(drafter.last_sources[:5], start=1):
                    label = source.get("title") or f"TRU source {index}"
                    st.link_button(
                        label,
                        source["url"],
                        use_container_width=True,
                    )

            st.caption("Review the draft before using it.")
