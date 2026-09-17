# Progress and next task

## Current state

- Product: ProfitLab, a local SEC earnings-growth research experiment.
- Implementation status: T05 complete; immutable filing downloads, versioned source blocks/table cells, and sanitized anchored source viewer.
- Next task: **T06 — Table-aware chunking and chunk inspector.**
- Latest verified task: T05 local acceptance; real SEC download/parse passed, visual citation inspection pending.
- Last runnable demo: `demo-t05-v2` (four periods plus amendment, parser html-2). Earlier demos remain readable.
- Decisions: Python + uv; Pydantic; Pydantic AI; configurable OpenAI-compatible Chat Completions provider; separate Jev API; FastAPI/Jinja local UI; local artifacts and SQLite.
- Scope: up to four fiscal years of 10-Ks; common-share earnings and diluted EPS, with supporting share-count information. Actual investment return is outside this version.
- Current external blockers: browser visual inspection lacks Computer Use permissions. SEC contact is configured and live discovery succeeded. Model integrations remain unverified until T07.

## Task tracker

Use `TODO`, `IN_PROGRESS`, `DONE`, or `BLOCKED`. Keep local acceptance and live verification separate. Initially no check has run.

| Task | Deliverable | Local status | Live verification |
| --- | --- | --- | --- |
| T01 | uv project, CLI, local UI, offline demo skeleton | DONE | Not applicable |
| T02 | Pydantic contracts, fixtures, persistent run storage | DONE | Not applicable |
| T03 | Trace recording, conversation/tool viewer, export | DONE | Not applicable |
| T04 | SEC ticker lookup and filing discovery | DONE | SEC discovery passed; visual inspection pending |
| T05 | Filing downloads and anchored source viewer | DONE | SEC download/parse passed; visual citation inspection pending |
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

Task: T05 — Filing downloads and anchored source viewer.
Implemented: controlled `stage <run-id> download|parse` with optional `--filing-id`,
shared SEC limiter and retry owner, one active in-process live SEC operation,
HTML/content/closing-document validation, byte/time limits, and immutable raw
source bytes. Typed source metadata stores hash, bytes, status, URL, content type
and retrieval time. Cache reuse checks metadata/source hashes; failures persist
with exact stage/error and remain visible in Sources and Trace. Initial discovery
filing contracts are preserved; fetch metadata is authoritative in `source-*`
artifacts. Successful stages publish immutable manifest snapshots.

Parser `html-2` preserves visible headings, paragraphs, div-based SEC prose,
captions, footnotes, merged table spans and inline-XBRL IDs. Blocks/cells have
repeatable IDs, DOM locators, header/year/unit associations and original anchors
only when an explicit DOM ID/name exists. Table expansion is bounded. Quotes use
Unicode-whitespace collapse, preserving case/punctuation and raw stored text.
Versioned parsed indexes retain previous derivatives. The viewer uses escaped
text and reconstructed tables, with exact-cell or span-aware row/column
highlighting; no raw HTML is marked safe. Printed page labels remain unknown
rather than inferred. Source pages are run-index scoped, with accession/date/hash,
section paths, local anchors and genuine SEC links; demos have synthetic badges.

Commands/results:
- `uv run pytest tests/task_gates/test_t05.py`: gate passed; final gate has seven
  tests covering full offline service/UI, stable IDs, spans/header IDs, exact
  highlights, quote normalization, scripts, traversal, raw preservation, malformed
  HTML/PDF/403, disconnect retry, byte limits, persistence/cache reuse and errors.
- Final `uv run pytest`: 38 passed; existing upstream Starlette/AnyIO warning.
- Final `uv run ruff check .` and `git diff --check`: passed.
- `uv run profitlab demo --through T05 --run-id demo-t05`: passed initial parser.
- Final versioned demo: `uv run profitlab demo --through T05 --run-id demo-t05-v2`.
- `uv run profitlab stage live-sec-t04 download --filing-id filing-000032019325000079`:
  passed using configured SEC contact; raw Apple 2025 10-K and provenance saved.
- `uv run profitlab stage live-sec-t04 parse --filing-id filing-000032019325000079`:
  passed. Real div-based prose prompted necessary parser support; final result
  has 698 visible blocks, 6,379 cells, 105 original block anchors. All 105 anchors
  were checked against raw DOM IDs/names. EPS tables include original anchors
  `f-72` and `f-410`; this is DOM verification, not a browser scroll check.
- Local server started/restarted with `uv run profitlab serve`, localhost:8000.

Open http://127.0.0.1:8000/runs/demo-t05-v2/sources. Choose the annual income table,
then click its EPS value for one-cell highlight; Row + column includes the label
and year. The edge-case table has merged headers and neighboring years. Open
http://127.0.0.1:8000/runs/live-sec-t04/sources for the saved real 2025 filing;
other discovered live filings remain pending download.

Visual inspection remains unrun: CUA inventory had no browser connector; native
Safari returned “Computer Use permissions are not granted.” Original SEC anchor
existence is verified in saved bytes, but navigation/scrolling on the SEC original
is pending. Parser verification is a one-filing smoke check, not a general accuracy
claim. Hidden facts are excluded from this visible-source parser; extraction of
structured contexts/transformations belongs to T09. Download cache reuse currently
uses per-run immutable artifacts; cross-run archive deduplication is deferred.
Dependencies/uv.lock unchanged. uv commands required existing-cache escalation.
Next task: T06.

## T04 task handoff

Task: T04 — SEC ticker lookup and annual filing discovery.
Implemented: typed httpx SEC client, shared disk rate limiter across local threads
and processes, declared contact identity, bounded per-request/total timeouts,
response bytes, historical-file traversal and one retry owner. Validated atomic
JSON caches include retrieval timestamps and hashes (24h ticker/1h submissions).
All requests, responses, failures, retries and cache hits have complete redacted
trace payloads. Ticker normalization trims/uppercases and maps class dots to
hyphens without fuzzy matching. Resolution distinguishes not_found, ambiguous,
unsupported and service_error. Annual selection deduplicates accession/report
period, excludes quarterlies, traverses both recent and historical array shapes,
and retains amendments without consuming annual slots. Both accession formats
are stored. Original SEC URLs are constructed from validated metadata; synthetic
sources use explicit badges. Home discovery form and CLI stop at discovery.
One live operation at a time is enforced within the local app; the disk limiter
also coordinates separate CLI processes using the same data directory.

Immutable initial manifests remain intact; discovery publishes a validated
`manifest-discovery` snapshot that repository readers prefer. Historical-file or
request limits report incomplete service failure, never not-found. Two-year
coverage is partial and does not fabricate additional years.

Commands/results:
- `uv run pytest tests/task_gates/test_t04.py`: initial gate caught a missing test
  import; fixed before final acceptance. Expanded gate covers retry recovery,
  redaction on success/failure, corrupt cache, malformed arrays/history, identity
  mismatch, byte/history/time limits, cache persistence and all lookup outcomes.
- Final `uv run pytest`: 31 passed; one upstream Starlette/AnyIO deprecation warning.
- Final `uv run ruff check .` and `git diff --check`: passed.
- `uv run profitlab demo --through T04 --run-id demo-t04`: passed.
- `uv run profitlab demo --through T04 --scenario two-years --run-id two-years-t04`: passed.
- `uv run profitlab doctor --live sec`: passed; run `discover-e09052541481`.
- `uv run profitlab discover AAPL --years 4 --mode live --run-id live-sec-t04`:
  passed; Apple Inc., CIK 0000320193, four distinct report periods 2022–2025.
- `uv run profitlab serve`: server available on localhost:8000.

Open http://127.0.0.1:8000/runs/demo-t04 to inspect the company, four annual
periods and amendment; open `/runs/two-years-t04` to see two periods. Home →
Synthetic demo → UNKNOWN gives not_found; TIMEOUT gives service_error. Trace
shows actual adapter requests, including the fixture older-history file. Live
run: http://127.0.0.1:8000/runs/live-sec-t04 (SEC original links and cached request
payloads). Filing downloads, source inspection and financial processing await T05+.

Visual check remains unrun: CUA inventory has no browser connector, and native
Safari returned “Computer Use permissions are not granted.” HTTP acceptance is
not represented as visual verification. Dependencies/uv.lock unchanged. Some uv
commands needed escalation to read the existing uv cache. Next task: T05.

## Previous task handoff

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

- 2026-09-17, SEC public JSON API (no model): `doctor --live sec`, run
  `discover-e09052541481`, passed. AAPL resolved to Apple Inc./0000320193;
  report date 2025-09-27, accession 0000320193-25-000079. Ticker and submissions
  returned HTTP 200 with validated schemas; complete payloads are saved in trace.
- 2026-09-17, SEC: `discover AAPL --years 4 --mode live --run-id live-sec-t04`,
  passed using the validated live-response cache. Report dates: 2025-09-27,
  2024-09-28, 2023-09-30, 2022-09-24. No filing downloads or original-anchor
  verification claimed; those are T05. No Jev or LLM calls made.

- 2026-09-17, SEC archive HTML (no model): T05 controlled download/parse on
  `live-sec-t04`, Apple 2025 10-K accession 0000320193-25-000079, passed. Exact raw
  bytes/provenance and html-2 block/cell artifacts saved. All 105 mapped DOM anchors
  exist; visual original-anchor scrolling remains pending due to CUA permissions.
