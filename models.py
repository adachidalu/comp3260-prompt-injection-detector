"""Compatibility wrapper for the maintained shared data models.

Edit `email_assistant/models.py` for application changes.
"""
try:
    from email_assistant.models import *
except ImportError:  # package-style legacy invocation
    from .email_assistant.models import *
