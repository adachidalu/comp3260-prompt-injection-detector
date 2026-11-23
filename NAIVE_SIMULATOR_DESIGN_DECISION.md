# Design decision: a deliberately naive teaching simulator

**Scope:** COMP 3260 fictional university Enrolment Services assistant.
**Branch:** Naza-Branch; this note does not authorize merging to main.

## What problem does this solve?
The team's existing offline `MockDrafter` is intentionally cautious, and the
OpenAI provider is a real model trained to resist some malicious instructions.
Neither is ideal for a predictable classroom demonstration of the *effect*
of allowing untrusted text to control a response.

## Options considered
| Option | Pro | Con |
| --- | --- | --- |
| OpenAI model | Real language-model evidence | May be resistant, costs money, model behavior varies |
| Small local open-weight model | Real local generation | Hardware/setup burden; also may be instruction-tuned |
| Scripted naive simulator | Free, repeatable, straightforward | Not evidence about real model prompt-injection susceptibility |

**Decision:** Implement option 3 as an explicitly labelled **teaching mode**;
retain the original mock and OpenAI options. For research conclusions about
language-model vulnerabilities, use a real model and independently assessed
outcomes, or limit conclusions to screening metrics.

## Where it lives
- `email_assistant/naive_simulator.py`: `NaiveTeachingDrafter.generate(message, policy_text)`
- `email_assistant/batch_dashboard.py`: optional provider in Explorer and batch UI
- `streamlit_app.py`: optional provider in individual email UI
- `replay_university.py` and `email_assistant/cli.py`: provider `naive`
- `tests/test_naive_teaching_simulator.py`: regression cases

## Exact security boundaries
- The simulator reads **only `IncomingEmail.student_text`** and the supplied
  fictional policy. It sees no benchmark labels, target answers, metadata,
  private record fixtures, or hidden-only HTML payloads.
- It has **no** mailbox, HTTP, database, message-send, or tool APIs.
- Some attack phrases cause it to write demonstrably incorrect drafts.
  Private identifiers it emits are explicitly **fabricated canaries**,
  not retrieved records. Send claims are false strings, not actions.
- With the same simulated provider held fixed, the team can compare
  detector/output-check *flow* across Phase 1 / Phase 2 / Phase 3.
- The full detector and the output check are not bypassed in protected mode.
  This class is not a production-safe substitute for an LLM.

## Research-integrity rule
**Never** report success/failure of this script as the real-world attack
success rate of an OpenAI or other LLM. Its failures were intentionally
programmed, so comparing them is a sanity check for our architecture.
Avoid claiming that all disguised cases will induce simulated compliance;
the simulator intentionally has limited text understanding.

Formal reporting should separate:
1. Detector-only hold/false-positive metrics on the held-out dataset.
2. Teaching simulator control-flow demonstrations (not LLM metrics).
3. Real language-model draft quality and attack-goal outcomes, **only after
   a real model is actually called and cases are independently reviewed**.
4. Action-denial metrics **only after** the independent action authorization
   component exists and is tested.

## Example
In Streamlit choose **Run all 650 emails**, select a small smoke preview and
`Naive teaching simulator (not AI)`. This makes no API calls.

In the terminal, the optional same-backend check is:

```powershell
python -m unittest discover -s tests -v
python replay_university.py --provider naive --max-cases 10 --results-out naive_preview.jsonl --summary-out naive_preview.json
```

Use the existing `MockDrafter` for reproducible detector evaluations and the
OpenAI adapter for separately approved, limited real-model studies.

**Status at authoring:** implementation and regression tests committed to
`Naza-Branch`. Fresh local end-to-end test and Streamlit smoke run pending.
