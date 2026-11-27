# Local + team-wide deployment plan — COMP 3260

## Chosen architecture (and alternatives)

The same **Naza-Branch** code is used locally in VS Code and remotely on one
private Streamlit server. Each environment has its **own API key** (same model
or different supported models as deliberately configured).

| Option | Advantages | Drawbacks | Team decision |
| --- | --- | --- | --- |
| Each teammate runs locally | Independent development | Each needs Python, dependencies and an authorized API key | Chinaza's local setup |
| One private Streamlit Community Cloud app | Shared link, no credential distribution, cheap to maintain | Needs GitHub admin, secrets setup, app access controls | Recommended for team |
| Host on a separate cloud/server | More resource, access and cost controls | Requires deployment maintenance | Fallback if Community Cloud limits become a problem |

**Never push a working key to GitHub or send it in group chat.**
The sample secrets file is a template, not usable credentials.

## Which UI is which?
- `streamlit_app.py`: the established single synthetic email, dataset explorer,
  and 650 × 3 offline/model benchmarking workflows.
- `pages/1_Live_TRU_Drafting.py`: Favour-derived real OpenAI drafting using
  **only official tru.ca web search**. Protected full screening, draft output
  safety, and human review are mandatory. **No real student data**.
- `email_assistant/tru_web_drafting.py`: isolated web-grounded provider.
- `university_test_policy.json`: fixed fictional 650-case evaluation policy,
  **not** a live official university policy.

This is a **draft-only workflow** and not a multi-turn chat assistant; the
system does not send messages or retrieve student records.

## Local Windows setup (Naza-Branch)

```powershell
git switch Naza-Branch
git pull origin Naza-Branch
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Open `.streamlit/secrets.toml` in VS Code; set your **own authorized**
`OPENAI_API_KEY` and a specific provider-supported `OPENAI_MODEL` with
Responses API web search support. Do not send or commit the real key.
Then:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Select **Open protected live TRU AI drafting test**, then enter a fictional
question, tick the billing acknowledgement, and review the unsent draft.
Run a genuine question and an injection case. The 650-case offline modes do not
need a key.

## Shared, restricted Streamlit Community Cloud

Only the GitHub repository owner/admin needs to do these deployment steps:

1. Sign in to https://share.streamlit.io/ and authorize GitHub access.
2. Deploy `adachidalu/comp3260-prompt-injection-detector`, select a reviewed
   deployment branch (temporarily `Naza-Branch` for staging, later `main`
   after the team's pull request), entrypoint `streamlit_app.py`.
3. Choose Python 3.11 or newer compatible with the repository dependencies.
4. In **Advanced settings / App settings -> Secrets**, set the same keys as
   the template, but use a separate **deployment-only key**. Do not copy the
   local secrets file into GitHub.
5. Set the app to **private** and invite only authorized teammates via email.
   Do not publish a public billable API-powered prototype.
6. Enable usage/budget monitoring and limited API access in the OpenAI project.
7. Open the hosted app as a teammate; verify the live draft and the offline
   650-case explorer. The UI should never display the API secret.

If a private app is unavailable on your plan or team access requirements
cannot be enforced, stop; use an access-controlled alternative host rather
than making the app public.

## Security and cost boundaries

- Deployment secrets reside on the server; visitors need only the restricted
  app link and access approval, **not the API key**.
- The Cloud app is separately billed under the deployment's API project.
- Start with 1–3 fictional cases to verify the provider and supported model.
  Web search API/tool calls may increase costs.
- Don't run the full 650 × 3 model replay for onboarding; offline screening
  comparison is sufficient for that demonstration.
- Current Streamlit batch UI is synchronous. A failed network request cannot
  be resumed exactly; a future improvement is incremental checkpoints.
- The live mode has no connection to Outlook/Graph, student systems, or email
  delivery. No actual records may be submitted.
- `TRUWebDrafter` rejects responses without an official TRU source URL, but
  the *presence* of a source does not guarantee every factual claim is correct.
  Staff must verify any factual output.

## How to verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest -v test_tru_web_naza.py
```

Expected:
- Missing credentials: live page shows a setup message, no request sent.
- Good synthetic question: a staff-review draft and official tru.ca sources
  appear when the configured model/tool call succeeds.
- Unsupported source, model/API error, or an unsafe message: no draft released.
- Main 650-case and naive simulator paths remain unchanged.
- Real API run is separately approved, documented, and billed.

## Branch coordination

As of this implementation, `favour` and `Naza-Branch` have divergent changes.
We **selectively ported** Favour's live web-grounded path instead of overwriting
Naza's dashboard, no-screening comparison, or naive teaching simulator.
The team should code-review these changes and reconcile Favour's newer
security controls before the final pull request to `main`.

**Completion status:** Branch code and setup instructions committed; the
actual Cloud app and real OpenAI API test require the deployment admin's
configuration. Do not claim hosting or billable API access are already active.
