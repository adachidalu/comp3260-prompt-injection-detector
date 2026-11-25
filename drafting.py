"""Compatibility wrapper for the maintained drafting providers.

The Streamlit app and replay runner use `email_assistant/drafting.py`.
Edit that file, not this wrapper.
"""
try:
    from email_assistant.drafting import *
except ImportError:  # package-style legacy invocation
    from .email_assistant.drafting import *
