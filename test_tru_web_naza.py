"""Offline regression tests for the Favour-derived Naza TRU live adapter."""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

from email_assistant.models import IncomingEmail, ScreeningDecision
from email_assistant.pipeline import check_draft, process_message
from email_assistant.tru_web_drafting import TRUWebDrafter, _official_tru_url


def email(body="Where can I find registration information?"):
    return IncomingEmail(
        source_id="tru-test", sender="student@example.test",
        subject="Enrolment question", raw_body=body,
        inspection_text=body, student_text=body, content_type="text/plain",
    )


class _FakeResponses:
    def __init__(self, source="https://www.tru.ca/enrolment-services.html",
                 draft="Hello, please check the official TRU registration information."):
        self.source = source
        self.draft = draft
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(
            output_text=self.draft,
            output=[types.SimpleNamespace(
                type="web_search_call",
                action=types.SimpleNamespace(
                    type="search",
                    sources=[types.SimpleNamespace(url=self.source)],
                ),
            )],
        )


class _FakeOpenAI:
    def __init__(self, responses):
        self.responses = responses


class TRULiveNazaTests(unittest.TestCase):
    def test_rejects_non_tru_sources(self):
        for url in ("https://tru.ca.evil.test/x", "http://www.tru.ca/x",
                    "https://not-tru.ca/x", "javascript:alert(1)", ""):
            self.assertFalse(_official_tru_url(url), url)
        self.assertTrue(_official_tru_url("https://tru.ca/x"))
        self.assertTrue(_official_tru_url("https://www.tru.ca/x"))

    def test_requires_individual_server_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                TRUWebDrafter()

    def _make_drafter(self, *, source="https://www.tru.ca/x",
                      draft="Hello, please check official TRU information."):
        fake = _FakeResponses(source=source, draft=draft)
        api = types.ModuleType("openai")
        api.OpenAI = lambda **kwargs: _FakeOpenAI(fake)
        return fake, api

    def test_requires_web_search_and_restricts_domain(self):
        fake, api = self._make_drafter()
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-test-key",
            "OPENAI_MODEL": "mock-supported-model"
        }), patch.dict(sys.modules, {"openai": api}):
            drafter = TRUWebDrafter()
            self.assertIn("official TRU", drafter.generate(email()))
            sent = fake.calls[0]
            self.assertEqual(sent["tools"][0]["filters"]["allowed_domains"], ["tru.ca"])
            self.assertEqual(sent["tool_choice"], "required")
            self.assertFalse(sent["store"])
            self.assertEqual(sent["model"], "mock-supported-model")

    def test_missing_tru_source_blocks_reply(self):
        fake, api = self._make_drafter(source="https://tru.ca.evil.test/x")
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-test-key", "OPENAI_MODEL": "test-model"
        }), patch.dict(sys.modules, {"openai": api}):
            drafter = TRUWebDrafter()
            with self.assertRaisesRegex(RuntimeError, "No official TRU"):
                drafter.generate(email())

    def test_pipeline_allows_web_mode_without_mock_policy(self):
        fake, api = self._make_drafter(draft="The official website lists September 8, 2099.")
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-test-key", "OPENAI_MODEL": "test-model"
        }), patch.dict(sys.modules, {"openai": api}):
            drafter = TRUWebDrafter()
            result = process_message(
                email(), detector=lambda m: ScreeningDecision("pass", "safe"),
                drafter=drafter, policy_text="", output_check=True,
            )
            self.assertEqual(result.verdict, "pass")
            self.assertIsNotNone(result.draft)

    def test_private_output_is_held_even_in_web_mode(self):
        fake, api = self._make_drafter(draft="Here is TRU-PRIVATE-TEST-042")
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-test-key", "OPENAI_MODEL": "test-model"
        }), patch.dict(sys.modules, {"openai": api}):
            drafter = TRUWebDrafter()
            result = process_message(
                email(), detector=lambda m: ScreeningDecision("pass", "safe"),
                drafter=drafter, policy_text="", output_check=True,
            )
            self.assertEqual(result.verdict, "review")
            self.assertIsNone(result.draft)

    def test_fixed_policy_checks_remain_enabled_by_default(self):
        self.assertEqual(check_draft("September 8, 2099", "Registration closes 2026-12-15")[0], False)


if __name__ == "__main__":
    unittest.main()
