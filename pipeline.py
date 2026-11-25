"""Compatibility wrapper for the integrated application pipeline.

The maintained implementation now lives in `email_assistant.pipeline`.
Keeping this wrapper prevents older package-level imports from silently using
an obsolete security path.
"""

from .email_assistant.pipeline import check_draft, process_message

__all__ = ["check_draft", "process_message"]
