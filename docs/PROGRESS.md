# Progress and next task

## Current state

- Product: ProfitLab, a local SEC earnings-growth research experiment.
- Implementation status: not started; repository contains planning documents only.
- Next task: **T01 — Bootstrap the application and runnable inspection interface.**
- Latest verified task: none.
- Last runnable demo: none; commands in the plan are future acceptance contracts.
- Decisions: Python + uv; Pydantic; Pydantic AI; configurable OpenAI-compatible Chat Completions provider; separate Jev API; FastAPI/Jinja local UI; local artifacts and SQLite.
- Scope: up to four fiscal years of 10-Ks; common-share earnings and diluted EPS, with supporting share-count information. Actual investment return is outside this version.
- Current external blockers: none for starting T01. Live stages later need SEC contact identification, a TypeSafe API key, and an OpenAI-compatible provider/model configuration.

## Task tracker

Use `TODO`, `IN_PROGRESS`, `DONE`, or `BLOCKED`. Keep local acceptance and live verification separate. Initially no check has run.

| Task | Deliverable | Local status | Live verification |
| --- | --- | --- | --- |
| T01 | uv project, CLI, local UI, offline demo skeleton | TODO | Not applicable |
| T02 | Pydantic contracts, fixtures, persistent run storage | TODO | Not applicable |
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

Replace this section after each task:

```text
Task:
Implemented:
Commands executed and results:
Demo run ID:
Server command:
Browser URL and click path:
Expected visible result:
Automated checks:
Browser checks:
Live checks:
Known limitations / blockers:
Files changed:
Next task:
```

## Durable decisions / deviations

- Planning baseline dated 2026-09-17. Dependency versions must be selected, recorded, and locked in T01; no untested version numbers are prescribed.
- Chunk default: approximately 1,500 tokens with 180-token prose overlap, subject to T14 evaluation.
- Full trace means observable messages, prompts, tool arguments/results, model outputs, service requests, and explicit decisions. It does not imply access to a model's private reasoning.

## Live verification ledger

Add date, provider, actual model ID, command, run ID, outcome, and unresolved issue for each live check. Never store credentials here.

No live checks executed.
