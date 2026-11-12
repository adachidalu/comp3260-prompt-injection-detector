# Agent Handover — Favour's Detection Workstream

## Source of truth

Project proposal: *Detecting Indirect Prompt Injection in University Email Assistants*, COMP 3260, Thompson Rivers University. The proposal describes four disguises: hidden HTML, Base64, invisible characters, and look-alike characters. Plain attacks also require rules. Week 2 is the detector milestone. Testing uses fictional email and policy data.

## Current state

A minimal `detector.py` and four tests have been created for hidden HTML detection; no other disguise detectors have been implemented. No integration with teammates' software has happened.

## Interface

`inspect_hidden_html(subject, html_body)` returns a dict with `subject`, `verdict`, `evidence`, `hidden_fragments`. Current verdicts: `pass`, `review`; later add `block` for prohibited instructions as specified in proposal.

## Limitations and security caveats

The parser is illustrative only and can mis-handle malformed HTML and complex CSS. Patterns are not comprehensive. The detector must not serve as the sole authorization mechanism; actions must be denied independently. Keep all data synthetic. The project should measure actual misses and false alarms on a held-out set rather than assume detection accuracy.

## Immediate next interaction

Ask Favour to run `python detector.py` and `python test_detector.py`. Explain the output and troubleshoot. Next develop Base64 detection, with resource bounds and evidence tracking, separately from the fixed evaluation set.

## Team context

Chinaza is working on email processing and AI integration per shared project conversation. The remaining exact teammate role distribution has not been verified in this chat. Team has four people, four weeks, and ~12 hours per person per week.
