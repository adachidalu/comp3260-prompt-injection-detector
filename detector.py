"""Compatibility wrapper for the maintained detector implementation.

Edit `email_assistant/detector.py` for application changes.
"""
try:
    from email_assistant.detector import *
except ImportError:  # package-style legacy invocation
    from .email_assistant.detector import *
