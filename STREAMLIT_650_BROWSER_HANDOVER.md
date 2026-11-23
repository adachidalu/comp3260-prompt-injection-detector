# Chinaza: Streamlit dataset explorer and 650-case batch runner

## Purpose
Use one browser interface to browse Stanley's fixed university-email benchmark
and execute its three replay configurations. No 650 individual .eml uploads and
no terminal replay commands are required.

## Start
From the repository root, on `Naza-Branch`:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Open the Streamlit app and choose:
- **Explore 650-email dataset**: filter by classification, topic, disguise, and attack goal;
  view raw/visible email representations, and run full screening on one case.
- **Run all 650 emails**: choose 650 emails and "All three modes," then click
  **Run evaluation**. The normal mode is offline mock; it does not call any AI API.
  The first-N options (10/26/100) are smoke previews and must not be reported
  as final evaluation results.

The browser displays verdict counts, false-alarm counts, per-disguise
results and a comparison chart. The **Source dataset** section also lets
reviewers download Stanley's original JSONL, CSV and matching fictional policy.
After a run, download all individual results as JSONL, the complete summary
as JSON, or a metrics table as CSV.

## Design decisions and alternatives
- **Selected: reuse Stanley's JSONL + `replay_university.py`**.
  This keeps labels and grouping identifiers and avoids two independent
  implementations of evaluation logic.
- **Rejected: 650 .eml uploads as the primary flow**.
  Valid for intake testing but cumbersome and would discard evaluation metadata.
- **Rejected: separate one-off Streamlit detector loop**.
  It could accidentally diverge from the validated replay and omit failures.
- **Kept: existing single-.eml interface** for showing MIME intake separately.
  The JSONL replay creates `IncomingEmail` directly; it does **not** test
  Outlook/Graph retrieval or the .eml MIME parser.

## Security and research restrictions
- All cases and the paired approved policy are fictional. The full dataset
  must be validated against `university_test_policy.json`; do not replace
  it with unrelated date values.
- The benchmark's `metadata`, `expected_policy_anchor` and labels are
  never passed to the drafting provider; only the standard `IncomingEmail`
  and approved policy are provided to `process_message`.
- Baseline/original evaluation modes intentionally disable parts of protection.
  Use them for **synthetic evaluation only**, never live email handling.
- The normal Streamlit single-message path uses full screening + output checks.
- Offline mock is the default. OpenAI batch use requires existing API credentials,
  a model, and explicit acknowledgement of billable calls. Results from the
  mock are **not AI robustness evidence**.
- Exported results may include raw fictional attack instructions. Treat them
  as test artifacts; do not feed them back as trusted policies.
- The team's independent mock action-authorization gate is **not** integrated.
  `phase3_enhanced` is not the full proposal's Phase 3. Its security outcomes
  are detector/pipeline measurements, not proof of attempted action denials.
- Do not tune detection rules using the held-out 650 cases and claim an
  independent final score. Freeze a separate held-out set after any tuning.

## Files changed by Chinaza
- `email_assistant/batch_runner.py` - shared chunked replay+summary orchestration.
- `email_assistant/batch_dashboard.py` - browser filters, progress, results, downloads.
- `streamlit_app.py` - navigation to both workflows.
- `tests/test_batch_runner.py` - automated regression tests for count/mode validation.

The `Stan`, `favour`, and `main` branches remain untouched by this work.

## Verification and next steps
Run:
```powershell
python -m unittest discover -s tests -v
python -m unittest -v
python -m streamlit run streamlit_app.py
```

Then verify in the browser:
1. Explorer filters case G001 and one disguised A-case correctly.
2. A genuine email produces a permitted mock draft under enhanced screening.
3. A disguised attack does not release an unsafe draft.
4. 10-case preview with three modes records exactly 30 evaluations.
5. Full offline 650-by-three run records exactly 1,950 results, charts update,
   and exported files contain the same counts as the summary.

GitHub commits have been created; a fresh local runtime/Streamlit browser
smoke test is still needed before asserting end-to-end validation.
