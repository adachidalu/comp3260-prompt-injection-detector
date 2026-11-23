"""Tests for browser-triggered replay orchestration (no Streamlit server/API needed)."""
import unittest

from email_assistant.batch_runner import load_evaluation, run_batch
from email_assistant.drafting import MockDrafter
from replay_university import CONFIGS


class BatchRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.policy = load_evaluation()

    def test_dataset_is_650_and_labels_match_plan(self):
        self.assertEqual(len(self.cases), 650)
        self.assertEqual(sum(c["label"] == "genuine" for c in self.cases), 150)
        self.assertEqual(sum(c["label"] == "attack" for c in self.cases), 500)

    def test_preview_runs_same_replay_for_all_modes(self):
        progress = []
        records, summary = run_batch(
            self.cases, self.policy, MockDrafter(),
            config_names=tuple(CONFIGS), case_count=10,
            progress=lambda done, total, mode: progress.append((done, total, mode)),
        )
        self.assertEqual(len(records), 30)
        self.assertEqual(summary["completed_evaluations"], 30)
        self.assertEqual(set(summary["configurations"]), set(CONFIGS))
        self.assertTrue(summary["preview_only"])
        self.assertEqual(progress[-1][:2], (30, 30))
        self.assertTrue(all(r["action_authorization_connected"] is False for r in records))

    def test_one_mode_is_marked_partial(self):
        records, summary = run_batch(
            self.cases, self.policy, MockDrafter(),
            config_names=("phase3_enhanced",), case_count=10,
        )
        self.assertEqual(len(records), 10)
        self.assertEqual(summary["chosen_configurations"], ["phase3_enhanced"])
        self.assertTrue(summary["preview_only"])

    def test_unknown_mode_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            run_batch(self.cases, self.policy, MockDrafter(),
                      config_names=("unapproved_mode",), case_count=10)

    def test_no_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, "No email"):
            run_batch([], self.policy, MockDrafter(), case_count=1)

    def test_invalid_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "Case count"):
            run_batch(self.cases, self.policy, MockDrafter(), case_count=651)

    def test_policy_is_required(self):
        with self.assertRaisesRegex(ValueError, "policy"):
            run_batch(self.cases, {"approved_policy": ""}, MockDrafter(), case_count=2)


if __name__ == "__main__":
    unittest.main()
