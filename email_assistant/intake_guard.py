"""Operational structure checks before prompt-injection screening.

This is NOT a replacement for Favour's full_detector: it checks validity, size,
and supported formats rather than suspicious wording.
"""
from .models import IncomingEmail, ScreeningDecision

MAX_BODY_CHARS = 60000
MAX_STUDENT_CHARS = 20000
MAX_SUBJECT_CHARS = 300
SUPPORTED_TYPES = frozenset({'text/plain', 'text/html', 'multipart/alternative'})


def check_incoming_email(message: IncomingEmail) -> ScreeningDecision:
    """Fail closed to REVIEW for malformed, empty, or oversized input."""
    fields = ('source_id', 'sender', 'subject', 'raw_body', 'inspection_text',
              'student_text', 'content_type')
    if not isinstance(message, IncomingEmail):
        return ScreeningDecision('review', 'Intake validation failed: invalid email object')
    if any(not isinstance(getattr(message, key, None), str) for key in fields):
        return ScreeningDecision('review', 'Intake validation failed: invalid email fields')
    if not message.source_id.strip() or not message.raw_body.strip():
        return ScreeningDecision('review', 'Intake validation failed: missing message identity or body')
    if message.content_type.lower() not in SUPPORTED_TYPES:
        return ScreeningDecision('review', 'Intake validation failed: unsupported content type')
    if not message.student_text.strip():
        return ScreeningDecision('review', 'Intake validation failed: no readable student enquiry')
    if len(message.raw_body) > MAX_BODY_CHARS or len(message.inspection_text) > 2 * MAX_BODY_CHARS:
        return ScreeningDecision('review', 'Intake validation failed: email exceeds safe text limit')
    if len(message.student_text) > MAX_STUDENT_CHARS:
        return ScreeningDecision('review', 'Intake validation failed: student text exceeds AI input limit')
    if len(message.subject) > MAX_SUBJECT_CHARS or len(message.sender) > 254:
        return ScreeningDecision('review', 'Intake validation failed: oversized metadata')
    if any('\x00' in getattr(message, key) for key in fields):
        return ScreeningDecision('review', 'Intake validation failed: NUL control byte')
    return ScreeningDecision('pass', 'Input structure and size validated')
