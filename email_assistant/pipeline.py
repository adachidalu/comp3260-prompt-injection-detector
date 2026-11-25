"""Fail-closed pipeline: intake -> detector -> controlled drafting -> output checks."""

import re
from typing import Callable

from .intake_guard import check_incoming_email
from .models import IncomingEmail, ProcessingResult, ScreeningDecision
from .security_controls import (
    record_verdict,
    validate_private_output,
    verdict_policy,
)

Detector = Callable[[IncomingEmail], ScreeningDecision]

DATE_PATTERN = re.compile(
    r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|'
    r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b',
    re.IGNORECASE,
)
LINK_PATTERN = re.compile(
    r'https?://[^\s<>()]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',
    re.IGNORECASE,
)
PRIVATE_PATTERN = re.compile(r'\bTRU-PRIVATE-[A-Z0-9-]+\b', re.IGNORECASE)
SENT_PATTERN = re.compile(
    r"\b(?:I\s+(?:have\s+)?sent|I've\s+sent|the\s+email\s+(?:has\s+been|was)\s+sent)\b",
    re.IGNORECASE,
)


def check_draft(draft: str, policy_text: str = '') -> tuple[bool, str]:
    """Conservative policy-bound output check."""
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


def _result(
    source_id: str,
    subject: str,
    verdict: str,
    reason: str,
    *,
    evidence: str = '',
    draft: str | None = None,
    provider: str = '',
    audit: bool = False,
) -> ProcessingResult:
    """Create one result and optionally log its final security verdict."""
    result = ProcessingResult(
        source_id=source_id,
        subject=subject,
        verdict=verdict,
        reason=reason,
        evidence=evidence,
        draft=draft,
        provider=provider,
    )
    if audit:
        record_verdict(source_id, verdict, evidence=evidence, reason=reason)
    return result


def process_message(
    message: IncomingEmail,
    *,
    detector: Detector,
    drafter,
    policy_text: str,
    output_check: bool = True,
    audit: bool = False,
) -> ProcessingResult:
    """Process one message through all integrated security gates.

    Security order:
    1. guarded email intake
    2. prompt-injection detector
    3. PASS/REVIEW/BLOCK verdict policy
    4. controlled drafting only when permitted
    5. policy-bound output check
    6. private-data output validator
    7. optional SQLite audit log
    """
    provider = getattr(drafter, 'name', '(unknown)')
    source_id = getattr(message, 'source_id', '(invalid email)')
    subject = getattr(message, 'subject', '(invalid email)')

    try:
        intake = check_incoming_email(message)
        if intake.verdict != 'pass':
            return _result(
                source_id,
                subject,
                'review',
                intake.reason,
                provider=provider,
                audit=audit,
            )

        if not isinstance(policy_text, str) or not policy_text.strip():
            return _result(
                source_id,
                subject,
                'review',
                'Approved mock policy is missing',
                provider=provider,
                audit=audit,
            )

        decision = detector(message)
        if (
            not isinstance(decision, ScreeningDecision)
            or decision.verdict not in ('pass', 'review', 'block')
        ):
            raise ValueError('Detector returned invalid verdict')

        application_policy = verdict_policy(decision.verdict)
        final_verdict = str(application_policy.get('status', 'REVIEW')).lower()
        allow_drafting = bool(application_policy.get('allow_drafting', False))

        if final_verdict not in ('pass', 'review', 'block'):
            final_verdict = 'review'
            allow_drafting = False

    except Exception as exc:
        return _result(
            source_id,
            subject,
            'review',
            f'Security check failed: {type(exc).__name__}',
            provider=provider,
            audit=audit,
        )

    if not allow_drafting:
        return _result(
            source_id,
            subject,
            final_verdict,
            decision.reason,
            evidence=decision.evidence,
            provider=provider,
            audit=audit,
        )

    try:
        draft = drafter.generate(message, policy_text)

        if output_check:
            good, issue = check_draft(draft, policy_text)
            if not good:
                return _result(
                    source_id,
                    subject,
                    'review',
                    issue,
                    evidence=decision.evidence,
                    provider=provider,
                    audit=audit,
                )

            privacy_check = validate_private_output(draft)
            if not privacy_check.get('approved', False):
                issues = ', '.join(privacy_check.get('detected_issues', []))
                reason = privacy_check.get(
                    'reason',
                    'Generated draft failed private-data validation.',
                )
                if issues:
                    reason = f'{reason} Detected: {issues}.'
                return _result(
                    source_id,
                    subject,
                    'review',
                    reason,
                    evidence=decision.evidence,
                    provider=provider,
                    audit=audit,
                )

        return _result(
            source_id,
            subject,
            'pass',
            decision.reason,
            evidence=decision.evidence,
            draft=draft,
            provider=provider,
            audit=audit,
        )

    except Exception as exc:
        return _result(
            source_id,
            subject,
            'review',
            f'Drafting failed: {type(exc).__name__}',
            evidence=decision.evidence,
            provider=provider,
            audit=audit,
        )
