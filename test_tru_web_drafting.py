"""Tests for the live TRU-grounded OpenAI drafting path."""

import os
import sys
import types
import unittest

from email_assistant.drafting import TRUWebDrafter
from email_assistant.models import IncomingEmail, ScreeningDecision
from email_assistant.pipeline import process_message


def email():
    return IncomingEmail(
        source_id="tru-web-test",
        sender="student@example.test",
        subject="Registration",
        raw_body="When is registration?",
        inspection_text="When is registration?",
        student_text="When is registration?",
        content_type="text/plain",
    )


class LiveStyleDrafter:
    name = "live-test"
    requires_policy_text = False
    enforce_policy_facts = False
    last_sources = [{"url": "https://www.tru.ca/example", "title": "TRU"}]

    def generate(self, message, policy_text=""):
        return "Hello,\n\nThe official information lists January 20, 2031.\n\nKind regards"


class TRUWebDraftingTests(unittest.TestCase):
    def test_pipeline_allows_verified_live_mode_without_fixed_policy(self):
        result = process_message(
            email(),
            detector=lambda _: ScreeningDecision("pass", "safe"),
            drafter=LiveStyleDrafter(),
            policy_text="",
        )
        self.assertEqual(result.verdict, "pass")
        self.assertIsNotNone(result.draft)

    def test_tru_web_drafter_requires_tru_only_search(self):
        calls = []

        source = types.SimpleNamespace(
            type="url",
            url="https://www.tru.ca/current/enrolment-services.html",
        )
        action = types.SimpleNamespace(
            type="search",
            sources=[source],
        )
        search_call = types.SimpleNamespace(
            type="web_search_call",
            action=action,
        )
        response = types.SimpleNamespace(
            output_text="Hello,\n\nPlease review the official TRU registration information.",
            output=[search_call],
        )

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return response

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()

        fake_module = types.ModuleType("openai")
        fake_module.OpenAI = FakeOpenAI

        old_module = sys.modules.get("openai")
        old_key = os.environ.get("OPENAI_API_KEY")
        old_model = os.environ.get("OPENAI_MODEL")

        try:
            os.environ["OPENAI_API_KEY"] = "fake-key"
            os.environ["OPENAI_MODEL"] = "test-model"
            sys.modules["openai"] = fake_module

            drafter = TRUWebDrafter()
            draft = drafter.generate(email())

            self.assertIn("official TRU", draft)
            self.assertEqual(calls[0]["tool_choice"], "required")
            self.assertEqual(
                calls[0]["tools"][0]["filters"]["allowed_domains"],
                ["tru.ca"],
            )
            self.assertTrue(calls[0]["tools"][0]["external_web_access"])
            self.assertEqual(
                calls[0]["include"],
                ["web_search_call.action.sources"],
            )
            self.assertFalse(calls[0]["store"])
            self.assertEqual(
                drafter.last_sources[0]["url"],
                "https://www.tru.ca/current/enrolment-services.html",
            )
        finally:
            if old_module is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = old_module

            if old_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_key

            if old_model is None:
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = old_model

    def test_tru_web_drafter_rejects_response_without_tru_source(self):
        action = types.SimpleNamespace(
            type="search",
            sources=[
                types.SimpleNamespace(
                    type="url",
                    url="https://example.com/not-tru",
                )
            ],
        )
        response = types.SimpleNamespace(
            output_text="Unsupported answer",
            output=[types.SimpleNamespace(type="web_search_call", action=action)],
        )

        class FakeResponses:
            def create(self, **kwargs):
                return response

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()

        fake_module = types.ModuleType("openai")
        fake_module.OpenAI = FakeOpenAI

        old_module = sys.modules.get("openai")
        old_key = os.environ.get("OPENAI_API_KEY")

        try:
            os.environ["OPENAI_API_KEY"] = "fake-key"
            sys.modules["openai"] = fake_module

            drafter = TRUWebDrafter("test-model")
            with self.assertRaisesRegex(RuntimeError, "No official TRU source"):
                drafter.generate(email())
        finally:
            if old_module is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = old_module

            if old_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
