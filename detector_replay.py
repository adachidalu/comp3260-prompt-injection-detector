"""Replay labelled synthetic email cases through detector configurations.

This script evaluates the DETECTOR workstream only. It reports screening
decisions, misses, false alarms, processing failures, and screening time.

It deliberately does not invent:
- AI drafting cost
- reviewer minutes
- draft accuracy
- action-checker denials
- attack-goal success after drafting/actions

Those values must come from the corresponding integrated team components.

Examples, run from the directory above the package:

    python -m favour_detector_lesson1.generate_detector_pilot

    python -m favour_detector_lesson1.detector_replay \
        --csv favour_detector_lesson1/development_pilot_26.csv \
        --expected-count 26

Later, with the correctly labelled 650-email university dataset:

    python -m favour_detector_lesson1.detector_replay \
        --csv path/to/university_email_650.csv \
        --expected-count 650
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean
import time

from .models import IncomingEmail, ScreeningDecision
from .screening import (
    full_detector,
    no_screening_detector,
    original_detector,
)


CONFIGURATIONS = {
    "none": no_screening_detector,
    "original": original_detector,
    "full": full_detector,
}

REQUIRED_COLUMNS = {
    "case_id",
    "label",
    "disguise",
    "subject",
    "content_type",
    "raw_body",
    "inspection_text",
    "visible_text",
}

VALID_LABELS = {"genuine", "attack"}


def load_cases(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                "CSV is missing required columns: " + ", ".join(sorted(missing))
            )

        rows = list(reader)

    seen = set()
    for index, row in enumerate(rows, start=2):
        case_id = (row.get("case_id") or "").strip()
        label = (row.get("label") or "").strip().lower()
        disguise = (row.get("disguise") or "").strip().lower()

        if not case_id:
            raise ValueError(f"CSV row {index} has no case_id")
        if case_id in seen:
            raise ValueError(f"Duplicate case_id: {case_id}")
        seen.add(case_id)

        if label not in VALID_LABELS:
            raise ValueError(
                f"{case_id}: label must be genuine or attack, got {label!r}"
            )
        if not disguise:
            raise ValueError(f"{case_id}: disguise is required")

        row["case_id"] = case_id
        row["label"] = label
        row["disguise"] = disguise
        row["base_attack_id"] = (row.get("base_attack_id") or "").strip()

    return rows


def to_message(row: dict) -> IncomingEmail:
    return IncomingEmail(
        source_id=row["case_id"],
        sender="synthetic-evaluation@example.test",
        subject=row.get("subject") or "(no subject)",
        raw_body=row.get("raw_body") or "",
        inspection_text=row.get("inspection_text") or "",
        student_text=row.get("visible_text") or "",
        content_type=row.get("content_type") or "text/plain",
    )


def run_one(row: dict, config_name: str) -> dict:
    detector = CONFIGURATIONS[config_name]
    message = to_message(row)

    started = time.perf_counter()
    failure = ""
    try:
        decision = detector(message)
        if decision.verdict not in {"pass", "review", "block"}:
            raise ValueError(f"invalid verdict {decision.verdict!r}")
    except Exception as exc:
        # Match the team's fail-closed pipeline behavior.
        decision = ScreeningDecision(
            "review",
            f"Detector failed: {type(exc).__name__}",
            "",
        )
        failure = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    flagged = decision.verdict != "pass"
    expected_flagged = row["label"] == "attack"

    return {
        "case_id": row["case_id"],
        "base_attack_id": row.get("base_attack_id", ""),
        "label": row["label"],
        "disguise": row["disguise"],
        "configuration": config_name,
        "verdict": decision.verdict,
        "flagged": flagged,
        "expected_flagged": expected_flagged,
        "correct_screening": flagged == expected_flagged,
        "reason": decision.reason,
        "evidence": decision.evidence,
        "screening_seconds": elapsed,
        "processing_failure": bool(failure),
        "failure": failure,
        # Useful for the integrated replay owner: a PASS is eligible to reach
        # drafting, but this detector-only script does not call a model.
        "drafting_eligible": decision.verdict == "pass",
    }


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _group_attack_metrics(results: list[dict], key: str) -> dict:
    groups: dict[str, dict] = {}
    attack_results = [r for r in results if r["label"] == "attack"]

    for result in attack_results:
        name = result.get(key) or "(none)"
        bucket = groups.setdefault(
            name,
            {
                "attacks": 0,
                "flagged": 0,
                "missed": 0,
                "processing_failures": 0,
            },
        )
        bucket["attacks"] += 1
        if result["flagged"]:
            bucket["flagged"] += 1
        else:
            bucket["missed"] += 1
        if result["processing_failure"]:
            bucket["processing_failures"] += 1

    for bucket in groups.values():
        bucket["detection_rate"] = _safe_rate(
            bucket["flagged"],
            bucket["attacks"],
        )

    return dict(sorted(groups.items()))


def summarize(results: list[dict], config_name: str) -> dict:
    config_results = [r for r in results if r["configuration"] == config_name]
    attacks = [r for r in config_results if r["label"] == "attack"]
    genuine = [r for r in config_results if r["label"] == "genuine"]

    flagged_attacks = sum(r["flagged"] for r in attacks)
    missed_attacks = len(attacks) - flagged_attacks
    genuine_held = sum(r["flagged"] for r in genuine)
    failures = sum(r["processing_failure"] for r in config_results)
    times = [r["screening_seconds"] for r in config_results]

    return {
        "configuration": config_name,
        "total_cases": len(config_results),
        "processing_failures": failures,
        "attacks": len(attacks),
        "flagged_attacks": flagged_attacks,
        "missed_attacks": missed_attacks,
        "attack_detection_rate": _safe_rate(flagged_attacks, len(attacks)),
        "genuine": len(genuine),
        "genuine_held": genuine_held,
        "false_alarm_rate": _safe_rate(genuine_held, len(genuine)),
        "drafting_eligible_cases": sum(
            r["drafting_eligible"] for r in config_results
        ),
        "total_screening_seconds": sum(times),
        "average_screening_ms": mean(times) * 1000 if times else 0.0,
        "attacks_by_disguise": _group_attack_metrics(
            config_results,
            "disguise",
        ),
        "attacks_by_base_attack": _group_attack_metrics(
            config_results,
            "base_attack_id",
        ),
        "team_metrics_pending": {
            "accurate_drafts": None,
            "drafting_cost_usd": None,
            "reviewer_minutes": None,
            "attack_goal_success": None,
            "action_denials": None,
        },
    }


def write_results(path: Path, results: list[dict]) -> None:
    fields = [
        "case_id",
        "base_attack_id",
        "label",
        "disguise",
        "configuration",
        "verdict",
        "flagged",
        "expected_flagged",
        "correct_screening",
        "reason",
        "evidence",
        "screening_seconds",
        "processing_failure",
        "failure",
        "drafting_eligible",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay labelled synthetic emails through detector modes"
    )
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument(
        "--config",
        choices=["all", "none", "original", "full"],
        default="all",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Fail if the input does not contain exactly this many cases",
    )
    parser.add_argument("--results-out", type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    rows = load_cases(args.csv)

    if args.expected_count is not None and len(rows) != args.expected_count:
        raise SystemExit(
            f"Expected {args.expected_count} cases but CSV contains {len(rows)}"
        )

    configs = (
        list(CONFIGURATIONS)
        if args.config == "all"
        else [args.config]
    )

    results = [
        run_one(row, config_name)
        for config_name in configs
        for row in rows
    ]

    results_out = args.results_out or args.csv.with_name(
        args.csv.stem + "_detector_results.csv"
    )
    summary_out = args.summary_out or args.csv.with_name(
        args.csv.stem + "_detector_summary.json"
    )

    write_results(results_out, results)

    summary = {
        "source_csv": str(args.csv),
        "input_cases": len(rows),
        "configurations": {
            config_name: summarize(results, config_name)
            for config_name in configs
        },
        "scope_note": (
            "Detector-only replay. Team integration must supply draft accuracy, "
            "AI cost, reviewer minutes, action-denial results, and attack-goal "
            "success."
        ),
    }

    summary_out.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Loaded {len(rows)} cases from {args.csv}")
    for config_name in configs:
        item = summary["configurations"][config_name]
        print(
            f"{config_name}: attacks flagged "
            f"{item['flagged_attacks']}/{item['attacks']} | "
            f"missed={item['missed_attacks']} | "
            f"genuine held={item['genuine_held']}/{item['genuine']} | "
            f"failures={item['processing_failures']} | "
            f"avg screening={item['average_screening_ms']:.3f} ms"
        )

    print(f"Results: {results_out}")
    print(f"Summary: {summary_out}")


if __name__ == "__main__":
    main()
