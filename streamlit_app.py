"""Streamlit review UI for controlled benchmark and live email testing."""

from __future__ import annotations

import os
from pathlib import Path
import tomllib

import streamlit as st

from email_assistant.drafting import DEFAULT_WEB_MODEL, OpenAIDrafter, TRUWebDrafter
from email_assistant.models import IncomingEmail
from email_assistant.pipeline import process_message
from email_assistant.screening import (
    full_detector,
    no_screening_detector,
    original_detector,
)
from generate_dataset import load_csv, read_policy


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "university_email_650.csv"
POLICY_PATH = ROOT / "university_test_policy.json"

PHASES = {
    "Phase 1 — No screening": {
        "detector": no_screening_detector,
        "output_check": False,
        "description": (
            "Drafting assistant only. Application-level prompt-injection screening and "
            "draft output checks are intentionally disabled for the baseline."
        ),
    },
    "Phase 2 — Original-message rules": {
        "detector": original_detector,
        "output_check": False,
        "description": (
            "Applies detection rules to the original message only. Disguise-revealing "
            "cleaning and draft output checks are not enabled."
        ),
    },
    "Phase 3 — Full security controls": {
        "detector": full_detector,
        "output_check": True,
        "description": (
            "Inspects original and cleaned representations and enables draft/privacy "
            "output checks. Mock action authorization remains an independently tested control."
        ),
    },
}

DISGUISE_LABELS = {
    "plain": "Plain attack",
    "hidden_html": "Hidden HTML",
    "base64": "Base64 encoded",
    "zero_width": "Invisible characters",
    "lookalike": "Unicode look-alikes",
}

ATTACK_GOAL_LABELS = {
    "policy_override": "Policy override",
    "private_disclosure": "Private-data disclosure",
    "record_read": "Unauthorized record read",
    "external_transfer": "External data transfer",
    "unauthorized_send": "Unauthorized send / false send claim",
}


def _pretty(value: str) -> str:
    return value.replace("_", " ").strip().title()


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


def _case_display(row: dict) -> str:
    subject = row["subject"].strip() or "(No subject)"
    if row["label"] == "genuine":
        return f"{subject} — Genuine — {row['case_id']}"

    disguise = DISGUISE_LABELS.get(row["disguise"], _pretty(row["disguise"]))
    goal = ATTACK_GOAL_LABELS.get(row["attack_goal"], _pretty(row["attack_goal"]))
    return f"{subject} — {disguise} — {goal} — {row['case_id']}"


def _friendly_status(result) -> None:
    if result.verdict == "pass":
        st.success("Ready for review")
        st.caption("The selected phase allowed a draft to be prepared.")
    elif result.verdict == "block":
        st.error("Message blocked")
        st.caption("The selected phase stopped the message before drafting.")
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
    "Test prompt-injection defenses with the fixed 650-email benchmark or type a live email."
)
st.caption(
    "Prototype only. Drafts are for staff review and are never sent automatically."
)

source_mode = st.radio(
    "Testing mode",
    ["650-email dataset", "Live email test"],
    horizontal=True,
)

phase_name = st.selectbox(
    "Experiment phase",
    list(PHASES),
    index=2,
)
phase = PHASES[phase_name]
st.caption(phase["description"])

if phase_name.startswith("Phase 1"):
    st.warning(
        "Baseline mode intentionally disables application-level screening and output checks."
    )

message = None
dataset_case = None
uses_fixed_policy = source_mode == "650-email dataset"

if source_mode == "650-email dataset":
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
                "Controlled evaluation mode: all cases use the fixed fictional policy so "
                "results remain comparable across the three phases."
            )

            filter_left, filter_right = st.columns(2)
            with filter_left:
                case_type = st.selectbox(
                    "Email type",
                    ["All emails", "Genuine enquiries", "Attack emails"],
                )

            if case_type == "Genuine enquiries":
                disguise_choice = "Not applicable"
                with filter_right:
                    st.selectbox(
                        "Attack disguise",
                        ["Not applicable"],
                        disabled=True,
                    )
            else:
                disguise_options = ["All attack disguises"] + [
                    DISGUISE_LABELS[key]
                    for key in ("plain", "hidden_html", "base64", "zero_width", "lookalike")
                ]
                with filter_right:
                    disguise_choice = st.selectbox(
                        "Attack disguise",
                        disguise_options,
                    )

            secondary_left, secondary_right = st.columns(2)
            with secondary_left:
                topic_values = sorted(
                    {row["topic"] for row in rows},
                    key=lambda value: _pretty(value).lower(),
                )
                topic_label = st.selectbox(
                    "Topic",
                    ["All topics"] + [_pretty(value) for value in topic_values],
                )

            with secondary_right:
                if case_type == "Genuine enquiries":
                    goal_label = st.selectbox(
                        "Attack goal",
                        ["Not applicable"],
                        disabled=True,
                    )
                else:
                    goal_values = sorted(
                        {row["attack_goal"] for row in rows if row["label"] == "attack"},
                        key=lambda value: ATTACK_GOAL_LABELS.get(value, _pretty(value)).lower(),
                    )
                    goal_label = st.selectbox(
                        "Attack goal",
                        ["All attack goals"]
                        + [
                            ATTACK_GOAL_LABELS.get(value, _pretty(value))
                            for value in goal_values
                        ],
                    )

            search_text = st.text_input(
                "Search cases",
                placeholder="Search by subject, topic, case ID, disguise, or attack goal...",
            ).strip().lower()

            filtered_rows = list(rows)

            if case_type == "Genuine enquiries":
                filtered_rows = [
                    row for row in filtered_rows if row["label"] == "genuine"
                ]
            elif case_type == "Attack emails":
                filtered_rows = [
                    row for row in filtered_rows if row["label"] == "attack"
                ]

            if case_type != "Genuine enquiries" and disguise_choice != "All attack disguises":
                disguise_key = next(
                    key for key, label in DISGUISE_LABELS.items()
                    if label == disguise_choice
                )
                filtered_rows = [
                    row for row in filtered_rows
                    if row["label"] == "attack" and row["disguise"] == disguise_key
                ]

            if topic_label != "All topics":
                filtered_rows = [
                    row for row in filtered_rows
                    if _pretty(row["topic"]) == topic_label
                ]

            if case_type != "Genuine enquiries" and goal_label != "All attack goals":
                goal_key = next(
                    key for key, label in ATTACK_GOAL_LABELS.items()
                    if label == goal_label
                )
                filtered_rows = [
                    row for row in filtered_rows
                    if row["label"] == "attack" and row["attack_goal"] == goal_key
                ]

            if search_text:
                def _matches_search(row: dict) -> bool:
                    searchable = " ".join(
                        [
                            row["case_id"],
                            row["subject"],
                            row["topic"],
                            row["disguise"],
                            row["attack_goal"],
                            DISGUISE_LABELS.get(row["disguise"], ""),
                            ATTACK_GOAL_LABELS.get(row["attack_goal"], ""),
                        ]
                    ).lower()
                    return search_text in searchable

                filtered_rows = [row for row in filtered_rows if _matches_search(row)]

            filtered_rows = sorted(
                filtered_rows,
                key=lambda row: (
                    row["subject"].lower(),
                    row["label"],
                    row["case_id"],
                ),
            )

            st.caption(f"{len(filtered_rows)} matching cases")

            if not filtered_rows:
                st.info("No test cases match those filters.")
            else:
                case_by_id = {row["case_id"]: row for row in filtered_rows}
                selected_case_id = st.selectbox(
                    "Choose an email",
                    list(case_by_id),
                    format_func=lambda case_id: _case_display(case_by_id[case_id]),
                )
                dataset_case = case_by_id[selected_case_id]
                message = _message_from_dataset(dataset_case)

else:
    st.caption(
        "Live testing mode uses the same selected security phase, but approved factual "
        "answers come from official TRU web sources rather than the fictional benchmark policy. "
        "Live tests are demonstrations and are not counted as formal 650-case results."
    )

    typed_sender = st.text_input("From", value="student@example.test")
    typed_subject = st.text_input(
        "Subject",
        placeholder="e.g., Registration question",
    )
    typed_body = st.text_area(
        "Email message",
        height=220,
        placeholder="Type the email body here...",
    )

    if typed_body.strip():
        message = _message_from_form(typed_sender, typed_subject, typed_body)

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
        if dataset_case["label"] == "genuine":
            case_summary = "Genuine enquiry"
        else:
            disguise = DISGUISE_LABELS.get(
                dataset_case["disguise"],
                _pretty(dataset_case["disguise"]),
            )
            goal = ATTACK_GOAL_LABELS.get(
                dataset_case["attack_goal"],
                _pretty(dataset_case["attack_goal"]),
            )
            case_summary = f"Attack · {disguise} · {goal}"
        st.caption(f"Benchmark case {dataset_case['case_id']}: {case_summary}")

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
                spinner_text = (
                    f"Running {phase_name} against the fixed benchmark policy..."
                )
            else:
                policy_text = ""
                drafter = TRUWebDrafter()
                spinner_text = (
                    f"Running {phase_name} and checking official TRU information..."
                )
        except (OSError, ValueError, RuntimeError):
            st.error("The drafting service could not be initialized.")
            st.stop()

        with st.spinner(spinner_text):
            result = process_message(
                message,
                detector=phase["detector"],
                drafter=drafter,
                policy_text=policy_text,
                output_check=phase["output_check"],
                audit=True,
            )

        st.divider()
        st.subheader("Review result")
        st.markdown(f"**{phase_name}**")
        _friendly_status(result)

        if dataset_case is not None:
            expected = (
                "Genuine enquiry"
                if dataset_case["label"] == "genuine"
                else "Attack case"
            )
            st.caption(
                f"Dataset label: {expected}. The label is shown for evaluation only and "
                "is not supplied to the detector."
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
