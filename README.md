# Chinaza's email processing + AI integration starter

This is a **local, synthetic-data-only** learning scaffold for COMP 3260. It is not a production security detector.

## What is implemented

1. Load `.eml` messages from a local folder, including plain-text and HTML bodies.
2. Preserve original markup and create separate extracted text for the detector; best-effort student text for a draft.
3. Convert a local JSON fixture shaped like a Microsoft Graph message (no Outlook login yet).
4. Call a replaceable detector function returning `pass`, `review`, or `block` with reason/evidence.
5. Draft only for `pass`; exceptions, missing detector, or screening uncertainty go to `review`.
6. Generate offline template-based sample draft, or optionally an actual AI draft through the OpenAI Responses API.
7. Run an illustrative output check and optionally store outcomes in SQLite/JSONL.
8. No message sending, record access, attachments, real mailbox sync, or external transfer.

**Important:** `demo_detector` is an educational placeholder, NOT Favour's completed detection rules. `strict` is the default to avoid implying this prototype is safe without the real detector. The output check is illustrative, NOT a substitute for the team's eventual action permission checker.

## Quick start (Python 3.10+)

Open a terminal in this folder:

```bash
python -m unittest discover -s tests -v
python -m chinaza_email.cli --detector demo --provider mock
```

Expected results for the three example messages:

- `01_registration.eml` -> PASS and an offline example draft.
- `02_plain_attack.eml` -> BLOCK, no draft.
- `03_hidden_html.eml` -> BLOCK (obvious attack text), no draft.

Use safer default mode to verify unconfigured detector holds everything:

```bash
python -m chinaza_email.cli
```

Export a results file / local SQLite log:

```bash
python -m chinaza_email.cli --detector demo --db local_results.sqlite --json-out results.jsonl
```

Run one fake Graph JSON message through the same pipeline:

```bash
python -m chinaza_email.cli --inbox examples/empty --graph-json examples/graph/graph_sample.json --detector demo
```

## Optional real AI call (not needed to learn or run tests)

First install the SDK and set environment variables in your own shell, not in code:

```bash
pip install -r requirements-optional.txt
# macOS/Linux: export OPENAI_API_KEY='your key'; export OPENAI_MODEL='your chosen model'
# PowerShell: $env:OPENAI_API_KEY='your key'; $env:OPENAI_MODEL='your chosen model'
python -m chinaza_email.cli --detector demo --provider openai
```

This mode uses the provider's API and may incur cost. Use only synthetic examples; never upload real student records. The team must select and fix the model/version/settings before formal evaluation. API calls cannot be verified by the included offline tests.

## How your code fits with other team members

- Favour's detector should replace `strict_unconfigured_detector` with an adapter that takes `IncomingEmail` and returns `ScreeningDecision(verdict, reason, evidence)`.
- Review UI reads `ProcessingResult`; only results with verdict `pass` have a draft.
- Dataset/replay owner can call `parse_eml` or `parse_graph_message` and `process_message` repeatedly; CSV IDs can be mapped to `source_id`.
- Action checker owner must control mock record reads/transfers independently, including direct requests. **Do not expose tools to the drafting model.**

## Microsoft Graph integration next (not implemented yet)

Read-only Outlook intake uses `GET /me/mailFolders/{id}/messages/delta`, following `@odata.nextLink` until `@odata.deltaLink`, and saving that delta token for the next 1–2 minute poll. A body-reading integration generally needs suitable mailbox consent (e.g., delegated `Mail.Read`); `Mail.ReadBasic` may not provide the message body. Authentication and permission approval are outside this starter. The `parse_graph_message` function accepts the resulting JSON record after an authorized fetch.

Docs: https://learn.microsoft.com/en-us/graph/delta-query-messages

## Learning checkpoints

1. Read `chinaza_email/ingest.py`: Why do we preserve HTML markup AND extract text?
2. Read `screening.py`: What happens when the detector isn't connected?
3. Read `pipeline.py`: Why must we check before calling `drafter.generate`?
4. Read `drafting.py`: What is the difference between MockDrafter and OpenAIDrafter?
5. Run tests, then add one extra fictional email and describe its verdict.
