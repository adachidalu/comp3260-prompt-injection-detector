# Team Integration Boundaries

This file exists to prevent accidental overlap between workstreams.

## Implemented on the `favour` branch

### Detection workstream

Official team-facing detector:

```python
from .screening import full_detector

decision = full_detector(message)
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

The detector currently covers:

- openly written prompt-injection instructions
- suspicious instructions hidden in HTML/CSS
- Base64-encoded instructions
- zero-width/invisible-character disguises
- selected Unicode look-alike/confusable characters

Comparison adapters are also available:

- `no_screening_detector`: baseline evaluation only
- `original_detector`: original/unmodified message rules
- `full_detector`: original + disguise-revealing transforms

The older name `favour_detector` is a temporary compatibility alias only.
New integration code should use `full_detector`.


## Favour-owned validation tools now included

These tools validate the detector without taking over teammate-owned components.

- `run_detector_integration_tests.py` runs real synthetic `.eml` files through
  intake + `full_detector` and checks PASS / REVIEW / BLOCK behavior.
- `generate_detector_pilot.py` creates the fixed 26-case DEVELOPMENT pilot:
  6 genuine, 4 plain attacks, and 16 disguised variants.
- `detector_replay.py` replays a labelled CSV through `none`, `original`,
  and `full` detector configurations and exports:
  - attacks flagged
  - missed attacks
  - genuine enquiries held
  - false-alarm rate
  - processing failures
  - screening runtime
  - results by disguise type and base attack

For the final 650-case replay, this detector tool can consume the correctly
labelled university-email CSV once the team supplies it. It does not fabricate
AI drafting cost, reviewer minutes, draft accuracy, action-denial counts, or
attack-goal success.

## Chinaza: email intake and AI drafting integration

Existing files such as `ingest.py` and `drafting.py` remain the intake/drafting
boundary. The detection branch must not replace mailbox retrieval, Graph
authentication/polling, or AI provider logic.

Detector requirement from intake:

- preserve `raw_body` so hidden HTML evidence is not lost
- provide `inspection_text` for security inspection
- provide `student_text` separately for drafting after PASS

## Amarachi: verdict/security handling integration

The detector only returns a decision. It does not implement the final
application behavior for all verdicts or security actions.

Integration point:

```text
full_detector(message)
       |
       v
ScreeningDecision
       |
       v
[verdict/security handling component]
```

That component should consume the shared verdict rather than duplicate detector
rules.

## Other teammate-owned components: placeholders only

Exact ownership should be confirmed by the team before implementation.

### Action permission checker placeholder

Expected behavior from the proposal:

- deny prohibited synthetic record reads
- deny external transfers
- deny unauthorized send actions
- log denied mock actions
- work even when called directly rather than only through the detector

The detector does **not** implement these action permissions.

Suggested future interface only:

```python
def authorize_action(action_name: str, context: dict) -> ActionDecision:
    ...
```

### Dataset/replay placeholder

The formal evaluator should call the shared detector interfaces rather than
copying detector logic.

Suggested use:

```text
configuration 1 -> no_screening_detector
configuration 2 -> original_detector
configuration 3 -> full_detector + team's output/action checks
```

Important: the current scientific 650-case JSONL in the repository does not
match the university-email dataset described in the project proposal. Do not
silently use it as the final proposal evaluation set.

### Review UI placeholder

The future review screen should consume `ProcessingResult` and display:

- original email
- verdict
- reason/evidence
- generated draft only when drafting was permitted

The detection branch does not implement the UI.

## Rule for future integration

Do not duplicate prompt-injection rules in other modules. Call
`full_detector(message)` and use the returned `ScreeningDecision`.

If a shared input/output shape must change, agree on the change before editing
`models.py`, `pipeline.py`, or teammate-owned modules.
