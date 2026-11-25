# Team Integration Boundaries and Current Architecture

This file records the current shared integration points so teammate-owned rules
are reused rather than copied.

## Maintained application path

New application code should use the deployable `email_assistant` package.

```text
synthetic email / Graph fixture
        |
        v
email_assistant.ingest + intake_guard
        |
        v
Favour full_detector
        |
        v
Amarachi verdict_handler
        |
        +---- REVIEW/BLOCK ----> no drafting
        |
        v
Chinaza MockDrafter / OpenAIDrafter
        |
        v
Chinaza policy-bound output checks
        |
        v
Amarachi output_validator
        |
        v
staff-review draft only
```

The Streamlit app uses this path through:

```python
from email_assistant.pipeline import process_message
```

The legacy root `pipeline.py` is now only a compatibility wrapper so older
imports do not silently bypass the integrated controls.

## Favour: prompt-injection detection

Official detector:

```python
from email_assistant.screening import full_detector
```

It returns a shared `ScreeningDecision` and covers:

- openly written prompt-injection instructions
- hidden HTML/CSS
- Base64-encoded instructions
- zero-width/invisible characters
- selected Unicode look-alike/confusable characters

Evaluation adapters remain:

- `no_screening_detector`
- `original_detector`
- `full_detector`

Do not copy detector rules into other modules.

## Chinaza: intake and controlled drafting

The maintained package path preserves:

- raw email/HTML for security inspection
- separate inspection and student-visible text
- guarded MIME/attachment/size handling
- mock and OpenAI drafting adapters
- policy-bound output checks
- no real send capability

The OpenAI adapter still runs with `tools=[]` for the controlled experiment.

## Amarachi: verdict, output, action, and audit controls

The root teammate modules remain their source of truth:

- `verdict_handler.py`
- `output_validator.py`
- `action_authorizer.py`
- `db_manager.py`

`email_assistant/security_controls.py` adapts these modules for the application
without duplicating their rule logic.

Current integration:

- PASS/REVIEW/BLOCK behavior is applied before drafting.
- The privacy output validator runs after the existing policy-bound draft check.
- Mock action authorization is exposed in Streamlit for demonstration.
- Verdicts and mock action decisions can be logged to local SQLite.
- Database failures do not weaken a REVIEW/BLOCK decision.

The application performs no real student-record read, external transfer, or
email send.

## Stanley: university-email dataset and replay

The repository now contains the university-email evaluation artifacts:

- `university_email_650.csv`
- `university_email_650.jsonl`
- `university_test_policy.json`
- `replay_university.py`
- `STANLEY_DATASET_AND_REPLAY.md`

The obsolete scientific benchmark warning from the earlier development branch
no longer applies to current `main`.

The replay uses `email_assistant.pipeline.process_message`, so pipeline output
checks are shared with the application rather than reimplemented.

## Streamlit review UI

`streamlit_app.py` now demonstrates:

- guarded synthetic email intake
- detector configuration comparison
- PASS / REVIEW / BLOCK results
- controlled mock/OpenAI drafting
- integrated output validation
- mock action permission checks
- local audit counts

The UI remains review-only and does not connect to a real mailbox or records
system.

## Audit database

`db_manager.py` creates `security_audit.db` when audit logging is used.

The repository ignores `*.db` and `*.sqlite`, so the local audit database
must not be committed.

## Regression tests

Run from the repository root:

```powershell
python -m unittest test_package_smoke.py test_security_integration.py -v
python -m unittest discover -s tests -v
```

The integration regression tests verify:

- a genuine email can reach drafting
- prompt injection is held before drafting
- a deliberately leaky draft is held by the privacy validator
- policy reads are allowed while record reads/transfers/sends are denied
- verdict and action audit records are written to SQLite

## Rule for future work

Keep each security concern independent:

```text
intake validation
-> prompt-injection detection
-> application verdict policy
-> drafting
-> output validation
-> action authorization
-> audit
```

A downstream control must not turn REVIEW or BLOCK back into PASS.

Future TRU-grounded knowledge retrieval should be added as a drafting knowledge
source after these controls, not as a replacement for the detector, output
validator, or action authorizer.
