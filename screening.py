"""Security-screening adapters between team email intake and detector rules.

This file owns only the detector boundary. Email intake/drafting remain in their
existing modules; action authorization and review UI should integrate through
the TODO boundaries documented elsewhere.
"""
import re

from .models import IncomingEmail, ScreeningDecision
from .detector import inspect_email


def strict_unconfigured_detector(message: IncomingEmail) -> ScreeningDecision:
    """Fail closed when no real detector has been selected."""
    return ScreeningDecision("review", "Full security detector is not connected")


def no_screening_detector(message: IncomingEmail) -> ScreeningDecision:
    """Evaluation baseline only: deliberately bypass security screening."""
    return ScreeningDecision(
        "pass",
        "Screening disabled for baseline evaluation",
        "",
    )


def demo_detector(message: IncomingEmail) -> ScreeningDecision:
    """Educational placeholder retained for backwards compatibility."""
    match = re.search(
        r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
        r"(?:send|forward|reveal)\s+[^\n.]{0,60}(?:private|student\s+record)",
        message.inspection_text,
        flags=re.IGNORECASE,
    )
    if match:
        return ScreeningDecision(
            "block",
            "Demo rule found an instruction to override or disclose",
            match.group(0),
        )
    if "html" in message.content_type or "[MIME text/html]" in message.raw_body:
        return ScreeningDecision(
            "review",
            "Demo rule cannot certify HTML email",
            "<HTML email>",
        )
    return ScreeningDecision(
        "pass",
        "Simple plain-text message passed the DEMO-only rules",
    )


def _run_detector(message: IncomingEmail, *, mode: str) -> ScreeningDecision:
    result = inspect_email(
        subject=message.subject,
        raw_body=message.raw_body,
        inspection_text=message.inspection_text,
        visible_text=message.student_text,
        mode=mode,
    )
    return ScreeningDecision(
        verdict=result["verdict"],
        reason=result["reason"],
        evidence=result["evidence"],
    )


def original_detector(message: IncomingEmail) -> ScreeningDecision:
    """Rules on the original message without disguise-revealing transforms."""
    return _run_detector(message, mode="original")


def full_detector(message: IncomingEmail) -> ScreeningDecision:
    """Full detector: original + hidden/decoded/cleaned representations."""
    return _run_detector(message, mode="full")


# Temporary backwards compatibility for older integration code / commands.
# New team code should import full_detector.
favour_detector = full_detector
