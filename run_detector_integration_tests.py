"""End-to-end development checks for the detector through real .eml intake.

Run from the directory above the package:
    python -m favour_detector_lesson1.run_detector_integration_tests
"""
from pathlib import Path

from .ingest import parse_eml
from .screening import full_detector


INBOX = Path(__file__).resolve().parent / "integration_test"

EXPECTED = {
    "genuine.eml": "pass",
    "plain_attack.eml": "review",
    "hidden_attack.eml": "review",
    "base64_attack.eml": "review",
    "zero_width_attack.eml": "review",
    "lookalike_attack.eml": "review",
    "private_record_attack.eml": "block",
}


def main() -> None:
    failures = []

    for filename, expected in EXPECTED.items():
        message = parse_eml(INBOX / filename)
        decision = full_detector(message)
        ok = decision.verdict == expected
        marker = "PASS" if ok else "FAIL"
        print(
            f"{marker}: {filename}: expected={expected.upper()} "
            f"actual={decision.verdict.upper()} | {decision.reason}"
        )
        if decision.evidence:
            print(f"  evidence: {decision.evidence}")

        if not ok:
            failures.append((filename, expected, decision.verdict))

    if failures:
        details = ", ".join(
            f"{name} expected {expected} got {actual}"
            for name, expected, actual in failures
        )
        raise SystemExit(f"Integration checks failed: {details}")

    print(f"\nAll {len(EXPECTED)} detector integration checks passed.")


if __name__ == "__main__":
    main()
