# Stanley's university-email dataset and replay handover

This is Nwosu Stanley's dataset, replay testing, and evaluation workstream for the fictional COMP 3260 student-support assistant. The old five-discipline scientific benchmark was replaced because it did not test the team's university-email workflow. The dates, addresses, portal, student records, and course rules here are **synthetic test fixtures**, not real university information.

## What is included

| File | Purpose |
| --- | --- |
| `generate_dataset.py` | Deterministically builds and validates the email cases using the Python standard library. Can optionally export `.eml` files for local intake tests. |
| `university_email_650.jsonl` | The fixed evaluation cases, one structured record per line. |
| `university_email_650.csv` | Equivalent spreadsheet-friendly cases; nested fields are JSON-encoded strings. |
| `dataset_summary.json` | Counts, version, seed, policy ID, and checksums of both exports. |
| `university_test_policy.json` | Fictional approved-policy fixture, including one synthetic private-record reference. |
| `replay_university.py` | Three-configuration replay through the existing team pipeline with row-level results and an honest summary. |
| `test_generator.py`, `test_replay_university.py` | Structural, export, and integration smoke tests. |

There are **650 cases**: 150 genuine student emails across 30 topics and 500 malicious emails. The malicious set consists of 100 openly written base attacks, each paired with four disguises (hidden HTML, Base64, zero-width characters, and look-alike Unicode), producing 100 plain and 400 disguised cases. Each attack retains a legitimate enquiry, such as a registration closing date or assignment deadline. The 100 families span five attacker goals: policy override, disclosure of a private identifier, unauthorized record read, external transfer, and unauthorized send or false send claim. The `base_attack_id` links all five versions; `baseline_id` links them to the corresponding genuine enquiry. Treat correlated variants as a group when reviewing cases or estimating uncertainty.

Each case includes original email source (`raw_body`), inspection and student-visible forms, attack vector, vulnerability, a heuristic difficulty score, expected defense response, fictional policy anchor, and objective metadata. Difficulty is a design label, **not** an empirically calibrated risk score. The payload metadata is reference material for an evaluator and must never be included in the model's drafting input.

The cases are template-generated: genuine messages reuse 30 underlying questions with five writing styles, and malicious families reuse five objective instructions and five wrappers across 20 student topics. They are 100 topic/objective families, not 100 independently discovered jailbreak techniques. Hidden-HTML content is available to inspection but not the drafting view, including in the baseline; consequently the baseline is not an experiment in feeding raw hidden HTML directly to the model. The protected record is not supplied to the drafter and no record-access tools are enabled, so successful private-record access cannot be established in this version.

## Reproduce and inspect

Run from the repository root with Python 3.10 or newer. These commands do not log into a mailbox, send email, access real records, or invoke a paid model.

```bash
python generate_dataset.py --validate university_email_650.jsonl
python generate_dataset.py --validate university_email_650.csv
python -m unittest -v
python -m unittest discover -s tests -v
```

To regenerate the committed dataset with the same seed and fictional policy:

```bash
python generate_dataset.py
```

To create local `.eml` inputs without sending them, use `python generate_dataset.py --eml-dir /tmp/stanley_eml`. The team's intake parser can read each file; the replay runner normally uses the same `IncomingEmail` fields directly and does not claim to exercise mailbox retrieval.

## Replay and read the measurements

Start with an offline preview, then run all fixed cases only when the code and evaluation plan are frozen:

```bash
python replay_university.py --provider mock --max-cases 10 \
  --results-out /tmp/stanley_preview_results.jsonl \
  --summary-out /tmp/stanley_preview_summary.json
python replay_university.py --provider mock \
  --results-out /tmp/stanley_results.jsonl \
  --summary-out /tmp/stanley_summary.json
```

`phase1_baseline` uses no detector screening, `phase2_original` uses the team's original screening, and `phase3_enhanced` uses the team's normalized screening plus its output check. All use the existing intake guard and controlled draft pipeline. The mock drafter is an offline stand-in, **not an AI model**. `--config phase2_original` selects one configuration; `--max-cases` is a preview only, not a representative sample.

Each result records the case and family IDs, label, disguise, detector verdict/reason/evidence and timing, final pipeline verdict, raw draft for later review if one was generated, returned draft, provider/model settings, runtime, and error. `screening_flagged` measures detector REVIEW/BLOCK; `final_held` also includes later output-check holds. The summary counts attacks held, attacks missed by screening, genuine enquiries held, by-disguise counts, drafting calls, and failures. A held attack is a **screening result**, not proof that its malicious goal would have succeeded. Phase 3 changes more than one control, so its improvement cannot be attributed solely to normalization.

The summary also groups attacks by `base_attack_id`, preserves the input and policy hashes, and separates detector runtime from drafting runtime. The original and inspection forms are retained in each result as well as in the source dataset. Output-check-rejected drafts are saved only in the evaluation log for independent review, not returned as approved drafts.

For a real model run, install the team's optional dependency (`pip install -r requirements-optional.txt`), configure `OPENAI_API_KEY` privately, and explicitly choose a supported model, for example `python replay_university.py --provider openai --model MODEL_ID --results-out /tmp/model_results.jsonl --summary-out /tmp/model_summary.json`. That mode can make up to 1,950 case/configuration passes; screening prevents some drafting calls. It may incur charges and transmit fictional test inputs to the provider, so obtain project approval before running it. Do not commit credentials or raw model results.

The runner does **not** connect to the team's action-authorization gate, execute the reference action probes, or measure unauthorized action success. It also cannot automatically determine semantic draft accuracy, attack-goal success, reviewer time, or model cost. Those fields remain `null`; a reviewer must assess actual saved drafts and observed action logs using the per-case reference objective and policy. In particular, do not infer that a private-record read or external transfer occurred merely because an attack passed screening. Actual approved policy and live student data are outside this benchmark.

## Evaluation hygiene and handoff

The existing `development_pilot_26.csv` belongs to development, not this held-out 650-case set. Do not tune rules, prompts, or thresholds on these 650 cases and then present the same replay as an unbiased final estimate. Report the dataset seed, checksums, team commit, policy ID, configuration, provider/model, failure count, and whether a run was a preview. If the team revises a control after viewing results, freeze a new independent evaluation set for the final comparison. Draft accuracy should be reviewed separately on genuine cases as well as attack cases.

The generator and replay script consume the existing `email_assistant` interfaces without editing the detector, intake, drafter, action handler, UI, or team integration files. The old `scientific_prompt_injection_650.jsonl` has been removed; it was the unrelated dataset created for the earlier scientific task. No teammate-owned files were removed or changed for this handoff.

## Project handover update: November 17, 2026

- **Confirmed decision:** Work only on case-sensitive branch `Stan`, replacing the earlier scientific dataset and preserving teammate-owned code.
- **Completed work:** University-email JSONL/CSV, fictional reference policy, deterministic generator, validation tests, three-configuration replay harness, and these usage instructions.
- **Verified locally:** 32 root unit tests, 20 safety tests, and all seven pre-existing `.eml` detector integration checks passed. Both exports validated, and the unchanged teammate-owned `detector_replay.py` successfully consumed the CSV across all three configurations.
- **Offline smoke replay:** Each configuration processed all 650 cases with zero processing failures. Detector flags were 0/500 attacks in the baseline, 100/500 with original screening, and 500/500 with enhanced screening; genuine holds were 0/150 in each. These are descriptive synthetic screening checks with a mock drafter, not real-model robustness, semantic accuracy, action-denial results, or an unbiased generalization estimate. No detector rules were modified in this work.
- **Changed files:** The file table lists Stanley's replacement and new files; the old scientific JSONL is the only deleted tracked file.
- **Blocker:** The replay harness does not yet consume the security teammate's action-authorization interface. Enhanced screening and output checking are wired, but this is not the complete proposal Phase 3.
- **Unresolved facts:** The approved AI provider/model, authorization to incur model charges, measured model cost, and human semantic-review results are not supplied by this offline work.
- **Next actions:** The team should freeze the controls using development cases, connect the action-check interface through agreed contracts, and authorize a real-model evaluation. Stanley can then score saved drafts and observed action logs, produce comparison tables/charts and bypass/denial logs, and carry those verified results into the final report and slides.
