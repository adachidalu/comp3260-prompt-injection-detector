"""Fail-closed pipeline: intake -> Favour's detector -> controlled drafting -> output check."""
import re
from typing import Callable
from .intake_guard import check_incoming_email
from .models import IncomingEmail, ScreeningDecision, ProcessingResult

Detector = Callable[[IncomingEmail], ScreeningDecision]
DATE_PATTERN = re.compile(
    r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|'
    r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b',
    re.IGNORECASE,
)
LINK_PATTERN = re.compile(r'https?://[^\s<>()]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', re.IGNORECASE)
PRIVATE_PATTERN = re.compile(r'\bTRU-PRIVATE-[A-Z0-9-]+\b', re.IGNORECASE)
SENT_PATTERN = re.compile(r"\b(?:I\s+(?:have\s+)?sent|I've\s+sent|the\s+email\s+(?:has\s+been|was)\s+sent)\b", re.IGNORECASE)


def check_draft(draft: str, policy_text: str = '') -> tuple[bool, str]:
    """Conservative supplemental output check, not semantic factual verification."""
    if not isinstance(draft, str) or not draft.strip():
        return False, 'AI draft is empty or invalid'
    if len(draft) > 5000:
        return False, 'AI draft exceeds safe display limit'
    if PRIVATE_PATTERN.search(draft):
        return False, 'AI draft includes a synthetic private identifier'
    if SENT_PATTERN.search(draft):
        return False, 'AI draft incorrectly claims mail was sent'
    if any(x not in policy_text for x in DATE_PATTERN.findall(draft)):
        return False, 'AI draft mentions a date absent from approved policy'
    if any(x.rstrip('.,;:') not in policy_text for x in LINK_PATTERN.findall(draft)):
        return False, 'AI draft includes an unapproved address or URL'
    return True, ''


def process_message(message: IncomingEmail, *, detector: Detector, drafter,
                    policy_text: str, output_check: bool = True) -> ProcessingResult:
    provider = getattr(drafter, 'name', '(unknown)')
    source_id = getattr(message, 'source_id', '(invalid email)')
    subject = getattr(message, 'subject', '(invalid email)')
    try:
        intake = check_incoming_email(message)
        if intake.verdict != 'pass':
            return ProcessingResult(source_id, subject, 'review', intake.reason, provider=provider)
        if not isinstance(policy_text, str) or not policy_text.strip():
            return ProcessingResult(source_id, subject, 'review',
                                    'Approved mock policy is missing', provider=provider)
        decision = detector(message)
        if not isinstance(decision, ScreeningDecision) or decision.verdict not in ('pass', 'review', 'block'):
            raise ValueError('Detector returned invalid verdict')
    except Exception as exc:
        return ProcessingResult(source_id, subject, 'review',
                                f'Security check failed: {type(exc).__name__}', provider=provider)
    if decision.verdict != 'pass':
        return ProcessingResult(source_id, subject, decision.verdict,
                                decision.reason, decision.evidence, provider=provider)
    try:
        draft = drafter.generate(message, policy_text)
        if output_check:
            good, issue = check_draft(draft, policy_text)
            if not good:
                return ProcessingResult(source_id, subject, 'review', issue,
                                        decision.evidence, provider=provider)
        return ProcessingResult(source_id, subject, 'pass', decision.reason,
                                decision.evidence, draft, provider)
    except Exception as exc:
        return ProcessingResult(source_id, subject, 'review',
                                f'Drafting failed: {type(exc).__name__}', provider=provider)
