"""Interactive benchmark dashboard for the 650-email evaluation set."""

from __future__ import annotations

import os
from pathlib import Path
import time
import tomllib

import pandas as pd
import streamlit as st

from email_assistant.drafting import DEFAULT_WEB_MODEL, MockDrafter, OpenAIDrafter
from email_assistant.models import IncomingEmail
from email_assistant.pipeline import process_message
from email_assistant.screening import (
    full_detector,
    no_screening_detector,
    original_detector,
)
from generate_dataset import load_csv, read_policy


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "university_email_650.csv"
POLICY_PATH = ROOT / "university_test_policy.json"

PHASES = {
    "Phase 1 — No screening": {
        "detector": no_screening_detector,
        "output_check": False,
    },
    "Phase 2 — Original-message rules": {
        "detector": original_detector,
        "output_check": False,
    },
    "Phase 3 — Full security controls": {
        "detector": full_detector,
        "output_check": True,
    },
}

DISGUISE_LABELS = {
    "genuine": "Genuine",
    "plain": "Plain attack",
    "hidden_html": "Hidden HTML",
    "base64": "Base64 encoded",
    "zero_width": "Invisible characters",
    "lookalike": "Unicode look-alikes",
}


def _message(row: dict) -> IncomingEmail:
    return IncomingEmail(
        source_id=row["case_id"],
        sender=row["sender"],
        subject=row["subject"],
        raw_body=row["raw_body"],
        inspection_text=row["inspection_text"],
        student_text=row["visible_text"],
        content_type=row["content_type"],
    )


@st.cache_data(show_spinner=False)
def _rows() -> list[dict]:
    return load_csv(DATASET_PATH)


@st.cache_data(show_spinner=False)
def _policy_text() -> str:
    return read_policy(POLICY_PATH)["approved_policy"]


def _configure_openai() -> bool:
    value = None
    model = None
    try:
        value = st.secrets.get("OPENAI_API_KEY")
        model = st.secrets.get("OPENAI_MODEL")
    except Exception:
        secrets_path = ROOT / ".streamlit" / "secrets.toml"
        if secrets_path.exists():
            try:
                with secrets_path.open("rb") as handle:
                    data = tomllib.load(handle)
                value = data.get("OPENAI_API_KEY")
                model = data.get("OPENAI_MODEL")
            except (OSError, tomllib.TOMLDecodeError):
                pass

    if value:
        os.environ["OPENAI_API_KEY"] = str(value).strip()
    if model:
        os.environ["OPENAI_MODEL"] = str(model).strip()
    return bool(os.getenv("OPENAI_API_KEY"))


def _run_screening(rows: list[dict]) -> pd.DataFrame:
    total = len(rows) * len(PHASES)
    progress = st.progress(0, text="Starting screening comparison...")
    records: list[dict] = []
    completed = 0

    for phase_name, config in PHASES.items():
        detector = config["detector"]
        for row in rows:
            started = time.perf_counter()
            decision = detector(_message(row))
            elapsed_ms = (time.perf_counter() - started) * 1000
            is_attack = row["label"] == "attack"
            flagged = decision.verdict in ("review", "block")

            records.append(
                {
                    "phase": phase_name,
                    "case_id": row["case_id"],
                    "label": row["label"],
                    "disguise": row["disguise"],
                    "topic": row["topic"],
                    "subject": row["subject"],
                    "attack_goal": row["attack_goal"],
                    "verdict": decision.verdict,
                    "flagged": flagged,
                    "attack_flagged": is_attack and flagged,
                    "missed_attack": is_attack and not flagged,
                    "false_alarm": (not is_attack) and flagged,
                    "screening_ms": elapsed_ms,
                    "reason": decision.reason,
                    "evidence": decision.evidence,
                }
            )
            completed += 1
            if completed % 20 == 0 or completed == total:
                progress.progress(
                    completed / total,
                    text=f"Processed {completed:,} of {total:,} phase/case checks",
                )

    progress.empty()
    return pd.DataFrame(records)


def _summary(screening_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for phase_name in PHASES:
        part = screening_df[screening_df["phase"] == phase_name]
        attack_total = int((part["label"] == "attack").sum())
        genuine_total = int((part["label"] == "genuine").sum())
        attack_flagged = int(part["attack_flagged"].sum())
        missed = int(part["missed_attack"].sum())
        false_alarms = int(part["false_alarm"].sum())
        genuine_passed = genuine_total - false_alarms
        rows.append(
            {
                "Phase": phase_name,
                "Attacks flagged": attack_flagged,
                "Attacks missed": missed,
                "Attack detection": 100 * attack_flagged / attack_total if attack_total else 0,
                "Genuine held": false_alarms,
                "Genuine passed": genuine_passed,
                "False-alarm rate": 100 * false_alarms / genuine_total if genuine_total else 0,
                "Avg screening ms": part["screening_ms"].mean(),
            }
        )
    return pd.DataFrame(rows)


def _disguise_summary(screening_df: pd.DataFrame) -> pd.DataFrame:
    attacks = screening_df[screening_df["label"] == "attack"].copy()
    grouped = (
        attacks.groupby(["phase", "disguise"], as_index=False)
        .agg(
            total=("case_id", "count"),
            flagged=("attack_flagged", "sum"),
            missed=("missed_attack", "sum"),
        )
    )
    grouped["detection_rate"] = 100 * grouped["flagged"] / grouped["total"]
    grouped["disguise"] = grouped["disguise"].map(
        lambda value: DISGUISE_LABELS.get(value, value.replace("_", " ").title())
    )
    return grouped


def _run_full_pipeline(rows: list[dict], provider: str) -> pd.DataFrame:
    policy = _policy_text()

    if provider == "OpenAI fixed-policy model":
        if not _configure_openai():
            raise RuntimeError("OpenAI API key is not configured")
        model = os.getenv("OPENAI_MODEL") or DEFAULT_WEB_MODEL
        drafter = OpenAIDrafter(model=model)
    else:
        drafter = MockDrafter()

    total = len(rows) * len(PHASES)
    progress = st.progress(0, text="Starting full pipeline replay...")
    records: list[dict] = []
    completed = 0

    for phase_name, config in PHASES.items():
        for row in rows:
            started = time.perf_counter()
            result = process_message(
                _message(row),
                detector=config["detector"],
                drafter=drafter,
                policy_text=policy,
                output_check=config["output_check"],
                audit=False,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            records.append(
                {
                    "phase": phase_name,
                    "case_id": row["case_id"],
                    "label": row["label"],
                    "disguise": DISGUISE_LABELS.get(row["disguise"], row["disguise"]),
                    "topic": row["topic"],
                    "subject": row["subject"],
                    "attack_goal": row["attack_goal"],
                    "verdict": result.verdict,
                    "draft_created": bool(result.draft),
                    "provider": result.provider,
                    "reason": result.reason,
                    "duration_ms": elapsed_ms,
                    "draft": result.draft or "",
                }
            )
            completed += 1
            if completed % 10 == 0 or completed == total:
                progress.progress(
                    completed / total,
                    text=f"Processed {completed:,} of {total:,} phase/case runs",
                )

    progress.empty()
    return pd.DataFrame(records)


st.set_page_config(
    page_title="650-Email Evaluation",
    page_icon="📊",
    layout="wide",
)

st.title("650-Email Evaluation")
st.write(
    "Run the frozen benchmark across the three experimental phases and compare "
    "where attacks are caught, missed, or incorrectly flagged."
)
st.caption(
    "The benchmark contains 150 genuine enquiries and 500 attacks "
    "(100 plain + 400 disguised variants)."
)

if not DATASET_PATH.exists():
    st.error("The benchmark CSV is not available in this checkout.")
    st.stop()

rows = _rows()

left, right, third = st.columns(3)
left.metric("Dataset cases", len(rows))
right.metric("Genuine enquiries", sum(row["label"] == "genuine" for row in rows))
third.metric("Attack cases", sum(row["label"] == "attack" for row in rows))

st.divider()
st.subheader("1. Screening comparison — all 650 emails")
st.write(
    "This runs every email through all three detector configurations. "
    "It makes no OpenAI calls and does not consume API credits."
)

if st.button(
    "Run all 650 across all 3 phases",
    type="primary",
    use_container_width=True,
):
    st.session_state["screening_results"] = _run_screening(rows)

screening_df = st.session_state.get("screening_results")
if screening_df is not None:
    summary_df = _summary(screening_df)

    st.subheader("Phase comparison")
    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Attack detection": st.column_config.ProgressColumn(
                "Attack detection",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
            "False-alarm rate": st.column_config.ProgressColumn(
                "False-alarm rate",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
            "Avg screening ms": st.column_config.NumberColumn(
                "Avg screening ms",
                format="%.3f",
            ),
        },
    )

    chart_data = summary_df.set_index("Phase")[
        ["Attacks flagged", "Attacks missed", "Genuine held"]
    ]
    st.bar_chart(chart_data)

    st.subheader("Detection by attack disguise")
    disguise_df = _disguise_summary(screening_df)
    st.dataframe(
        disguise_df.rename(
            columns={
                "phase": "Phase",
                "disguise": "Disguise",
                "total": "Total",
                "flagged": "Flagged",
                "missed": "Missed",
                "detection_rate": "Detection rate",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Detection rate": st.column_config.ProgressColumn(
                "Detection rate",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
        },
    )

    st.subheader("Inspect every result")
    phase_filter = st.selectbox(
        "Phase filter",
        ["All phases"] + list(PHASES),
        key="screen_phase_filter",
    )
    verdict_filter = st.selectbox(
        "Verdict filter",
        ["All verdicts", "pass", "review", "block"],
        key="screen_verdict_filter",
    )
    disguise_filter = st.selectbox(
        "Disguise filter",
        ["All disguises"]
        + sorted(
            screening_df["disguise"].unique(),
            key=lambda value: DISGUISE_LABELS.get(value, value).lower(),
        ),
        format_func=lambda value: (
            value if value == "All disguises"
            else DISGUISE_LABELS.get(value, value.replace("_", " ").title())
        ),
        key="screen_disguise_filter",
    )

    visible = screening_df.copy()
    if phase_filter != "All phases":
        visible = visible[visible["phase"] == phase_filter]
    if verdict_filter != "All verdicts":
        visible = visible[visible["verdict"] == verdict_filter]
    if disguise_filter != "All disguises":
        visible = visible[visible["disguise"] == disguise_filter]

    visible = visible.sort_values(["phase", "subject", "case_id"])
    st.dataframe(
        visible[
            [
                "phase",
                "case_id",
                "label",
                "disguise",
                "subject",
                "attack_goal",
                "verdict",
                "reason",
                "evidence",
                "screening_ms",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download screening comparison CSV",
        data=screening_df.to_csv(index=False).encode("utf-8"),
        file_name="screening_comparison_650_x_3.csv",
        mime="text/csv",
    )

st.divider()
st.subheader("2. Full end-to-end replay")
st.write(
    "This also runs drafting and output checks. Use the offline mock first to verify "
    "the pipeline without API cost. The OpenAI option uses the fixed fictional policy "
    "for the formal benchmark."
)

provider = st.selectbox(
    "Drafting provider",
    ["Offline mock — no API cost", "OpenAI fixed-policy model"],
)

if provider == "OpenAI fixed-policy model":
    st.warning(
        "A complete 650 × 3 replay can make a large number of API calls and consume "
        "credits. Run the no-cost comparison and offline replay first."
    )
    confirm_paid = st.checkbox(
        "I understand that this full replay can consume OpenAI API credits."
    )
else:
    confirm_paid = True

if st.button(
    "Run full 650-email replay",
    disabled=not confirm_paid,
    use_container_width=True,
):
    try:
        st.session_state["full_results"] = _run_full_pipeline(rows, provider)
        st.session_state["full_provider"] = provider
    except RuntimeError as exc:
        st.error(str(exc))

full_df = st.session_state.get("full_results")
if full_df is not None:
    st.caption(
        f"Last full replay provider: {st.session_state.get('full_provider', 'unknown')}"
    )

    full_summary = (
        full_df.groupby("phase", as_index=False)
        .agg(
            total=("case_id", "count"),
            drafts_created=("draft_created", "sum"),
            held_or_blocked=("verdict", lambda values: sum(v in ("review", "block") for v in values)),
            avg_duration_ms=("duration_ms", "mean"),
        )
    )
    st.dataframe(full_summary, use_container_width=True, hide_index=True)

    st.subheader("Full replay case results")
    st.dataframe(
        full_df.sort_values(["phase", "subject", "case_id"]),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download full replay CSV",
        data=full_df.to_csv(index=False).encode("utf-8"),
        file_name="full_replay_650_x_3.csv",
        mime="text/csv",
    )

st.info(
    "For the formal report, do not treat the offline mock replay as model-robustness "
    "evidence. Use the fixed OpenAI model/settings for measured drafting results, and "
    "record failures, costs, and bypasses."
)
