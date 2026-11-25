"""Deployable university email assistant package.

New code should import from this package. Root-level teammate modules remain
available for backwards compatibility; package adapters connect them to the app.
"""

from .models import IncomingEmail, ProcessingResult, ScreeningDecision
from .screening import full_detector, no_screening_detector, original_detector
from .security_controls import (
    audit_summary,
    authorize_mock_action,
    validate_private_output,
    verdict_policy,
)

__all__ = [
    "IncomingEmail",
    "ProcessingResult",
    "ScreeningDecision",
    "full_detector",
    "original_detector",
    "no_screening_detector",
    "verdict_policy",
    "validate_private_output",
    "authorize_mock_action",
    "audit_summary",
]
