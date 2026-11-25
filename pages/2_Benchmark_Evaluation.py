"""Interactive benchmark dashboard for the 650-email evaluation set."""

from __future__ import annotations

import os
from pathlib import Path
import time
import tomllib

import pandas as pd
import streamlit as st

from email_assistant.drafting import DEFAULT_WEB_MODEL, OpenAIDrafter
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
    summary_rows = []

    for phase_name in PHASES:
        part = screening_df[screening_df["phase"] == phase_name]
        attack_total = int((part["label"] == "attack").sum())
        genuine_total = int((part["label"] == "genuine").sum())
        attack_flagged = int(part["attack_flagged"].sum())
        missed = int(part["missed_attack"].sum())
        false_alarms = int(part["false_alarm"].sum())

        summary_rows.append(
            {
                "Phase": phase_name,
                "Attacks flagged": attack_flagged,
                "Attacks missed": missed,
                "Attack detection": (
                    100 * attack_flagged / attack_total if attack_total else 0
                ),
                "Genuine held": false_alarms,
                "Genuine passed": genuine_total - false_alarms,
                "False-alarm rate": (
                    100 * false_alarms / genuine_total if genuine_total else 0
                ),
                "Avg screening ms": part["screening_ms"].mean(),
            }
        )

    return pd.DataFrame(summary_rows)


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
        lambda value: DISGUISE_LABELS.get(
            value,
            value.replace("_", " ").title(),
        )
    )

    return grouped


def _balanced_sample(rows: list[dict], sample_size: int) -> list[dict]:
    """Fixed, deterministic sample covering genuine mail and every disguise."""
    groups = [
        "genuine",
        "plain",
        "hidden_html",
        "base64",
        "zero_width",
        "lookalike",
    ]
    buckets: dict[str, list[dict]] = {}

    for group in groups:
        if group == "genuine":
            bucket = [
                row for row in rows
                if row["label"] == "genuine"
            ]
        else:
            bucket = [
                row for row in rows
                if row["label"] == "attack"
                and row["disguise"] == group
            ]

        buckets[group] = sorted(
            bucket,
            key=lambda row: (
                row["attack_goal"],
                row["topic"],
                row["subject"],
                row["case_id"],
            ),
        )

    selected: list[dict] = []
    base_quota, remainder = divmod(sample_size, len(groups))

    for index, group in enumerate(groups):
        quota = base_quota + (1 if index < remainder else 0)
        selected.extend(buckets[group][:quota])

    return sorted(
        selected,
        key=lambda row: (
            0 if row["label"] == "genuine" else 1,
            row["disguise"],
            row["subject"],
            row["case_id"],
        ),
    )


class _CountingDrafter:
    """Count actual model calls without changing the production drafter."""

    def __init__(self, drafter):
        self.drafter = drafter
        self.name = drafter.name
        self.requires_policy_text = getattr(drafter, "requires_policy_text", True)
        self.enforce_policy_facts = getattr(drafter, "enforce_policy_facts", True)
        self.api_calls = 0

    def generate(self, message, policy_text):
        self.api_calls += 1
        return self.drafter.generate(message, policy_text)


def _build_drafter():
    if not _configure_openai():
        raise RuntimeError("OpenAI API key is not configured")

    model = os.getenv("OPENAI_MODEL") or DEFAULT_WEB_MODEL
    return _CountingDrafter(OpenAIDrafter(model=model))


def _run_sample_batch(
    batch_rows: list[dict],
) -> list[dict]:
    """Run one small OpenAI batch through all three phases."""
    policy = _policy_text()
    drafter = _build_drafter()
    records: list[dict] = []

    total_runs = len(batch_rows) * len(PHASES)
    progress = st.progress(0, text="Running this batch...")
    completed = 0

    for row in batch_rows:
        for phase_name, config in PHASES.items():
            started = time.perf_counter()

            calls_before = drafter.api_calls

            result = process_message(
                _message(row),
                detector=config["detector"],
                drafter=drafter,
                policy_text=policy,
                output_check=config["output_check"],
                audit=False,
            )

            api_called = drafter.api_calls > calls_before
            elapsed_ms = (time.perf_counter() - started) * 1000
            is_attack = row["label"] == "attack"
            held = result.verdict in ("review", "block")

            records.append(
                {
                    "phase": phase_name,
                    "case_id": row["case_id"],
                    "label": row["label"],
                    "disguise": DISGUISE_LABELS.get(
                        row["disguise"],
                        row["disguise"],
                    ),
                    "topic": row["topic"],
                    "subject": row["subject"],
                    "attack_goal": row["attack_goal"],
                    "verdict": result.verdict,
                    "attack_caught": is_attack and held,
                    "attack_missed": is_attack and not held,
                    "genuine_held": (not is_attack) and held,
                    "draft_created": bool(result.draft),
                    "api_called": api_called,
                    "provider": result.provider,
                    "reason": result.reason,
                    "duration_ms": elapsed_ms,
                    "draft": result.draft or "",
                }
            )

            completed += 1
            progress.progress(
                completed / total_runs,
                text=(
                    f"Completed {completed} of {total_runs} "
                    "phase/case runs in this batch"
                ),
            )

    progress.empty()
    return records


def _partial_replay_summary(results_df: pd.DataFrame) -> pd.DataFrame:
    summary_rows = []

    for phase_name in PHASES:
        part = results_df[results_df["phase"] == phase_name]
        attacks = part[part["label"] == "attack"]
        genuine = part[part["label"] == "genuine"]

        caught = (
            int(attacks["attack_caught"].sum())
            if not attacks.empty
            else 0
        )
        missed = (
            int(attacks["attack_missed"].sum())
            if not attacks.empty
            else 0
        )
        genuine_held = (
            int(genuine["genuine_held"].sum())
            if not genuine.empty
            else 0
        )

        summary_rows.append(
            {
                "Phase": phase_name,
                "Emails completed": len(part),
                "Attacks seen": len(attacks),
                "Attacks caught": caught,
                "Attacks missed": missed,
                "Attack catch rate": (
                    100 * caught / len(attacks)
                    if len(attacks)
                    else 0
                ),
                "Genuine seen": len(genuine),
                "Genuine held": genuine_held,
                "API calls attempted": (
                    int(part["api_called"].sum())
                    if not part.empty
                    else 0
                ),
                "Drafts created": (
                    int(part["draft_created"].sum())
                    if not part.empty
                    else 0
                ),
                "Avg duration ms": (
                    part["duration_ms"].mean()
                    if not part.empty
                    else 0
                ),
            }
        )

    return pd.DataFrame(summary_rows)


st.set_page_config(
    page_title="650-Email Evaluation",
    page_icon="📊",
    layout="wide",
)

st.title("650-Email Evaluation")
st.write(
    "Compare the three experimental phases using the frozen benchmark."
)
st.caption(
    "The benchmark contains 150 genuine enquiries and 500 attacks "
    "(100 plain + 400 disguised variants)."
)

if not DATASET_PATH.exists():
    st.error("The benchmark CSV is not available in this checkout.")
    st.stop()

rows = _rows()

left, middle, right = st.columns(3)
left.metric("Dataset cases", len(rows))
middle.metric(
    "Genuine enquiries",
    sum(row["label"] == "genuine" for row in rows),
)
right.metric(
    "Attack cases",
    sum(row["label"] == "attack" for row in rows),
)

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

    st.subheader("Inspect every screening result")

    filter_left, filter_middle, filter_right = st.columns(3)

    with filter_left:
        phase_filter = st.selectbox(
            "Phase filter",
            ["All phases"] + list(PHASES),
            key="screen_phase_filter",
        )

    with filter_middle:
        verdict_filter = st.selectbox(
            "Verdict filter",
            ["All verdicts", "pass", "review", "block"],
            key="screen_verdict_filter",
        )

    with filter_right:
        disguise_filter = st.selectbox(
            "Disguise filter",
            ["All disguises"]
            + sorted(
                screening_df["disguise"].unique(),
                key=lambda value: DISGUISE_LABELS.get(
                    value,
                    value,
                ).lower(),
            ),
            format_func=lambda value: (
                value
                if value == "All disguises"
                else DISGUISE_LABELS.get(
                    value,
                    value.replace("_", " ").title(),
                )
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

    visible = visible.sort_values(
        ["phase", "subject", "case_id"]
    )

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
st.subheader("2. Sampled end-to-end OpenAI replay")
st.write(
    "For real model/API testing, use a smaller fixed subset instead of sending all "
    "650 emails through all three phases."
)
st.caption(
    "The sample is deterministic and balanced across genuine mail, plain attacks, "
    "hidden HTML, Base64, invisible-character attacks, and Unicode look-alikes."
)

sample_size = st.selectbox(
    "Fixed sample size",
    [6, 12, 18, 30, 60],
    index=1,
    help=(
        "12 is a useful quick test: two cases from each of the six "
        "benchmark categories."
    ),
)

batch_size = st.selectbox(
    "Emails per batch",
    [1, 2, 3, 5, 10],
    index=2,
    help=(
        "Each selected email is replayed through all three phases. "
        "Choose 1 if you want to be able to stop after every email."
    ),
)

selected_sample = _balanced_sample(rows, sample_size)

with st.expander("Preview the fixed sample"):
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Category": DISGUISE_LABELS.get(
                        row["disguise"],
                        row["disguise"].replace("_", " ").title(),
                    ),
                    "Case ID": row["case_id"],
                    "Subject": row["subject"],
                    "Attack goal": row["attack_goal"],
                }
                for row in selected_sample
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

st.warning(
    f"A {sample_size}-email replay contains at most "
    f"{sample_size * 3} phase/case runs. Some attacks are stopped "
    "before drafting, so the actual number of API calls can be lower."
)

confirm_paid = st.checkbox(
    "I understand that OpenAI batches can consume API credits.",
    key="sampled_paid_confirm",
)

run_state = st.session_state.get("sampled_replay_state")

start_clicked = st.button(
    "Start / restart sampled replay",
    type="primary",
    disabled=not confirm_paid,
    use_container_width=True,
)

if start_clicked:
    st.session_state["sampled_replay_state"] = {
        "provider": "OpenAI fixed-policy model",
        "sample_size": sample_size,
        "sample_ids": [
            row["case_id"]
            for row in selected_sample
        ],
        "next_index": 0,
        "results": [],
        "stopped": False,
    }

    run_state = st.session_state["sampled_replay_state"]

if run_state is not None:
    row_by_id = {
        row["case_id"]: row
        for row in rows
    }

    run_rows = [
        row_by_id[case_id]
        for case_id in run_state["sample_ids"]
        if case_id in row_by_id
    ]

    completed_emails = int(run_state["next_index"])
    total_emails = len(run_rows)

    overall_fraction = (
        completed_emails / total_emails
        if total_emails
        else 0
    )

    st.progress(
        overall_fraction,
        text=(
            f"Overall progress: {completed_emails} of "
            f"{total_emails} emails completed "
            f"({completed_emails * 3} of "
            f"{total_emails * 3} phase/case runs)"
        ),
    )

    st.caption(
        f"Current run: {run_state['provider']} · "
        f"fixed sample of {run_state['sample_size']} emails"
    )

    if (
        run_state.get("stopped")
        and completed_emails < total_emails
    ):
        st.info(
            "This run is stopped. Everything completed so far is preserved below."
        )

    remaining = max(
        total_emails - completed_emails,
        0,
    )
    next_count = min(
        batch_size,
        remaining,
    )

    control_left, control_middle, control_right = st.columns(3)

    with control_left:
        run_next = st.button(
            f"Run next {next_count} email(s)",
            disabled=(
                run_state.get("stopped", False)
                or completed_emails >= total_emails
            ),
            use_container_width=True,
        )

    with control_middle:
        stop_here = st.button(
            "Stop here and keep results",
            disabled=(
                run_state.get("stopped", False)
                or completed_emails >= total_emails
            ),
            use_container_width=True,
        )

    with control_right:
        resume = st.button(
            "Resume",
            disabled=(
                not run_state.get("stopped", False)
                or completed_emails >= total_emails
            ),
            use_container_width=True,
        )

    if stop_here:
        run_state["stopped"] = True
        st.session_state["sampled_replay_state"] = run_state

    if resume:
        run_state["stopped"] = False
        st.session_state["sampled_replay_state"] = run_state

    if run_next or start_clicked:
        start = completed_emails
        end = min(
            start + batch_size,
            total_emails,
        )
        batch_rows = run_rows[start:end]

        try:
            new_records = _run_sample_batch(
                batch_rows,
            )

            run_state["results"].extend(
                new_records
            )
            run_state["next_index"] = end
            st.session_state["sampled_replay_state"] = run_state

        except RuntimeError as exc:
            st.error(str(exc))

    results = run_state.get("results", [])

    if results:
        sampled_df = pd.DataFrame(results)
        summary_df = _partial_replay_summary(
            sampled_df
        )

        st.subheader("Progress results")

        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Attack catch rate": st.column_config.ProgressColumn(
                    "Attack catch rate",
                    min_value=0.0,
                    max_value=100.0,
                    format="%.1f%%",
                ),
                "Avg duration ms": st.column_config.NumberColumn(
                    "Avg duration ms",
                    format="%.1f",
                ),
            },
        )

        attack_rows = sampled_df[
            sampled_df["label"] == "attack"
        ]

        metric_left, metric_middle, metric_right, metric_fourth = st.columns(4)

        metric_left.metric(
            "Attack phase-runs caught",
            int(
                attack_rows["attack_caught"].sum()
            ),
        )

        metric_middle.metric(
            "Attack phase-runs missed",
            int(
                attack_rows["attack_missed"].sum()
            ),
        )

        metric_right.metric(
            "API calls attempted",
            int(
                sampled_df["api_called"].sum()
            ),
        )

        metric_fourth.metric(
            "Drafts created",
            int(
                sampled_df["draft_created"].sum()
            ),
        )

        st.subheader("Completed case results")

        st.dataframe(
            sampled_df.sort_values(
                ["phase", "subject", "case_id"]
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download current partial results",
            data=sampled_df.to_csv(index=False).encode("utf-8"),
            file_name="sampled_replay_partial_results.csv",
            mime="text/csv",
        )

    if (
        run_state["next_index"] >= total_emails
        and total_emails
    ):
        st.success(
            "The sampled replay is complete."
        )

st.info(
    "You can stop only between batches, not in the middle of an active API request. "
    "Use a batch size of 1 for the finest control. For the formal report, record the "
    "sample size, exact case IDs, model/settings, and whether a run ended early."
)
