"""Offline harness checks, not a development set for detector tuning."""
import unittest

from email_assistant.drafting import MockDrafter
from email_assistant.models import ScreeningDecision
import generate_dataset as g
import replay_university as replay


class UniversityReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = g.generate(shuffle=False)
        cls.policy = g.read_policy()

    def test_replay_all_modes_on_smoke_examples(self):
        # Harness smoke checks only; no detector rules are adjusted here.
        pilot = [
            {
                **self.rows[0], "case_id": "PILOT-G",
            },
            {
                **next(r for r in self.rows if r["disguise"] == "plain"),
                "case_id": "PILOT-A",
            },
        ]
        records = replay.replay(pilot, self.policy["approved_policy"], MockDrafter(),
                                configs=tuple(replay.CONFIGS))
        self.assertEqual(len(records), 6)
        self.assertEqual({r["configuration"] for r in records}, set(replay.CONFIGS))
        self.assertTrue(all(r["attack_goal_success"] is None for r in records))
        self.assertTrue(all(r["attempted_actions"] is None for r in records))
        self.assertTrue(all(r["action_authorization_connected"] is False for r in records))

    def test_full_summary_does_not_invent_team_metrics(self):
        genuine = {**self.rows[0], "case_id": "DEMO-G"}
        attack = {**next(r for r in self.rows if r["disguise"] == "plain"), "case_id": "DEMO-A"}
        rows = replay.replay([genuine, attack], self.policy["approved_policy"],
                             MockDrafter(), configs=("phase1_baseline", "phase3_enhanced"))
        summary = replay.summarize(rows, "synthetic-hash", self.policy["policy_id"],
                                   provider="offline-mock (not AI)", preview=True)
        self.assertTrue(summary["preview_only"])
        for group in summary["configurations"].values():
            self.assertIsNone(group["attack_goal_success_rate"])
            self.assertIsNone(group["draft_accuracy_rate"])
            self.assertIsNone(group["blocked_actions"])
            self.assertIsNone(group["model_cost_usd"])
            self.assertEqual(group["cases"], 2)

    def test_mock_only_produces_drafts_for_allowed_cases(self):
        rows = [self.rows[0],
                next(r for r in self.rows if r["disguise"] == "plain"
                     and r["attack_goal"] == "policy_override")]
        result = replay.replay(rows, self.policy["approved_policy"], MockDrafter(),
                               configs=("phase3_enhanced",))
        self.assertTrue(result[0]["draft_created"])
        self.assertFalse(result[1]["draft_created"])
        self.assertTrue(result[1]["screening_flagged"])

    def test_output_hold_is_not_counted_as_detector_flag(self):
        class UnsafeDraft:
            name = "test-double"

            def generate(self, message, policy_text):
                return "I have sent your email"

        # Deliberately substitute a pass-through test double without touching
        # the team's detector; phase 3 must distinguish output holds from detection.
        name = "phase3_output_hold_test"
        replay.CONFIGS[name] = (lambda message: ScreeningDecision("pass", "passed", ""), True)
        try:
            records = replay.replay([self.rows[0]], self.policy["approved_policy"],
                                    UnsafeDraft(), configs=(name,))
        finally:
            del replay.CONFIGS[name]
        record = records[0]
        self.assertEqual(record["detector_verdict"], "pass")
        self.assertFalse(record["screening_flagged"])
        self.assertTrue(record["final_held"])
        self.assertEqual(record["raw_draft_for_evaluator"], "I have sent your email")
        self.assertFalse(record["draft_created"])
        self.assertIsNone(record["attack_goal_success"])


if __name__ == "__main__":
    unittest.main()
