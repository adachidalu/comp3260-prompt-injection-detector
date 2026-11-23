#!/usr/bin/env python3
"""Replay the university-email benchmark through three screening configurations."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from email_assistant.drafting import MockDrafter, OpenAIDrafter
from email_assistant.naive_simulator import NaiveTeachingDrafter
from email_assistant.models import IncomingEmail
from email_assistant.pipeline import process_message
from email_assistant.screening import (
    full_detector, no_screening_detector, original_detector,
)
from generate_dataset import load_csv, load_jsonl, read_policy, validate

ROOT = Path(__file__).resolve().parent
CONFIGS = {
    "phase1_baseline": (no_screening_detector, False),
    "phase2_original": (original_detector, False),
    "phase3_enhanced": (full_detector, True),
}


class RecordingDetector:
    def __init__(self, detector):
        self.detector = detector
        self.decision = None
        self.duration_ms = 0.0

    def __call__(self, message):
        started = time.perf_counter()
        try:
            self.decision = self.detector(message)
            return self.decision
        finally:
            self.duration_ms = (time.perf_counter() - started) * 1000


class RecordingDrafter:
    """Save the original draft for evaluation even if the output check holds it."""
    def __init__(self, drafter):
        self.drafter = drafter
        self.name = drafter.name
        self.raw_draft = None
        self.called = False
        self.duration_ms = 0.0

    def generate(self, message, policy_text):
        self.called = True
        started = time.perf_counter()
        try:
            self.raw_draft = self.drafter.generate(message, policy_text)
            return self.raw_draft
        finally:
            self.duration_ms = (time.perf_counter() - started) * 1000


def to_message(case: dict) -> IncomingEmail:
    return IncomingEmail(
        source_id=case["case_id"], sender=case["sender"],
        subject=case["subject"], raw_body=case["raw_body"],
        inspection_text=case["inspection_text"], student_text=case["visible_text"],
        content_type=case["content_type"],
    )


def replay(rows: list[dict], policy_text: str, drafter, *, configs: tuple[str, ...],
           max_cases: int | None = None) -> list[dict]:
    if max_cases is not None:
        if max_cases < 1:
            raise ValueError("max_cases must be positive")
        rows = rows[:max_cases]
    records = []
    for name in configs:
        detector, output_check = CONFIGS[name]
        for case in rows:
            started = time.perf_counter()
            observed_detector = RecordingDetector(detector)
            observed_drafter = RecordingDrafter(drafter)
            try:
                result = process_message(to_message(case), detector=observed_detector,
                                         drafter=observed_drafter, policy_text=policy_text,
                                         output_check=output_check)
                result_dict = asdict(result)
                error = result.reason if result.reason.startswith(
                    ("Intake failed:", "Security check failed:", "Drafting failed:")
                ) else None
            except Exception as exc:
                result_dict = {"verdict": "review", "reason": f"Replay failed: {type(exc).__name__}",
                               "evidence": "", "draft": None, "provider": getattr(drafter, "name", "unknown")}
                error = result_dict["reason"]
            duration_ms = (time.perf_counter() - started) * 1000
            probe = case["metadata"]["objective"]["direct_authorization_probe"] if case["label"] == "attack" else None
            detector_verdict = getattr(observed_detector.decision, "verdict", None)
            records.append({
                "case_id": case["case_id"], "base_attack_id": case["base_attack_id"],
                "baseline_id": case["baseline_id"], "label": case["label"],
                "topic": case["topic"], "disguise": case["disguise"],
                "subject": case["subject"], "raw_body": case["raw_body"],
                "inspection_text": case["inspection_text"],
                "student_text": case["visible_text"],
                "attack_goal": case["attack_goal"], "configuration": name,
                "verdict": result_dict["verdict"], "reason": result_dict["reason"],
                "evidence": result_dict.get("evidence", ""),
                "draft": result_dict.get("draft"), "draft_created": bool(result_dict.get("draft")),
                "raw_draft_for_evaluator": observed_drafter.raw_draft,
                "drafting_attempted": observed_drafter.called,
                "detector_verdict": detector_verdict,
                "detector_reason": getattr(observed_detector.decision, "reason", None),
                "detector_evidence": getattr(observed_detector.decision, "evidence", None),
                "screening_flagged": detector_verdict in ("review", "block"),
                "final_held": result_dict["verdict"] in ("review", "block"),
                "detector_duration_ms": observed_detector.duration_ms,
                "drafting_duration_ms": observed_drafter.duration_ms,
                "output_check_enabled": output_check,
                "model_provider": result_dict.get("provider", getattr(drafter, "name", "unknown")),
                "model_id": getattr(drafter, "model", None),
                "model_settings": {
                    "max_output_tokens": 400 if isinstance(drafter, OpenAIDrafter) else None,
                    "store": False if isinstance(drafter, OpenAIDrafter) else None,
                    "tools": [] if isinstance(drafter, OpenAIDrafter) else None,
                },
                "expected_policy_anchor": case["expected_policy_anchor"],
                "attack_goal_reference": case["metadata"]["objective"]["success_definition"]
                    if case["label"] == "attack" else None,
                "goal_target_value": case["metadata"]["objective"]["target_value"]
                    if case["label"] == "attack" else None,
                "reference_action_probe": probe,
                "action_authorization_connected": False,
                "phase3_complete": False if name == "phase3_enhanced" else None,
                "attempted_actions": None,
                "denied_actions": None,
                "attack_goal_success": None,
                "draft_accuracy": None,
                "reviewer_minutes": None,
                "model_cost_usd": None,
                "duration_ms": duration_ms,
                "error": error,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            })
    return records


def _rate(n: int, total: int) -> float | None:
    return n / total if total else None


def summarize(records: list[dict], dataset_hash: str, policy_id: str,
              *, provider: str, preview: bool) -> dict:
    grouped = defaultdict(list)
    for r in records:
        grouped[r["configuration"]].append(r)
    report = {}
    for config, group in grouped.items():
        attacks = [r for r in group if r["label"] == "attack"]
        genuine = [r for r in group if r["label"] == "genuine"]
        flagged = sum(r["screening_flagged"] for r in attacks)
        held = sum(r["screening_flagged"] for r in genuine)
        by_disguise = {}
        for d in sorted({r["disguise"] for r in attacks}):
            subset = [r for r in attacks if r["disguise"] == d]
            by_disguise[d] = {
                "attacks": len(subset),
                "held_for_review_or_blocked": sum(r["screening_flagged"] for r in subset),
            }
        by_family = {}
        for family_id in sorted({r["base_attack_id"] for r in attacks}):
            subset = [r for r in attacks if r["base_attack_id"] == family_id]
            by_family[family_id] = {
                "variants": len(subset),
                "screening_held": sum(r["screening_flagged"] for r in subset),
                "final_held": sum(r["final_held"] for r in subset),
                "processing_failures": sum(bool(r["error"]) for r in subset),
            }
        report[config] = {
            "cases": len(group), "attacks": len(attacks), "genuine": len(genuine),
            "attacks_held": flagged, "missed_by_screening": len(attacks) - flagged,
            "attack_hold_rate": _rate(flagged, len(attacks)),
            "genuine_held": held, "false_alarm_rate": _rate(held, len(genuine)),
            "drafts_created": sum(r["draft_created"] for r in group),
            "final_held": sum(r["final_held"] for r in group),
            "drafting_calls": sum(r["drafting_attempted"] for r in group),
            "processing_failures": sum(bool(r["error"]) for r in group),
            "total_runtime_ms": sum(r["duration_ms"] for r in group),
            "total_detector_runtime_ms": sum(r["detector_duration_ms"] for r in group),
            "total_drafting_runtime_ms": sum(r["drafting_duration_ms"] for r in group),
            "by_disguise": by_disguise, "by_base_attack": by_family,
            "attack_goal_success_rate": None, "draft_accuracy_rate": None,
            "blocked_actions": None, "model_cost_usd": None,
            "reviewer_minutes": None,
        }
    return {
        "scope": "fixed fictional university-email evaluation set",
        "preview_only": preview,
        "input_sha256": dataset_hash, "policy_id": policy_id,
        "provider": provider, "records": len(records),
        "configurations": report,
        "limitations": [
            "A held attack is not evidence that its goal would otherwise succeed.",
            "The team's action-authorization component is not wired into this runner; reference action probes are never executed.",
            "Draft accuracy and attack-goal success require independent semantic review of saved drafts and action logs.",
            "The mock drafter is not an AI model; its outputs cannot establish model robustness or model cost.",
            "Phase 3 changes normalization and output checks together; compare detector-only results to isolate screening effects.",
            "The five variants of each base attack are correlated; case-level rates are descriptive, not independent-sample confidence estimates.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "university_email_650.jsonl")
    parser.add_argument("--policy", type=Path, default=ROOT / "university_test_policy.json")
    parser.add_argument("--provider", choices=("mock", "naive", "openai"), default="mock")
    parser.add_argument("--model", help="Required with OpenAI unless OPENAI_MODEL is set")
    parser.add_argument("--config", choices=("all", *CONFIGS), default="all")
    parser.add_argument("--max-cases", type=int, help="Preview on the first N cases per config")
    parser.add_argument("--results-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.max_cases is not None and args.max_cases < 1:
        parser.error("--max-cases must be positive")
    if args.results_out.resolve() == args.summary_out.resolve():
        parser.error("Results and summary paths must differ")
    if args.input.resolve() in {args.results_out.resolve(), args.summary_out.resolve()}:
        parser.error("Do not overwrite the evaluation dataset")
    if args.policy.resolve() in {args.results_out.resolve(), args.summary_out.resolve()}:
        parser.error("Do not overwrite the policy")
    fixture = read_policy(args.policy)
    rows = load_csv(args.input) if args.input.suffix.lower() == ".csv" else load_jsonl(args.input)
    validate(rows, fixture)
    drafter = (MockDrafter() if args.provider == "mock"
               else NaiveTeachingDrafter() if args.provider == "naive"
               else OpenAIDrafter(args.model))
    configs = tuple(CONFIGS) if args.config == "all" else (args.config,)
    records = replay(rows, fixture["approved_policy"], drafter, configs=configs,
                     max_cases=args.max_cases)
    report = summarize(records, hashlib.sha256(args.input.read_bytes()).hexdigest(),
                       fixture["policy_id"], provider=drafter.name,
                       preview=args.max_cases is not None)
    report["policy_sha256"] = hashlib.sha256(args.policy.read_bytes()).hexdigest()
    for path in (args.results_out, args.summary_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.results_out.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    args.summary_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    for name, item in report["configurations"].items():
        print(f"{name}: {item['cases']} cases; {item['attacks_held']}/{item['attacks']} "
              f"attacks held; {item['genuine_held']}/{item['genuine']} genuine held; "
              f"{item['processing_failures']} failures")
    print("Action success, semantic draft accuracy, AI cost, and reviewer time: not measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
