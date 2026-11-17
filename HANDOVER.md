# Agent Handover — Detection Workstream

## Source of truth

Project: *Detecting Indirect Prompt Injection in University Email Assistants*,
COMP 3260, Thompson Rivers University.

The detector must cover five forms:

1. openly written attacks
2. hidden HTML
3. Base64
4. invisible/zero-width characters
5. Unicode look-alike/confusable characters

All testing uses fictional data.

## Current detector state

The `favour` branch now contains the unified detector implementation.

Official team-facing function:

```python
from .screening import full_detector
```

Input:

```python
IncomingEmail
```

Output:

```python
ScreeningDecision(
    verdict="pass" | "review" | "block",
    reason="...",
    evidence="...",
)
```

Implemented detector modes:

- `no_screening_detector`: evaluation baseline only
- `original_detector`: rules on the original/visible message
- `full_detector`: original + disguise-revealing inspection

The old name `favour_detector` remains only as a compatibility alias.

## Implemented detection coverage

- plain/direct suspicious instructions
- hidden HTML/CSS instructions
- Base64 decoding followed by suspicious-rule scanning
- zero-width/invisible character removal followed by scanning
- bounded Unicode confusable normalization followed by scanning
- PASS / REVIEW / BLOCK
- human-readable evidence strings
- fail-closed behavior through the shared pipeline

## Development and integration checks

Unit/development tests:

```powershell
python test_detector.py
python run_development_tests.py
```

End-to-end synthetic email checks, run from the directory above the package:

```powershell
python -m favour_detector_lesson1.run_detector_integration_tests
```

The integration inbox includes:

- genuine email -> PASS
- plain attack -> REVIEW
- hidden HTML attack -> REVIEW
- Base64 attack -> REVIEW
- zero-width attack -> REVIEW
- look-alike attack -> REVIEW
- private-record request -> BLOCK

## Week-3 detector pilot support

A fixed 26-case DEVELOPMENT pilot is checked in as:

```text
development_pilot_26.csv
```

It contains:

- 6 genuine enquiries
- 4 plain attacks
- 16 disguised variants

It can be regenerated deterministically with:

```powershell
python -m favour_detector_lesson1.generate_detector_pilot
```

Run all three detector configurations:

```powershell
python -m favour_detector_lesson1.detector_replay --csv favour_detector_lesson1/development_pilot_26.csv --expected-count 26
```

The replay exports detector results and summary metrics including:

- attacks flagged
- missed attacks
- genuine enquiries held
- false-alarm rate
- processing failures
- screening time
- breakdown by disguise
- breakdown by base attack

## Week-4 detector replay support

The same replay tool can process the final correctly labelled 650-case
university-email CSV:

```powershell
python -m favour_detector_lesson1.detector_replay --csv PATH_TO_FINAL_650.csv --expected-count 650
```

Important: the existing `scientific_prompt_injection_650.jsonl` in the
repository does not match the university-support dataset described in the
proposal. Do not use it as the final proposal evaluation set without a team
decision correcting the mismatch.

## Team boundaries

### Chinaza

Email intake and AI drafting integration remain outside the detector workstream.
Do not replace Graph/mailbox logic or drafting-provider logic.

### Amarachi

Verdict/security handling remains outside the detector. Consume the returned
`ScreeningDecision`; do not duplicate detector rules.

### Other teammate-owned/shared components

Exact ownership must be confirmed before implementation:

- final 650-case university-email dataset
- action permission checker and denied-action logging
- final Streamlit review UI
- integrated AI cost / draft accuracy / reviewer-minute measurements
- final report and presentation packaging

The detector replay intentionally leaves these integrated metrics as pending
rather than inventing values.

## Integration rule

Do not duplicate prompt-injection rules elsewhere. Other components should call
`full_detector(message)`.

Do not rename or change `IncomingEmail`, `ScreeningDecision`, or the shared
pipeline contract without coordinating with the team.
