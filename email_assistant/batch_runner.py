"""Reusable, deterministic Streamlit-friendly runner for Stanley's fixed dataset.

Uses the exact pipeline and scoring implementation in replay_university.py.
No automatic email sending, tool calls, or access to real student records.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from generate_dataset import load_jsonl, read_policy, validate
from replay_university import CONFIGS, replay, summarize

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "university_email_650.jsonl"
POLICY_PATH = ROOT / "university_test_policy.json"
CHUNK_SIZE = 25
ProgressCallback = Callable[[int, int, str], None]


def load_evaluation():
    """Load and validate one paired dataset/policy version."""
    policy = read_policy(POLICY_PATH)
    cases = load_jsonl(DATASET_PATH)
    validate(cases, policy)
    return cases, policy


def run_batch(cases: list[dict], policy: dict, drafter, *,
              config_names: tuple[str, ...] = tuple(CONFIGS),
              case_count: int | None = None,
              progress: ProgressCallback | None = None):
    """Run selected cases for each mode with incremental UI progress updates.

    The first N are a smoke preview, not an independent random sample.
    Pass only already-validated case records and the paired policy fixture.
    """
    if not cases:
        raise ValueError("No email cases supplied")
    if not config_names or len(set(config_names)) != len(config_names):
        raise ValueError("Select at least one distinct evaluation configuration")
    if any(name not in CONFIGS for name in config_names):
        raise ValueError("Unknown evaluation configuration")
    if case_count is None:
        case_count = len(cases)
    if not 1 <= case_count <= len(cases):
        raise ValueError("Case count must be between 1 and the dataset size")
    if not isinstance(policy.get("approved_policy"), str) or not policy["approved_policy"].strip():
        raise ValueError("Approved fictional policy is missing")

    selected = cases[:case_count]
    total = case_count * len(config_names)
    completed = 0
    records: list[dict] = []
    for name in config_names:
        for index in range(0, case_count, CHUNK_SIZE):
            batch = selected[index:index + CHUNK_SIZE]
            records.extend(replay(batch, policy["approved_policy"], drafter, configs=(name,)))
            completed += len(batch)
            if progress:
                progress(completed, total, name)

    if len(records) != total:
        raise RuntimeError("Incomplete evaluation: expected result rows not produced")
    preview = case_count != len(cases) or set(config_names) != set(CONFIGS)
    report = summarize(
        records, hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(),
        policy["policy_id"], provider=drafter.name, preview=preview,
    )
    report["policy_sha256"] = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    report["completed_evaluations"] = completed
    report["selected_case_count"] = case_count
    report["chosen_configurations"] = list(config_names)
    report["ui_source"] = "streamlit_batch_dashboard"
    return records, report
