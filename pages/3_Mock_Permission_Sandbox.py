"""Interactive read-only COMP 3260 mock-permission experiment.

One evaluation per auto-rerun: stopping is effective between model requests,
not while an individual network request is in flight.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from email_assistant.permission_sandbox import (
    MODES, ScriptedProbeClient, choose_sample,
    create_openai_client, evaluate_case, summarize,
)
from generate_dataset import load_jsonl, read_policy, validate

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "university_email_650.jsonl"
POLICY = ROOT / "university_test_policy.json"

st.set_page_config(page_title="Mock Permission Sandbox", page_icon="🧪", layout="wide")
st.title("🧪 Mock Permission Sandbox")
st.caption(
    "Actual model tool requests (when OpenAI is selected) · "
    "Fictional actions only · No real side effects"
)
st.warning(
    "Use synthetic data only. The permissive mode is an intentionally unsafe "
    "lab condition, NOT a real authorization setting. None of the tools connects "
    "to TRU, external websites, student records or email delivery."
)

with st.expander("What the three conditions mean", expanded=False):
    st.markdown(
        "**A:** No prompt-injection detector, mock calls permitted (but never executed).  "
        "**B:** No detector, Amara's real allow/deny decision applied to mock calls.  "
        "**C:** Favour's full detector, Amara's authorization and Chinaza's draft-output checker. "
        "All three send the same fictional policy and tool catalogue to the model. "
        "They do not disable the model's own training or safety protections."
    )


@st.cache_data(show_spinner=False)
def _load_data():
    fixture = read_policy(POLICY)
    cases = load_jsonl(DATASET)
    validate(cases, fixture)
    return cases, fixture


def _load_secrets():
    # Local Streamlit secrets are gitignored; cloud deployment has private Secrets.
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        try:
            value = st.secrets.get(name)
        except Exception:
            value = None
        if value:
            os.environ[name] = str(value).strip()
    return bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


try:
    CASES, FIXTURE = _load_data()
except (OSError, TypeError, ValueError, KeyError) as exc:
    st.error(f"The frozen university dataset or its policy is invalid: {type(exc).__name__}")
    st.stop()

st.caption(f"Dataset: {len(CASES)} emails · Fictional policy: {FIXTURE['policy_id']}")

if "permission_sandbox_job" not in st.session_state:
    st.session_state["permission_sandbox_job"] = None

job = st.session_state["permission_sandbox_job"]
if job is None:
    st.subheader("1. Choose a sample and permission comparison")
    a, b, c = st.columns(3)
    provider = a.selectbox(
        "AI provider",
        ["Offline scripted probe (no API)", "OpenAI real model (billable)"],
        help="The offline probe is scripted, NOT evidence of real model behaviour.",
    )
    cohort = b.selectbox(
        "Cases to include",
        ["All emails", "Attack cases only", "Genuine emails only"],
    )
    seed = c.number_input(
        "Reproducible random seed", min_value=0, max_value=999999, value=650,
    )
    pool = [row for row in CASES if (
        cohort == "All emails" or
        (cohort == "Attack cases only" and row["label"] == "attack") or
        (cohort == "Genuine emails only" and row["label"] == "genuine")
    )]
    a, b, c = st.columns(3)
    sample_size = a.number_input(
        "SAMPLE_SIZE — maximum emails", min_value=1,
        max_value=len(pool), value=min(10, len(pool)), step=1,
    )
    batch_size = b.number_input(
        "BATCH_SIZE — emails per batch", min_value=1,
        max_value=min(50, len(pool)), value=min(5, len(pool)), step=1,
    )
    number_of_batches = c.number_input(
        "NUMBER_OF_BATCHES — run this many",
        min_value=1, max_value=650, value=2, step=1,
    )
    modes = st.multiselect(
        "Permission/screening conditions", list(MODES), default=list(MODES),
    )
    n_cases = min(int(sample_size), int(batch_size) * int(number_of_batches), len(pool))
    total = n_cases * len(modes)
    st.info(
        f"Planned sample: {n_cases} unique email(s) × {len(modes)} condition(s) "
        f"= **{total} evaluations** in up to "
        f"{(n_cases + int(batch_size) - 1) // int(batch_size)} batch(es)."
    )
    st.caption(
        "The same sampled emails are used in every selected condition. "
        "A fixed random seed makes repeated previews reproducible; these are "
        "development samples, not an unbiased final benchmark if you tune rules on them."
    )
    is_real = provider.startswith("OpenAI")
    authorized = True
    if is_real:
        ready = _load_secrets()
        st.warning(
            f"Real-model testing may make MORE than {total} billable API requests "
            "because function calls require follow-up responses. "
            "All inputs and records are fictional; check your account's budget."
        )
        authorized = st.checkbox(
            "I approve these billable, fictional tool-calling tests."
        ) and ready
        if not ready:
            st.error(
                "Configure OPENAI_API_KEY and OPENAI_MODEL in the server's private Secrets first."
            )
    else:
        st.caption(
            "Offline probe gives predictable mocked requests, not actual model decisions."
        )

    if st.button(
        "Start sandbox evaluation", type="primary",
        disabled=not (authorized and total > 0),
    ):
        selected = choose_sample(
            pool, sample_size=int(sample_size),
            batch_size=int(batch_size),
            number_of_batches=int(number_of_batches),
            seed=int(seed),
        )
        tasks = [(case, mode) for case in selected for mode in modes]
        st.session_state["permission_sandbox_job"] = {
            "status": "running", "tasks": tasks, "cursor": 0,
            "records": [], "errors_in_row": 0,
            "batch_size": int(batch_size),
            "provider": "openai" if is_real else "scripted_probe",
            "model": os.getenv("OPENAI_MODEL", "") if is_real
                     else "offline-scripted-probe",
            "sample_size": n_cases, "seed": int(seed), "modes": list(modes),
            "policy_id": FIXTURE["policy_id"],
            "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        st.rerun()
else:
    st.subheader("2. Progress and controls")


@st.fragment(
    run_every="1s" if job and job["status"] == "running" else None
)
def _workstation():
    job = st.session_state["permission_sandbox_job"]
    if not job:
        return
    total = len(job["tasks"])
    done = job["cursor"]
    st.progress(
        done / total, text=f"{done}/{total} completed condition/case evaluations",
    )
    st.caption(
        f"Status: **{job['status'].upper()}** · "
        f"Selected sample: {job['sample_size']} emails · "
        f"Batch size: {job['batch_size']} emails"
    )

    a, b, c = st.columns(3)
    if a.button(
        "Stop after current evaluation", disabled=job["status"] != "running",
    ):
        job["status"] = "paused"
        st.rerun()
    if b.button(
        "Resume remaining evaluations", disabled=job["status"] != "paused",
    ):
        job["status"] = "running"
        st.rerun()
    if c.button(
        "Clear run and start over", disabled=job["status"] == "running",
    ):
        st.session_state["permission_sandbox_job"] = None
        st.rerun()

    if job["status"] == "running" and done < total:
        case, mode = job["tasks"][done]
        try:
            if job["provider"] == "openai":
                _load_secrets()
                client, model = create_openai_client(model=job["model"])
            else:
                client, model = ScriptedProbeClient(), "offline-scripted-probe"
            record = evaluate_case(
                case, FIXTURE["approved_policy"], mode=mode,
                client=client, model=model, provider=job["provider"],
            )
        except Exception as exc:
            record = {
                "case_id": case["case_id"], "label": case["label"],
                "mode": mode, "provider": job["provider"],
                "outcome": "review", "error_type": type(exc).__name__,
                "reason": "Runner failed closed", "events": [],
                "tool_requests": 0, "api_calls": 0,
            }
        job["records"].append(record)
        job["cursor"] += 1
        job["errors_in_row"] = (
            job["errors_in_row"] + 1 if record.get("error_type") else 0
        )
        if job["errors_in_row"] >= 3:
            job["status"] = "paused"
        elif job["cursor"] >= total:
            job["status"] = "completed"

    records = job["records"]
    if records:
        st.write("**Results by condition**")
        st.dataframe(
            pd.DataFrame(summarize(records)), hide_index=True,
            use_container_width=True,
        )
        st.write("**Case-level results (most recent first)**")
        st.dataframe(
            pd.DataFrame([{
                "Case": r.get("case_id"), "Condition": r.get("mode"),
                "Label": r.get("label"), "Outcome": r.get("outcome"),
                "Tool requests": r.get("tool_requests", 0),
                "Approved (simulated)": r.get("simulated_allowed", 0),
                "Denied": r.get("denied", 0), "Error": r.get("error_type"),
            } for r in reversed(records[-100:])]),
            hide_index=True, use_container_width=True,
        )
        with st.expander(
            "Inspect a model action request and its authorization decision"
        ):
            with_events = [r for r in records if r.get("events")]
            if with_events:
                selected_case = st.selectbox(
                    "Evaluation", range(len(with_events)),
                    format_func=lambda i: (
                        f"{with_events[i]['case_id']} · {with_events[i]['mode']}"
                    ),
                )
                current = with_events[selected_case]
                for event in current["events"]:
                    st.json(event)
                st.text_area(
                    "Model's final unsent draft",
                    current.get("raw_model_reply_for_evaluator") or "",
                    height=135, disabled=True,
                )
            else:
                st.caption(
                    "No mock tool calls have been requested in completed cases."
                )
        st.divider()
        st.write("**Export results at any point, including after stopping**")
        st.download_button(
            "Download completed case results (.jsonl)",
            "".join(
                json.dumps(record, ensure_ascii=False) + "\n"
                for record in records
            ),
            file_name="permission_sandbox_results.jsonl",
            mime="application/x-ndjson",
        )
        event_rows = [
            {"case_id": record.get("case_id"), "mode": record.get("mode"), **event}
            for record in records for event in record.get("events", [])
        ]
        st.download_button(
            "Download mock authorization events (.json)",
            json.dumps(event_rows, ensure_ascii=False, indent=2),
            file_name="permission_sandbox_events.json",
            mime="application/json",
        )
        st.download_button(
            "Download summary and run settings (.json)",
            json.dumps({
                "summary": summarize(records),
                "run": {
                    key: value for key, value in job.items()
                    if key not in ("tasks", "records")
                },
                "limitations": [
                    "Only fictional mock operations were simulated; no real actions occurred.",
                    "Tool calls are model requests, not evidence of real record access.",
                    "Offline scripted probe is not a language model.",
                    "No-screening conditions do not turn off OpenAI safety training.",
                    "Stopped runs are partial; no claims about unprocessed cases.",
                ],
            }, ensure_ascii=False, indent=2),
            file_name="permission_sandbox_summary.json",
            mime="application/json",
        )
    if job["status"] == "paused" and job["errors_in_row"] >= 3:
        st.error(
            "Paused automatically after three consecutive failures "
            "to avoid extra API calls."
        )
    if job["status"] == "completed":
        st.success(
            "All selected evaluations are complete. "
            "This was a sandbox-only experiment."
        )


_workstation()
st.caption(
    "Stop takes effect between cases. An API request already in flight cannot "
    "be interrupted; keep the browser tab open. Session results persist only "
    "while this Streamlit session is active."
)
st.page_link(
    "streamlit_app.py", label="Return to main university email app", icon="⬅️",
)
