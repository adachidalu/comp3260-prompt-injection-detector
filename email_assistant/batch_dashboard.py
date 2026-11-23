"""Two browser views for Stanley's fixed university-email evaluation set.

Only UI concerns belong here. Generation, validation, detection and replay
remain in the team's existing modules. No real mailbox is connected.
"""
from __future__ import annotations

import csv
import io
import json
import os

import streamlit as st

from email_assistant.batch_runner import load_evaluation, run_batch
from email_assistant.drafting import MockDrafter, OpenAIDrafter
from email_assistant.pipeline import process_message
from email_assistant.screening import full_detector
from replay_university import CONFIGS, to_message


@st.cache_data(show_spinner=False)
def _dataset():
    return load_evaluation()


def _files_or_error():
    try:
        return _dataset()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Evaluation dataset is unavailable or invalid: {type(exc).__name__}: {exc}")
        return None, None


def _configure_openai():
    try:
        key = st.secrets.get("OPENAI_API_KEY")
        model = st.secrets.get("OPENAI_MODEL")
    except (OSError, KeyError, AttributeError, FileNotFoundError):
        key, model = None, None
    if key:
        os.environ["OPENAI_API_KEY"] = str(key)
    if model:
        os.environ["OPENAI_MODEL"] = str(model)


def _drafter(use_openai: bool):
    if not use_openai:
        return MockDrafter()
    _configure_openai()
    return OpenAIDrafter()


def render_explorer():
    st.subheader("Browse Stanley's 650 university emails")
    st.caption("Synthetic data, versioned with its fictional approved policy. "
               "Labels and expected answers are visible to reviewers, not sent to the AI.")
    cases, fixture = _files_or_error()
    if cases is None:
        return

    cols = st.columns(4)
    labels = ["All", "genuine", "attack"]
    label = cols[0].selectbox("Classification", labels)
    topic = cols[1].selectbox("Student topic", ["All", *sorted({c["topic"] for c in cases})])
    disguise = cols[2].selectbox("Attack presentation", ["All", *sorted({c["disguise"] for c in cases})])
    goal = cols[3].selectbox("Attack goal", ["All", *sorted({c["attack_goal"] for c in cases})])
    matches = [
        c for c in cases
        if (label == "All" or c["label"] == label)
        and (topic == "All" or c["topic"] == topic)
        and (disguise == "All" or c["disguise"] == disguise)
        and (goal == "All" or c["attack_goal"] == goal)
    ]
    st.caption(f"{len(matches)} of {len(cases)} cases match your filters")
    if not matches:
        st.warning("No matching cases. Change a filter to continue.")
        return
    by_id = {c["case_id"]: c for c in matches}
    selected_id = st.selectbox("Select an email", list(by_id),
                               format_func=lambda x: f"{x} | {by_id[x]['topic']} | {by_id[x]['subject']}")
    case = by_id[selected_id]
    st.write(f"**Subject:** {case['subject']}")
    st.caption(f"Case {selected_id} · {case['label']} · {case['disguise']} · "
               f"Goal: {case['attack_goal']} · Family: {case['base_attack_id'] or 'none'}")
    st.text_area("Student-visible email", case["visible_text"], height=145, disabled=True)
    with st.expander("Original email body / HTML for security inspection"):
        st.code(case["raw_body"], language="html" if case["content_type"] == "text/html" else "text")
    with st.expander("Approved fictional policy and expected answer"):
        st.code(fixture["approved_policy"], language="text")
        st.write(f"**Expected factual reference:** {case['expected_policy_anchor']}")

    provider = st.selectbox("Drafting provider for this email",
                            ["Offline mock (no API calls)", "OpenAI API (may incur charges)"],
                            key="explorer_provider")
    if st.button("Screen this email and prepare draft", type="primary"):
        try:
            drafter = _drafter(provider.startswith("OpenAI"))
            result = process_message(
                to_message(case),
                detector=full_detector,
                drafter=drafter,
                policy_text=fixture["approved_policy"],
                output_check=True,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            st.error(f"Draft provider could not start: {type(exc).__name__}: {exc}")
            return
        st.write(f"**Result: {result.verdict.upper()}** — {result.reason}")
        if result.evidence:
            st.code(result.evidence)
        if result.draft:
            st.text_area("Draft for staff review only", result.draft, height=160, disabled=True)
        else:
            st.info("No draft released. The email was held or blocked.")
        st.caption("This result is a test, not an email sent to a student.")


def _metrics_csv(summary: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "configuration", "cases", "attacks", "attacks_held",
        "missed_by_screening", "genuine", "genuine_held",
        "false_alarm_rate", "drafts_created", "processing_failures",
    ])
    writer.writeheader()
    for name, details in summary["configurations"].items():
        writer.writerow({"configuration": name, **{
            k: details.get(k) for k in writer.fieldnames if k != "configuration"
        }})
    return output.getvalue()


def _display_report(report: dict, records: list[dict]):
    st.success(f"Finished {report['completed_evaluations']} case/configuration evaluations.")
    if report["preview_only"]:
        st.warning("Preview or partial comparison. These results are not the full 650 × 3 evaluation.")
    table = []
    for name, value in report["configurations"].items():
        table.append({
            "Configuration": name,
            "Cases": value["cases"],
            "Attacks flagged": value["attacks_held"],
            "Attacks missed": value["missed_by_screening"],
            "Genuine held": value["genuine_held"],
            "Drafts": value["drafts_created"],
            "Failures": value["processing_failures"],
        })
    st.dataframe(table, hide_index=True, use_container_width=True)
    import pandas as pd
    chart_data = pd.DataFrame(table).set_index("Configuration")
    st.bar_chart(chart_data[["Attacks flagged", "Genuine held"]])
    st.caption("Attacks flagged is a screening metric, NOT proof of attack success or full "
               "security. The action-permission checker is not connected to this replay.")

    by_mode = st.selectbox("Detailed results for security mode",
                           list(report["configurations"]), key="batch_mode_details")
    disguise_rows = [
        {"Disguise": name, **value}
        for name, value in report["configurations"][by_mode]["by_disguise"].items()
    ]
    st.write("**Attack screening by disguise**")
    st.dataframe(disguise_rows, hide_index=True, use_container_width=True)
    st.write("**Individual evaluations — first 100 displayed**")
    visible = [r for r in records if r["configuration"] == by_mode]
    st.dataframe([
        {"Case": r["case_id"], "Topic": r["topic"], "Type": r["disguise"],
         "Label": r["label"], "Detector": r["detector_verdict"],
         "Final verdict": r["verdict"], "Draft": r["draft_created"],
         "Failure": bool(r["error"])}
        for r in visible[:100]
    ], hide_index=True, use_container_width=True)
    st.caption("Full individual results are available in the JSONL download.")

    st.download_button(
        "Download all case results (.jsonl)",
        data="".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        file_name="university_evaluation_results.jsonl",
        mime="application/x-ndjson",
    )
    st.download_button(
        "Download full summary (.json)",
        data=json.dumps(report, indent=2, ensure_ascii=False),
        file_name="university_evaluation_summary.json",
        mime="application/json",
    )
    st.download_button(
        "Download comparison table (.csv)",
        data=_metrics_csv(report),
        file_name="university_evaluation_metrics.csv",
        mime="text/csv",
    )


def render_batch():
    st.subheader("Run all 650 emails from the browser")
    st.caption("Uses Stanley's frozen synthetic dataset and the same replay() "
               "and summarize() methods as the command-line evaluator.")
    cases, policy = _files_or_error()
    if cases is None:
        return
    a, b, c = st.columns(3)
    case_count = a.selectbox("Emails per configuration", [10, 26, 100, 650], index=3)
    mode_label = b.selectbox(
        "Security comparison",
        ["All three modes", *CONFIGS.keys()],
    )
    config_names = tuple(CONFIGS) if mode_label == "All three modes" else (mode_label,)
    provider = c.selectbox("Drafting provider", [
        "Offline mock (recommended)", "OpenAI API (billable)"], key="batch_provider")
    use_openai = provider.startswith("OpenAI")
    total = case_count * len(config_names)
    st.info(f"Selected: {case_count} emails × {len(config_names)} configuration(s) "
            f"= {total} evaluations.")
    st.caption("The dataset is fixed and shuffled; previews use its first N cases and "
               "are not representative samples.")
    authorized = True
    if use_openai:
        st.warning(f"This can make up to {total} billable model calls; each call may take time. "
                   "Only fictional examples are used. API keys must stay private.")
        authorized = st.checkbox("I authorize these billable test calls with fictional data.")

    if st.button("Run evaluation", type="primary", disabled=not authorized):
        try:
            drafter = _drafter(use_openai)
            progress_bar = st.progress(0, text="Starting evaluation...")
            def on_progress(done: int, count: int, mode: str):
                progress_bar.progress(done / count, text=f"{done}/{count} evaluations · {mode}")

            records, report = run_batch(
                cases, policy, drafter, config_names=config_names,
                case_count=case_count, progress=on_progress,
            )
            st.session_state["stanley_batch_report"] = report
            st.session_state["stanley_batch_records"] = records
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            st.error(f"Batch run did not complete: {type(exc).__name__}: {exc}")
            return

    report = st.session_state.get("stanley_batch_report")
    records = st.session_state.get("stanley_batch_records")
    if report and records:
        _display_report(report, records)
    else:
        st.caption("No completed batch run yet. Select your settings and click Run evaluation.")
