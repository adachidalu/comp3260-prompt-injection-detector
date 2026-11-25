"""Compatibility wrapper for the maintained screening adapters.

Edit `email_assistant/screening.py` for application changes.
"""
try:
    from email_assistant.screening import *
except ImportError:  # package-style legacy invocation
    from .email_assistant.screening import *
