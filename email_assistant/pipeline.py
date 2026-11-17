"""Team handoff: intake -> detector -> (optional) draft -> staff review."""
import re
from typing import Callable
from .models import IncomingEmail, ScreeningDecision, ProcessingResult

Detector = Callable[[IncomingEmail], ScreeningDecision]


def check_draft(draft: str) -> tuple[bool, str]:
    """Tiny safety example, NOT the final Week-3 action/output checker."""
    if re.search(r'TRU-PRIVATE-[A-Z0-9-]+', draft, flags=re.IGNORECASE):
        return False, 'Draft contains a synthetic private identifier'
    return True, ''


def process_message(message: IncomingEmail, *, detector: Detector, drafter,
                    policy_text: str, output_check: bool = True) -> ProcessingResult:
    try:
        decision = detector(message)
        if decision.verdict not in ('pass', 'review', 'block'):
            raise ValueError('Detector returned invalid verdict')
    except Exception as exc:
        # A broken rule must never accidentally grant permission to draft.
        return ProcessingResult(message.source_id, message.subject, 'review',
                                f'Detector failed: {type(exc).__name__}', provider=drafter.name)

    if decision.verdict != 'pass':
        return ProcessingResult(message.source_id, message.subject, decision.verdict,
                                decision.reason, decision.evidence, provider=drafter.name)
    try:
        draft = drafter.generate(message, policy_text)
        if output_check:
            good, issue = check_draft(draft)
            if not good:
                return ProcessingResult(message.source_id, message.subject, 'review',
                                        issue, provider=drafter.name)
        return ProcessingResult(message.source_id, message.subject, 'pass',
                                decision.reason, decision.evidence, draft, drafter.name)
    except Exception as exc:
        return ProcessingResult(message.source_id, message.subject, 'review',
                                f'Drafting failed: {type(exc).__name__}', provider=drafter.name)
