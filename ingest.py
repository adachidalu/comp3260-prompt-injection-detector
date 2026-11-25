"""Compatibility wrapper for the maintained email intake code.

The Streamlit app and dataset tests use `email_assistant/ingest.py`.
Edit that file, not this wrapper.
"""
try:
    from email_assistant.ingest import *
except ImportError:  # package-style legacy invocation
    from .email_assistant.ingest import *
