# Progress and next task

## Current state

- Product: ProfitLab, a local SEC earnings-growth research experiment.
- Implementation status: T03 complete; persistent trace recording, filtered viewer, redaction and trace export.
- Next task: **T04 — SEC ticker lookup and annual filing discovery.**
- Latest verified task: T03 local acceptance.
- Last runnable demo: `demo-t03`, fixture inputs plus scripted service trace. Earlier T01/T02 demos remain readable.
- Decisions: Python + uv; Pydantic; Pydantic AI; configurable OpenAI-compatible Chat Completions provider; separate Jev API; FastAPI/Jinja local UI; local artifacts and SQLite.
- Scope: up to four fiscal years of 10-Ks; common-share earnings and diluted EPS, with supporting share-count information. Actual investment return is outside this version.
- Current external blockers: none for offline implementation. Live stages later need SEC contact identification, a TypeSafe API key, and an OpenAI-compatible provider/model configuration.

## Task tracker

Use `TODO`, `IN_PROGRESS`, `DONE`, or `BLOCKED`. Keep local acceptance and live verification separate. Initially no check has run.

| Task | Deliverable | Local status | Live verification |
| --- | --- | --- | --- |
| T01 | uv project, CLI, local UI, offline demo skeleton | DONE | Not applicable |
| T02 | Pydantic contracts, fixtures, persistent run storage | DONE | Not applicable |
| T03 | Trace recording, conversation/tool viewer, export | DONE | Not applicable |
| T04 | SEC ticker lookup and filing discovery | TODO | Not run |
| T05 | Filing downloads and anchored source viewer | TODO | Not run |
| T06 | Table-aware chunking and chunk inspector | TODO | Not applicable |
| T07 | Jev and OpenAI-compatible provider adapters | TODO | Not run |
| T08 | Jev relevance screening and coverage recovery | TODO | Not run |
| T09 | Candidate extraction with source validation | TODO | Not run |
| T10 | Candidate reconciliation and coverage selection | TODO | Not applicable |
| T11 | Deterministic annual-growth calculations | TODO | Not applicable |
| T12 | Pydantic AI report agent and citation validation | TODO | Not run |
| T13 | Complete ticker-to-report workflow and run controls | TODO | Not run |
| T14 | Measured chunk-size and screening evaluation | TODO | Not run |
| T15 | End-to-end verification and failure/recovery cases | TODO | Not run |
| T16 | Usability handoff, exports, final reproducibility check | TODO | Not run |

## Instruction for the implementing agent

1. Read this file and the relevant specification before editing.
2. Select the first TODO task whose dependencies are DONE. Resume an IN_PROGRESS task first.
3. Announce the task and its user-visible result. Implement only that bounded task and necessary fixes.
4. Use `uv` for dependencies, scripts, and tests. Preserve `uv.lock`.
5. Run the task's automated checks and its offline demo. Inspect its browser page when browser tooling is available; otherwise record that visual verification remains unrun.
6. Record actual commands, results, artifact/run IDs, and limitations below. Never invent a successful live call or browser inspection.
7. Mark DONE only when the local acceptance criteria pass. A blocked external check stays visibly pending, and compatible later offline work may continue.
8. Stop after the task. Tell the user what to open, what to click, what they should see, and the next task ID.

## Latest task handoff

Task: T03 — Persistent trace recorder and trace viewer.
Implemented: append-only fsynced JSONL trace, run-scoped process locks and ordered
sequence allocation, content-addressed immutable payloads, context-local nested
spans, shared call IDs across attempts, service/tool operation wrapper, duration,
errors and BaseException/cancellation closure. Server startup reconciles open spans
as interrupted; malformed final lines remain on disk with a visible warning and
usable earlier history. Shared redaction handles configured secrets, sensitive
keys/headers, bearer tokens, URL credentials and query tokens before persistence.
Added filtered timeline, one-expansion full request/result loading, standalone
payload JSON/viewer links, copy event JSON, payload/ID search, incremental event
endpoint/polling notification and trace-only JSON/JSONL export. No fabricated model
conversation; scripted operations are labeled pipeline and Synthetic demo.

Commands executed and results:
- `uv run pytest tests/task_gates/test_t01.py tests/task_gates/test_t02.py`: 10 passed.
- `uv run pytest tests/task_gates/test_t03.py`: initially caught a secret echoed in
  the tool label; fixed metadata redaction, then complete suite passed.
- `uv run profitlab demo --through T03 --run-id demo-t03`: passed.
- `uv run profitlab export demo-t03 --output ./exports/demo-t03`: passed; complete
  payloads exported alongside trace.json and events.jsonl.
- Final `uv run pytest`: 13 passed, one upstream Starlette/AnyIO deprecation warning.
- Final `uv run ruff check .` and `git diff --check`: passed.
- `uv run profitlab serve`: started, then stopped and restarted with final changes;
  server left running at localhost:8000.

Open http://127.0.0.1:8000/runs/demo-t03/trace. Expand the failed fixture request,
inspect full arguments/error, and follow its call ID to attempt 2. Expand fixture
read to see the full large result or use Full result JSON/viewer. Refresh preserves
history. Export directory: exports/demo-t03 (ignored runtime output).
Automated gate checks concurrent recorder instances (80 uniquely ordered events),
matching start/end IDs and nested parentage, startup recovery after a truncated
journal tail, cancellation closure, filters, full large payload retrieval, run
scoping, HTML escaping, restart persistence, overwrite refusal and credential scans
across all saved/exported artifacts. Earlier invalid-future CLI gate now uses T04.
Browser checks: CUA inventory contains no browser connector; native Safari returned
“Computer Use permissions are not granted.” Visual expansion/copy/polling checks
remain unrun; HTTP checks are not claimed as visual inspection.
Live checks: not applicable; no external service calls or paid model requests.
Limitations: trace-only export; actual agent conversation hooks start in T07/T12.
Polling announces new matching events with a refresh link. Restart reconciliation
assumes the specified single local server and stopped application workers; it does
not infer remote completion or retry interrupted calls. Future integrations must
pass Settings.redactor() and use the recorder instead of logging raw failures.
Dependencies and uv.lock unchanged. uv commands required escalation for the existing
cache. Next task: T04.

## Durable decisions / deviations

- User preference: default generative provider is OpenAI API at `https://api.openai.com/v1`,
  model `gpt-5.6-luna` for low cost. Set `LLM_API_KEY` locally. Base URL/model
  remain overrideable. Official model docs verified 2026-09-17; live quality and
  account access remain untested until T07. Settings, example, specification and
  README updated; T01 gate and Ruff rerun successfully.

- Planning baseline dated 2026-09-17. Dependency versions must be selected, recorded, and locked in T01; no untested version numbers are prescribed.
- Chunk default: approximately 1,500 tokens with 180-token prose overlap, subject to T14 evaluation.
- Full trace means observable messages, prompts, tool arguments/results, model outputs, service requests, and explicit decisions. It does not imply access to a model's private reasoning.

## Live verification ledger

Add date, provider, actual model ID, command, run ID, outcome, and unresolved issue for each live check. Never store credentials here.

No live checks executed.
