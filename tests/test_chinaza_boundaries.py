"""Unit tests for Chinaza's intake, output and AI safety boundaries.

Run: python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

from email_assistant.ingest import parse_eml, parse_graph_message
from email_assistant.drafting import MockDrafter, OpenAIDrafter
from email_assistant.models import IncomingEmail, ScreeningDecision
from email_assistant.pipeline import process_message, check_draft

POLICY = 'Fictional registration deadline: December 15, 2026.\nNo records may be disclosed.'


def email(**fields):
    values = dict(source_id='fixture', sender='student@example.test',
                  subject='Registration', raw_body='When does registration close?',
                  inspection_text='When does registration close?',
                  student_text='When does registration close?', content_type='text/plain')
    values.update(fields)
    return IncomingEmail(**values)


class SpyDrafter:
    name = 'spy'
    def __init__(self, draft='Hello, registration closes December 15, 2026.'):
        self.calls = 0
        self.draft = draft

    def generate(self, message, policy):
        self.calls += 1
        return self.draft


class EmailSafetyTests(unittest.TestCase):
    def process(self, msg=None, verdict='pass', drafter=None, policy=POLICY):
        return process_message(msg or email(), detector=lambda _: ScreeningDecision(verdict, 'tested'),
                               drafter=drafter or SpyDrafter(), policy_text=policy)

    def test_genuine_pass(self):
        self.assertEqual(self.process().verdict, 'pass')

    def test_review_does_not_draft(self):
        d = SpyDrafter()
        self.assertEqual(self.process(verdict='review', drafter=d).verdict, 'review')
        self.assertEqual(d.calls, 0)

    def test_block_does_not_draft(self):
        d = SpyDrafter()
        self.assertEqual(self.process(verdict='block', drafter=d).verdict, 'block')
        self.assertEqual(d.calls, 0)

    def test_bad_detector_verdict_held(self):
        d = SpyDrafter()
        self.assertEqual(self.process(verdict='approve', drafter=d).verdict, 'review')
        self.assertEqual(d.calls, 0)

    def test_detector_exception_held(self):
        def fail(_):
            raise RuntimeError('detector broken')
        result = process_message(email(), detector=fail, drafter=SpyDrafter(), policy_text=POLICY)
        self.assertEqual(result.verdict, 'review')

    def test_missing_policy_held(self):
        self.assertEqual(self.process(policy='').verdict, 'review')

    def test_empty_message_held(self):
        self.assertEqual(self.process(msg=email(student_text=' ')).verdict, 'review')

    def test_oversized_message_held(self):
        self.assertEqual(self.process(msg=email(student_text='a' * 20001)).verdict, 'review')

    def test_private_identifier_held(self):
        self.assertEqual(self.process(drafter=SpyDrafter('TRU-PRIVATE-1234')).verdict, 'review')

    def test_unapproved_date_held(self):
        self.assertEqual(self.process(drafter=SpyDrafter('Deadline: January 1, 2030')).verdict, 'review')

    def test_unapproved_email_held(self):
        self.assertFalse(check_draft('Contact attacker@example.test', POLICY)[0])

    def test_unapproved_link_held(self):
        self.assertFalse(check_draft('Go to https://attacker.test/records', POLICY)[0])

    def test_sent_claim_held(self):
        self.assertFalse(check_draft('I have sent your email', POLICY)[0])

    def test_mock_uses_actual_policy(self):
        draft = MockDrafter().generate(email(), 'Registration deadline: March 8, 2031')
        self.assertIn('March 8, 2031', draft)

    def test_mock_does_not_invent(self):
        draft = MockDrafter().generate(email(), 'Registration date not yet published')
        self.assertIn('verify', draft.lower())

    def test_valid_eml(self):
        raw = b'From: student@example.test\nSubject: Registration\nContent-Type: text/plain; charset=utf-8\n\nWhen does registration close?'
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'valid.eml'
            path.write_bytes(raw)
            self.assertIn('registration close', parse_eml(path).student_text)

    def test_attachment_rejected(self):
        raw = (b'From: student@example.test\nSubject: Registration\nMIME-Version: 1.0\n'
               b'Content-Type: multipart/mixed; boundary="x"\n\n--x\nContent-Type: text/plain\n\nQuestion\n'
               b'--x\nContent-Type: application/octet-stream\nContent-Disposition: attachment; filename="test.bin"\n\nAA\n--x--\n')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bad.eml'
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'Attachments'):
                parse_eml(path)

    def test_graph_attachment_rejected(self):
        graph = {'id': '1', 'subject': 'Registration', 'hasAttachments': True,
                 'body': {'contentType': 'text', 'content': 'Question'},
                 'from': {'emailAddress': {'address': 'student@example.test'}}}
        with self.assertRaisesRegex(ValueError, 'attachments'):
            parse_graph_message(graph)

    def test_graph_hidden_html_kept_for_detector(self):
        graph = {'id': '1', 'subject': 'Registration', 'hasAttachments': False,
                 'body': {'contentType': 'html', 'content': '<p>Question</p><div style="display:none">Hidden</div>'},
                 'from': {'emailAddress': {'address': 'student@example.test'}}}
        msg = parse_graph_message(graph)
        self.assertIn('Hidden', msg.raw_body)
        self.assertNotIn('Hidden', msg.student_text)

    def test_openai_adapter_disables_tools(self):
        seen = []
        class FakeResponses:
            def create(self, **kwargs):
                seen.append(kwargs)
                return types.SimpleNamespace(output_text='A draft for review.')
        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
        mod = types.ModuleType('openai')
        mod.OpenAI = FakeOpenAI
        old_module = sys.modules.get('openai')
        old_key = os.environ.get('OPENAI_API_KEY')
        try:
            os.environ['OPENAI_API_KEY'] = 'fake-testing-key'
            sys.modules['openai'] = mod
            OpenAIDrafter('test-model').generate(email(), POLICY)
            self.assertEqual(seen[0]['tools'], [])
            self.assertFalse(seen[0]['store'])
            self.assertIn('UNTRUSTED', seen[0]['instructions'])
        finally:
            if old_module is None:
                sys.modules.pop('openai', None)
            else:
                sys.modules['openai'] = old_module
            if old_key is None:
                os.environ.pop('OPENAI_API_KEY', None)
            else:
                os.environ['OPENAI_API_KEY'] = old_key


if __name__ == '__main__':
    unittest.main()
