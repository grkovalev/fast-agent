# Progress and next task

## Current state

- Product: ProfitLab, a local SEC earnings-growth research experiment.
- Implementation status: T02 complete; validated contracts, SQLite/immutable storage, fixtures and artifact inspection.
- Next task: **T03 — Persistent trace recorder and trace viewer.**
- Latest verified task: T02 local acceptance.
- Last runnable demos: `demo-t02` and `two-years-t02`, setup plus stored fixture inputs.
- Decisions: Python + uv; Pydantic; Pydantic AI; configurable OpenAI-compatible Chat Completions provider; separate Jev API; FastAPI/Jinja local UI; local artifacts and SQLite.
- Scope: up to four fiscal years of 10-Ks; common-share earnings and diluted EPS, with supporting share-count information. Actual investment return is outside this version.
- Current external blockers: none for offline implementation. Live stages later need SEC contact identification, a TypeSafe API key, and an OpenAI-compatible provider/model configuration.

## Task tracker

Use `TODO`, `IN_PROGRESS`, `DONE`, or `BLOCKED`. Keep local acceptance and live verification separate. Initially no check has run.

| Task | Deliverable | Local status | Live verification |
| --- | --- | --- | --- |
| T01 | uv project, CLI, local UI, offline demo skeleton | DONE | Not applicable |
| T02 | Pydantic contracts, fixtures, persistent run storage | DONE | Not applicable |
| T03 | Trace recording, conversation/tool viewer, export | TODO | Not applicable |
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

Task: T02 — Pydantic contracts, fixtures, and persistent run storage.
Implemented: versioned contracts split by domain; Decimal string serialization;
explicit metric missingness; probability, fiscal interval, identity and unit checks;
SQLite schema v1 run/artifact index; atomic temporary-file publication; immutable
content checks and read-time SHA-256 verification; run-scoped typed reference
validation, evidence quote/anchor/hash checks, candidate grouping key checks and
final report selection checks. Added four synthetic annual HTML inputs, ticker and
submissions responses, two-year scenario, test-only gold answers, inspect CLI and
escaped raw artifact pages. Existing T01 summaries remain readable.

Commands executed and results:
- `uv run profitlab demo --through T02 --run-id demo-t02`: passed.
- `uv run profitlab inspect demo-t02`: passed; manifest and nine indexed artifacts.
- `uv run profitlab demo --through T02 --scenario two-years --run-id two-years-t02`: passed.
- `uv run pytest tests/task_gates/test_t01.py tests/task_gates/test_t02.py`: initially
  caught a source-ID self-reference defect; corrected, then 9 passed.
- Final `uv run pytest`: 10 passed; one upstream Starlette/AnyIO deprecation warning.
- Final `uv run ruff check .` and `git diff --check`: passed.
- `uv run profitlab serve`: started at localhost:8000; server left running.

Browser URLs: http://127.0.0.1:8000/runs/demo-t02 and
http://127.0.0.1:8000/runs/two-years-t02.
Click Saved artifacts → manifest → back → fixture-metadata (decimal string 1.00,
USD and scales) or annual-2025 (raw HTML with explicit financial units).
Automated checks create new repository/app instances to verify restart persistence,
check immutable conflicts and corruption, prohibit network, and prohibit runtime
reads of gold/test fixtures. Missing and selected zero values stay distinct.
Browser checks: CUA inventory has no browser connector; attempted native Safari,
which returned “Computer Use permissions are not granted.” Visual verification
and manual server-restart browser inspection remain unrun.
Live checks: not applicable; no external services called.
Limitations: these are fixture inputs, not extracted/selected financial facts.
Manifest covered_years remains empty. A run-ID reservation survives interrupted
creation; do not overwrite it. Stage status updates/recovery arrive in T13.
Reference validators will grow with parsing/extraction services, including inline
XBRL contexts. Trace redaction and export are T03 work. Required uv commands
needed escalation for access to the existing uv cache; dependencies/lock unchanged.
Next task: T03.

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
