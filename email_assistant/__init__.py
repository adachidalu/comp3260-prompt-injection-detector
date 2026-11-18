"""Deployable university email assistant package.

New code should import from this package. The root-level modules remain
temporarily for backwards compatibility with the team's existing commands.
"""

from .models import IncomingEmail, ProcessingResult, ScreeningDecision
from .screening import full_detector, no_screening_detector, original_detector

__all__ = [
    "IncomingEmail",
    "ProcessingResult",
    "ScreeningDecision",
    "full_detector",
    "original_detector",
    "no_screening_detector",
]
