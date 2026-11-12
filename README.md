# Favour's detector starter — Lesson 1

This starter implements one part of the COMP 3260 email-assistant project: suspicious hidden HTML text detection.

## Requirements

- Python 3.10 or newer
- No third-party packages

## Run

```bash
python detector.py
python test_detector.py
```

## Expected demonstration output

- Ordinary enquiry: `pass`
- Hidden instruction attempting to change the answer: `review`
- Hidden harmless formatting note: `pass`

## What the code does

1. Parses HTML with Python's built-in `HTMLParser`.
2. Extracts text inside elements hidden using `hidden`, `display:none`, `visibility:hidden`, or `opacity:0`.
3. Checks extracted text against a few illustrative suspicious-instruction patterns.
4. Returns a verdict and matched evidence for a reviewer.

## Important limitations

This is a *starter*, not a comprehensive HTML/CSS interpretation engine. It cannot reliably interpret stylesheet classes, complex/nested or malformed HTML, CSS cascading, email-client rendering quirks, and many concealment tricks. It may miss attacks and false-alarm on legitimate text. A `pass` does not guarantee safety. The full system must separately enforce action permissions, draft checking, and human review as described in the proposal. Never use real student records.

## Team integration interface

`inspect_hidden_html(subject: str, html_body: str) -> dict` returns `subject`, `verdict`, `evidence` and `hidden_fragments`.

## Next steps

- Improve HTML parsing and handling of malformed tags.
- Add tests of nested spans, HTML entities, and tricky CSS cases.
- Add Base64, invisible-character, and confusable-character detectors in separate functions.
- Coordinate an agreed common return schema with the teammate integrating the app.
