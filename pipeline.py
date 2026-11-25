"""Compatibility wrapper for the integrated application pipeline.

The maintained implementation lives in `email_assistant.pipeline`.
"""
try:
    from email_assistant.pipeline import *
except ImportError:  # package-style legacy invocation
    from .email_assistant.pipeline import *
