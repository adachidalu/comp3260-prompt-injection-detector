"""Compatibility entry point for the maintained application CLI.

The implementation lives in `email_assistant/cli.py`.
"""
try:
    from email_assistant.cli import *
    from email_assistant.cli import main as _main
except ImportError:  # package-style legacy invocation
    from .email_assistant.cli import *
    from .email_assistant.cli import main as _main


if __name__ == "__main__":
    _main()
