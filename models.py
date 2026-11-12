"""Shared data shapes for Chinaza's email intake and team integrations."""
from dataclasses import dataclass
from typing import Literal

Verdict = Literal['pass', 'review', 'block']


@dataclass(frozen=True)
class IncomingEmail:
    source_id: str
    sender: str
    subject: str
    raw_body: str             # Original text/MIME parts, including HTML markup
    inspection_text: str      # Extracted text for the security detector
    student_text: str         # Best-effort student question for drafting (NOT a security boundary)
    content_type: str         # text/plain, text/html, or multipart/alternative


@dataclass(frozen=True)
class ScreeningDecision:
    verdict: Verdict
    reason: str
    evidence: str = ''


@dataclass(frozen=True)
class ProcessingResult:
    source_id: str
    subject: str
    verdict: Verdict
    reason: str
    evidence: str = ''
    draft: str | None = None
    provider: str = ''
