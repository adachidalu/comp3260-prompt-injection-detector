"""Regression tests for the integrated team security controls."""

import tempfile
import unittest
from pathlib import Path

import db_manager

from email_assistant.drafting import MockDrafter
from email_assistant.models import IncomingEmail
from email_assistant.pipeline import process_message
from email_assistant.screening import full_detector
from email_assistant.security_controls import (
    audit_summary,
    authorize_mock_action,
)


def _genuine_message(source_id: str = "integration-genuine") -> IncomingEmail:
    return IncomingEmail(
        source_id=source_id,
        sender="student@example.test",
        subject="Registration",
        raw_body="When does registration close?",
        inspection_text="When does registration close?",
        student_text="When does registration close?",
        content_type="text/plain",
    )


class LeakyDrafter:
    name = "leaky-test-drafter"

    def generate(self, message, policy_text):
        return "Hello, the synthetic student ID is TRU-123456."


class IntegratedSecurityTests(unittest.TestCase):
    def test_private_output_validator_holds_leaky_draft(self):
        result = process_message(
            _genuine_message(),
            detector=full_detector,
            drafter=LeakyDrafter(),
            policy_text="Registration support is available.",
        )

        self.assertEqual(result.verdict, "review")
        self.assertIsNone(result.draft)
        self.assertIn("private-data", result.reason.lower())

    def test_action_authorizer_allows_only_approved_mock_policy_read(self):
        allowed = authorize_mock_action(
            {"action_type": "read_mock_policy", "target": "policy"},
            audit=False,
        )
        denied_record = authorize_mock_action(
            {"action_type": "read_student_record", "target": "student-1"},
            audit=False,
        )
        denied_transfer = authorize_mock_action(
            {"action_type": "external_transfer", "target": "external"},
            audit=False,
        )
        denied_send = authorize_mock_action(
            {"action_type": "send_email", "target": "student@example.test"},
            audit=False,
        )

        self.assertTrue(allowed["allowed"])
        self.assertFalse(denied_record["allowed"])
        self.assertFalse(denied_transfer["allowed"])
        self.assertFalse(denied_send["allowed"])

    def test_verdict_and_action_are_written_to_audit_database(self):
        original_path = db_manager.DB_PATH

        with tempfile.TemporaryDirectory() as temp_dir:
            db_manager.DB_PATH = Path(temp_dir) / "security_audit.db"
            try:
                result = process_message(
                    _genuine_message("audit-genuine"),
                    detector=full_detector,
                    drafter=MockDrafter(),
                    policy_text="Registration deadline is December 15, 2026.",
                    audit=True,
                )
                self.assertEqual(result.verdict, "pass")

                action = authorize_mock_action(
                    {"action_type": "read_student_record", "target": "student-1"},
                    audit=True,
                )
                self.assertFalse(action["allowed"])
                self.assertTrue(action["audit_logged"])

                summary = audit_summary()
                self.assertEqual(summary["total_verdicts"], 1)
                self.assertEqual(summary["total_action_requests"], 1)
            finally:
                db_manager.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
