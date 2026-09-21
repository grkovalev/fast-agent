# Progress and next task

## Current state

- Product: ProfitLab, a local SEC earnings-growth research experiment.
- Implementation status: T14 established the isolated V2 contracts, storage, eight-stage shell, live updates, cancellation, and workspace. T15 begins the real source pipeline.
- Next task: **T15 — Canonical visible source and exact anchors.**
- Latest verified task: T14 focused local acceptance; manual browser inspection remains pending.
- Last runnable T13 demo: `demo-t13-20260920` (complete offline managed workflow and validated synthetic report).
- Earlier runnable demos: `demo-t11` and `losses-t11` (annual calculations and preliminary metrics tables; latest calculation snapshots use finalized code). Earlier demos remain readable.
- Decisions: Python + uv; Pydantic; Pydantic AI; configurable OpenAI-compatible Chat Completions provider; separate Jev API; FastAPI/Jinja local UI; SQLite plus bounded source/payload blobs. Previous run data is unsupported by the active plan.
- Scope: up to four fiscal years of 10-Ks; common-share earnings and diluted EPS, with supporting share-count information. Actual investment return is outside this version.
- Current external blockers: browser visual inspection lacks Computer Use permissions. Live Jev and LLM compatibility probes passed after the follow-up fixes; SEC discovery/download checks remain recorded below.

## Task tracker

Use `TODO`, `IN_PROGRESS`, `DONE`, or `BLOCKED`. Keep local acceptance and live verification separate. Initially no check has run.

| Task | Deliverable | Local status | Live verification |
| --- | --- | --- | --- |
| T01 | uv project, CLI, local UI, offline demo skeleton | DONE | Not applicable |
| T02 | Pydantic contracts, fixtures, persistent run storage | DONE | Not applicable |
| T03 | Trace recording, conversation/tool viewer, export | DONE | Not applicable |
| T04 | SEC ticker lookup and filing discovery | DONE | SEC discovery passed; visual inspection pending |
| T05 | Filing downloads and anchored source viewer | DONE | SEC download/parse passed; visual citation inspection pending |
| T06 | Table-aware chunking and chunk inspector | DONE | Not applicable |
| T07 | Jev and OpenAI-compatible provider adapters | DONE | Jev and LLM passed; visual inspection pending |
| T08 | Jev relevance screening and coverage recovery | DONE | Bounded Jev spot check passed; visual inspection pending |
| T09 | Candidate extraction with source validation | DONE | Saved Apple table extraction passed; original/visual inspection pending |
| T10 | Candidate reconciliation and coverage selection | DONE | Not applicable |
| T11 | Deterministic annual-growth calculations | DONE | Not applicable |
| T12 | Pydantic AI report agent and citation validation | DONE | Configured model called twice; actual get_coverage observed; narrative validation failed, honest partial fallback verified |
| T13 | Complete ticker-to-report workflow and run controls | DONE | Browser unavailable; live end-to-end not run |
| T14 | V2 contracts, storage, and live pipeline shell | DONE | Offline shell passed; manual browser inspection pending |
| T15 | Canonical visible source and exact anchors | TODO | Not run |
| T16 | LLM outline with source-coverage validation | TODO | Not run |
| T17 | Jev section scoring | TODO | Not run |
| T18 | Source-range chunking with bounded overlap | TODO | Not run |
| T19 | Jev detailed chunk scoring | TODO | Not run |
| T20 | Quote-backed findings | TODO | Not run |
| T21 | Post-discovery SEC Company Facts | TODO | Not run |
| T22 | Independent fact comparison | TODO | Not run |
| T23 | Consolidated modern pipeline UI | TODO | Not run |
| T24 | Provider, persistence, and resume optimization | TODO | Not run |
| T25 | Remove obsolete execution paths and tests | TODO | Not run |
| T26 | Retrieval benchmark and baselines | TODO | Not run |
| T27 | Final real-data demonstration | TODO | Not run |

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

Task: T14 — V2 contracts, storage, and live pipeline shell.
Implemented: an isolated `data/v2/profitlab-v2.sqlite3` namespace with normalized
run, stage, event, and future stage-owned tables; the eight ordered V2 stages;
shared source-range, scoring, finding, structured-fact, and comparison contracts;
durable cancellation and restart interruption; persisted-before-published stage
events; bounded SSE updates with a polling fallback; and a responsive selected-stage
workspace. The controlled offline shell advances through all eight stages and marks
each future domain stage partial/unimplemented without fabricating output. V1 runs
remain separately readable and no V1 artifact inventory appears in the V2 workspace.

Commands/results:
- `uv run pytest tests/task_gates/test_t14.py tests/task_gates/test_t01.py tests/task_gates/test_t02.py -q`:
  **13 passed** in 0.91s (1.20s wall time); T14 itself contributes three focused tests.
- `PROFITLAB_DATA_DIR=/tmp/profitlab-t14-demo-20260921 uv run profitlab demo --through T14 --run-id demo-t14-20260921`:
  passed and created the offline V2 shell.
- `uv run ruff check .` and `git diff --check`: passed.
- The full historical suite was started and showed no failure before being stopped;
  it was intentionally not used as a T14 completion gate because it exercises V1
  execution paths scheduled for removal. No live SEC/provider call was applicable.
- Browser automation was not run per active task policy; manual visual verification
  remains pending.

Run `uv run profitlab demo --through T14 --run-id demo-t14`, then
`uv run profitlab serve`. Open `http://127.0.0.1:8000/v2/runs/demo-t14`, select all
eight stages, refresh the selected stage, and confirm persisted partial statuses,
clear unimplemented limitations, and no V1 artifact list. From the home page, create
a fresh V2 run and cancel it while active; refresh and confirm cancellation persists.
Next: T15.

## T13 task handoff

Task: T13 — Complete ticker-to-report workflow and run controls.
Implemented: a persisted ten-stage state machine shared by `analyze`/`resume`/`cancel`
CLI commands and application-managed web jobs. The home form now launches the full
ticker-to-report flow and the run page polls durable company, coverage, elapsed,
stage, error and cache-provenance state. Startup marks abandoned work interrupted;
resume reuses only completed stages whose relevant settings, code/prompt inputs and
artifact hashes still match. Chunk changes invalidate screening onward, while
writer-only changes preserve evidence and invalidate writing/validation.

Cancellation propagates to asynchronous provider work and safely drains bounded
synchronous writes before releasing ownership. Per-stage and total timeouts,
single-live-run reservation, sequential provider execution, credential preflight
before paid stages, duplicate-worker locks and honest failed/partial terminal states
are enforced. Existing evidence, candidates and trace remain inspectable after a
stop. Rebuilt chunk indexes select the latest current chunk set, and writer prompt
content is loaded at execution so its hashed input matches the actual instructions.

Commands/results:
- `uv run pytest tests/task_gates/test_t13.py -q`: **10 passed** in 214.50s.
  Coverage includes persistence/reuse, scoped invalidation, cancellation/resume,
  restart recovery, duplicate workers, credential and timeout failures, live-run
  reservation, two-year partial coverage, unknown tickers, background web progress,
  CLI parity, and safe synchronous-write draining.
- `uv run profitlab demo --through T13 --run-id demo-t13-20260920`: passed using
  actual offline services/frameworks with explicitly synthetic providers; the run
  reached the complete stage with a validated cited report.
- `uv run pytest -q`: **104 passed** in 542.50s; existing Starlette/AnyIO
  deprecation warning only.
- `uv run ruff check .` and `git diff --check`: passed.
- `PROFITLAB_PORT=8003 uv run profitlab serve`: server started for visual QA.
  Computer Use exposed no browser connector, and Safari again returned “Computer
  Use was not approved to use Safari,” so visual verification remains unrun.
- No live SEC, Jev or LLM workflow was run. Live end-to-end verification remains
  pending and is not inferred from the synthetic gate.

Open http://127.0.0.1:8000/, select **Synthetic demo**, enter **DEMO**, and click
**Analyze ticker**. Watch the ten stages, then open **Report**. Choose **Slow (try
cancellation)** to cancel, inspect Trace, and resume; completed unchanged stages
should remain reused. Next: T14.

## T13 screening-budget follow-up

A live four-filing MSFT run produced 935 chunks, exposing that the provisional
100-request/120-second screening limits were sized for demos and small spot checks.
The defaults now allow 2,000 Jev calls and 1,800 seconds for screening, with a
2,400-second stage ceiling and 3,600-second workflow ceiling. Screening retains its
own timeout instead of expanding the shorter extraction/writer conversation budget.
The observed workload therefore fits with more than 2x request headroom. These are
configurable safety ceilings, not an instruction to replace Jev classification with
the general LLM. Changing them invalidates the screen stage and downstream caches.
`uv run pytest tests/task_gates/test_t08.py -q`: 4 passed. `uv run pytest
tests/task_gates/test_t13.py -q`: 10 passed. `uv run ruff check .` and
`git diff --check`: passed; existing Starlette/AnyIO deprecation warning only.

## T12 task handoff

Task: T12 — Report-writing agent, actual conversation, and citations.
Implemented: versioned Pydantic AI Report writer with typed run dependencies,
four bounded read-only evidence/selection/calculation/coverage tools, selected
artifact inputs, source ownership checks and explicit missing tool results.
Quantitative placeholders resolve only selected facts, fiscal years and existing
calculation result keys. Application rendering owns the annual table. Output
validation checks company, coverage, table IDs, limitations, source IDs, exact
management quotes, attribution, quantitative placeholders and unavailable results.
Bounded framework repair feedback and incremental native conversations survive
failure/interruption. Fixture writer executes an actual get_evidence call and
repairs an intentional unsupported numeric claim. Persistent failure saves a
clearly labeled data-only partial Report and the diagnostic, without claiming
successful model narrative. Old snapshots remain immutable; changed upstream
calculations hide stale reports.

CLI adds write/validate stages and initial offline verify. UI adds cited narrative,
management source drawers, fact/calculation links, fake-provider labels and a
mechanical Checks page. Trace accurately distinguishes early runs without model
calls and writer histories, each with separate conversation IDs. README updated;
dependencies/lock unchanged. Necessary regression fix: SQLite transaction context
managers now close connections on both success and exception; the extended suite
exposed descriptor exhaustion from connections otherwise awaiting garbage
collection. Added closure/rollback-path verification.

Commands/results:
- `uv run profitlab demo --through T12 --run-id demo-t12`: passed, using actual
  offline services/framework with explicit fake providers.
- `uv run profitlab stage demo-t12 write`: passed after final prompt/validator
  changes, preserving earlier snapshots and conversations.
- `uv run profitlab stage demo-t12 validate` and
  `uv run profitlab verify demo-t12`: passed, model_narrative=true, validation
  status valid, rendered placeholder output matches persisted output.
- Final `uv run pytest tests/task_gates/test_t12.py`: 15 passed. Includes actual
  fixture framework tools/repairs, invalid numbers/IDs/quotes, unsupported
  management attribution, exact coverage, unavailable calculations, source
  ownership, tool budgets, fallback, interrupted native history, immutable
  report snapshots, stale-report hiding, connection closure and two-year coverage.
- Initial `uv run pytest`: 85 passed / six failures. Two obsolete UI labels were
  restored; four downstream failures were caused by SQLite descriptor exhaustion,
  corrected by explicit transactional connection closure. Final `uv run pytest`:
  **92 passed**, existing upstream warning only. This collection preceded the
  two supplemental T12 cases; the final 15-case T12 gate passed separately.
- `uv run ruff check .` and `git diff --check`: passed. Existing upstream
  Starlette/AnyIO deprecation warning only.
- `PROFITLAB_PORT=8002 uv run profitlab serve`: updated interface running on
  localhost:8002, leaving existing servers untouched. `/health` returned 200;
  `/runs/demo-t12/report` returned 200 with validated narrative, fake-provider
  badge, management source drawers and 25.00% markup. HTTP checks are not visual
  inspection.
- `uv run profitlab stage live-sec-t04 reconcile`, then calculate, then write:
  used previously saved public Apple SEC extraction artifacts. Two bounded actual
  configured `gpt-5.6-luna` writer attempts were made; both exhausted one allowed
  repair and persisted data-only partial reports. First attempt used raw fiscal
  years and literal RESULT_KEY fields; clarified prompt examples and added
  validated fiscal_year placeholders. Second attempt added an unsupported custom
  coverage sentence despite the exact supplied coverage contract. First attempt
  had no tool call. Second made actual `get_coverage`, call ID
  `call_OSDDOZb8YJTXCQJAQatSHkD1`; its real request/result and conversation are saved.
  No tool call is invented. Successful live model narrative remains pending;
  these partial saved selections are not an end-to-end ticker report measurement.
- `uv run profitlab verify live-sec-t04`: passed mechanical integrity for the
  data-only partial report, explicitly model_narrative=false and status partial.

Open http://127.0.0.1:8002/runs/demo-t12/report. Click an EPS figure, then
**View source** for the cell/row/year highlight. Click **View calculation** for
narrative growth arithmetic. Expand a management **Source drawer**, inspect its
exact quote and open the saved passage. Follow **Writer conversation**; inspect
get_evidence, its returned source and retry-prompt in the redacted native messages.
Trace with stage=write and kind=structured_repair shows validation feedback.
Checks records reference integrity only; it does not prove causal truth. Next: T13.

Visual verification remains unrun: CUA inventory has no browser connectors and
Safari returned “Computer Use was not approved to use Safari.” Source-viewer
visual confirmation and successful live model narrative remain visibly pending.
No new SEC/Jev call was made. Full workflow/resume/cancel remain T13; expanded
verification and portable report exports remain T15/T16.

## T12 discovery-mode follow-up

User entered MSFT with Synthetic demo selected. The synthetic ticker map contains
DEMO, so that run's not_found outcome is expected and is not a live SEC lookup.
Clarified the home form's ticker/mode guidance and synthetic lookup failures.
Replaced stale discovery text saying extraction is unimplemented with the accurate
statement that extraction has not run. Earlier immutable manifests remain unchanged;
overview rendering clarifies their legacy wording and shows live-mode guidance.
`uv run pytest tests/task_gates/test_t04.py tests/task_gates/test_t01.py`: 24 passed.
`uv run ruff check .` and `git diff --check`: passed. Restarted only the task's
localhost:8002 server. The home form still stops at discovery; full flow is T13.

## T11 task handoff

Task: T11 — Deterministic annual-growth calculations.
Implemented: Decimal-based absolute changes and eligible annual percentages,
plus optional continuous-positive-series CAGR. Exact selected candidate IDs,
source input values/precision, evidence references, formula/version, years,
rounding policy, unrounded results, status/reason and loss-transition labels are
persisted in immutable calculation contracts. Arithmetic uses a local 60-digit
Decimal context; half-up two-decimal rounding applies only to display. Four years
have three annual comparisons and a three-interval CAGR for each main metric.
Missing fiscal years are expanded as unavailable intervals, never bridged.
Conflicts, missing inputs, currency/unit and share-class changes, incompatible
annual contexts, fiscal transitions, material fiscal-length changes and mixed
per-share bases suppress comparisons. Leap-year and 52/53-week variation is
allowed. Zero and negative bases retain absolute changes with labels; transitions
into losses suppress conventional percentages. CAGR requires all annual values
positive and comparable. No model computes arithmetic.

CLI adds `stage <run-id> calculate`, T11 demo progression and a losses scenario
whose changed values are saved in synthetic source HTML before parsing/extraction.
Report and Calculations pages show **Data table; narrative not generated**, exact
annual values, linked percentages/transition labels, formulas, unrounded results,
inputs and complete artifacts. Fact links target stable candidate anchors, then
View source highlights the cell/row/year. Changed extraction or reconciliation
hides stale calculation output until rerun; older artifacts remain inspectable.
Overview tabs and README reflect the implemented stage. Dependencies/lock unchanged.

Commands/results:
- `uv run profitlab demo --through T11 --run-id demo-t11`: passed.
- `uv run profitlab demo --through T11 --scenario losses --run-id losses-t11`: passed.
- `uv run profitlab stage demo-t11 calculate` and the same for `losses-t11`:
  passed, creating finalized immutable calculation snapshots. Normal EPS 2025 is
  (2.00 - 1.60) / 1.60 × 100 = 25%; losses show narrowed losses, a zero base and
  turned profitable, with conventional percentages suppressed.
- Final `uv run pytest tests/task_gates/test_t11.py`: 14 passed, including
  the supplementary fiscal-length/per-share-basis check. Offline pipeline runs cover
  normal, losses, conflict, two-years and split-adjusted scenarios with sockets
  forbidden; checks include persistence, immutable repeat calculations, exact
  candidate anchors, preliminary report markup and stale selection invalidation.
- Final arithmetic subset `uv run pytest tests/task_gates/test_t11.py -k
  'not offline_pipeline'`: nine passed (including added fiscal-length and mixed
  per-share-basis check).
- `uv run pytest`: 78 passed (suite collected before the supplementary T11
  test was added); existing Starlette/AnyIO deprecation warning only.
- `uv run ruff check .` and `git diff --check`: passed.
- Localhost HTTP checks: `/health`, `/runs/demo-t11/report`,
  `/runs/demo-t11/calculations`, `/runs/losses-t11/calculations` all HTTP 200;
  data-table labels and three-interval CAGR details verified in response markup.
- `PROFITLAB_PORT=8001 uv run profitlab serve`: updated interface launched on
  localhost:8001, leaving the existing port-8000 server untouched.

Open http://127.0.0.1:8001/runs/demo-t11/report. Click **25.00%** in EPS 2025
and inspect 1.60, 2.00, the formula and unrounded result; follow an input to
**View source**. Open http://127.0.0.1:8001/runs/losses-t11/calculations to
see absolute changes and suppressed percentages. Trace → stage=calculate has
the full deterministic inputs/results. Next task: T12.

Visual verification remains unrun: CUA inventory has no browser connectors and
Safari returned “Computer Use was not approved to use Safari.” HTTP/TestClient
checks do not constitute visual inspection. No live SEC/Jev/LLM requests made.
Narrative report generation is still unavailable.

## T10 task handoff

Task: T10 — Candidate reconciliation and evidence coverage.
Implemented: deterministic ordered selection with comparable keys for exact period,
metric, annuality, unit/currency, whole-company/segment scope, attribution,
accounting basis and share class. Required source/context validations precede
selection. Duplicate/repeated values preserve every candidate and evidence ref
without adding independent votes. Complete financial statements/EPS notes precede
isolated mentions. Newest equivalent comparable presentations have filing-date
provenance; differing values require explicit restated/recast/split-adjusted
labels in the cited row, year/header or table caption. An amendment alone does not
explain a discrepancy. Equally precise disagreements and contradictory same-date
presentations remain unselected. Differing precision is equivalent only when the
finer value rounds to the coarser reported precision (Decimal, half-up; pairwise
agreement prevents a coarse-precision bridge hiding a conflict).

Added typed CandidateGroups and AnnualObservations, per-candidate reason codes,
full selection trace events, immutable content-derived group/observation IDs and
versioned reconciliation indexes. Four-year main-metric coverage keeps contextual
parent/consolidated income separately labeled. Missing exact periods are shown
without invented fiscal starts. Ambiguous classes/currencies/intervals stay
conflicting; fiscal transitions and mixed original/adjusted per-share bases are
flagged. Adjustment basis includes presentation accession to avoid equating
separate adjustments merely because their labels match. Complementary passages
are deduplicated by normalized text, filing report-end year and topic, with all
source refs retained. No model chooses a winning number or writes a narrative.

CLI adds `stage <run-id> reconcile` and T10 demo progression; scenarios include
conflict, explicit restatement, split-adjusted four-year series and two-year
coverage. Necessary extraction fix: distinguish split-adjusted GAAP from non-GAAP
adjusted figures in table/visible-XBRL context filters. UI adds coverage, competing
values, selection reason codes, filing dates, exact quotes and highlighted-source
links. After re-extraction, stale selections are hidden with a reconcile-again
notice; historical immutable artifacts remain accessible. README/fixture notes
updated, and T01 future-task rejection now uses T11.

Commands/results:
- `uv run profitlab demo --through T10 --run-id demo-t10`: passed.
- `uv run profitlab demo --through T10 --scenario conflict --run-id conflict-t10`:
  passed. Both use actual offline pipeline/services with explicitly fake providers.
- `uv run profitlab stage demo-t10 reconcile` and
  `uv run profitlab stage conflict-t10 reconcile`: passed after final content-ID
  hardening; latest snapshots supersede initial selection artifacts without
  overwriting them. Each has 12 groups, four observations and four deduplicated
  year-scoped explanations. Normal main coverage has all 12 cells selected;
  conflict EPS 2025 remains unselected with 2.00 and 2.25 sources preserved.
  Runs preserve partial status from upstream unsupported extraction contexts.
- Final `uv run pytest tests/task_gates/test_t10.py`: nine passed. Covers socket-
  forbidden/no-gold real offline pipeline, annual/quarterly and attribution/scope
  separation, duplicate provenance, Decimal precision/rounding, restatements,
  split-adjusted series, unexplained/same-date conflicts, cross-check disagreement,
  share-class ambiguity, missing periods/metrics, restart persistence, immutable
  repeat selection, stale selection UI, source row/year highlights and CLI stage.
- `uv run pytest`: 65 passed. Final T10 gate additionally verifies the final
  immutable payload ID hardening. Earlier gate attempts caught an incorrect test
  CSS name and the split-adjusted/non-GAAP filter issue; both corrected. Initial
  obsolete gate run was interrupted; no failed run is presented as passing.
- `uv run ruff check .` and `git diff --check`: passed. Existing upstream
  Starlette/AnyIO deprecation warning only. Dependencies/lockfile unchanged.
- `uv run profitlab serve`: restarted with final code, running at localhost:8000.
  `/health`, `/runs/demo-t10/candidates` and `/runs/conflict-t10/candidates`
  returned HTTP 200. Saved response markup contains coverage/competing-source
  sections and both conflict values. HTTP checks are not visual inspection.

Open http://127.0.0.1:8000/runs/demo-t10/candidates. Expand **Why / compare sources**
for a metric/year, follow **Compare candidate group**, then **View competing
source** to inspect the exact cell/row/year. Selected and alternative sources show
dates, raw/normalized values and reason codes. Open
http://127.0.0.1:8000/runs/conflict-t10/candidates to see EPS 2025 marked
**Conflicting**, with both sources and no selected value. Trace → stage=reconcile
shows the full deterministic rule results.

Visual verification remains unrun: this turn's CUA inventory has no browser
connectors; native Safari returned “Computer Use was not approved to use Safari.”
No new live SEC/Jev/LLM request was made or claimed. T10 has no required live check;
earlier real-source visual confirmation remains pending. Labels/layouts outside
the bounded extraction/adjustment rules remain unsupported or ambiguous.
Calculations and narrative report generation remain unavailable. Next task: T11.

## T09 task handoff

Task: T09 — Candidate extraction with source validation.
Implemented: typed untrusted figure/passage proposals and extraction attempts;
visible cell-anchored inline-XBRL duration facts for five explicit us-gaap concepts,
USD/share units, scale/sign and simple dot-decimal transformations; conservative
annual table rows with merged year headers, exact fiscal intervals and unit scales.
Base-unit Decimal values retain raw source text and reported scale. Narrative
passages have separate quote-validated evidence. Every accepted candidate has a
run-owned EvidenceRef with exact quote, source hash and saved/original anchors.
Repository evidence validation now accepts the immutable download provenance hash
when the discovery record predates download and has no source_hash.

Actual Pydantic AI structured extraction fallback runs over unresolved retained
chunks with supplied IDs, versioned instructions, native incremental conversations,
output schemas, configured repairs, transport traces and bounded requests. Fixture
providers are explicit; invented citations remain visible and rejected. Source ID,
block/table ownership, raw text, year, metric, Decimal normalization, scale and
fiscal interval checks guard proposals. Unverifiable contexts remain ambiguous;
unsupported taxonomy/transforms/dimensions/hidden-only facts stay diagnostic.
Fallback budget: eight chunks, three requests per chunk, configured total timeout.
No model inference fills missing fiscal dates; no gold file enters production.

CLI adds `stage <run-id> extract`, filing/chunk/subset controls and optional supplied
SEC Company Facts JSON cross-check. That comparison uses exact concept, unit,
interval and accession; conflicts are disclosed without replacing filing values or
claiming independent corroboration. Candidate UI has raw values, Decimal units,
periods, methods, reasons, proposal diagnostics, evidence JSON, source drawer and
cell/row/year highlight links. Candidates remain unselected; reconciliation is T10.
README documents the commands and limitations. Updated the T01 future-task invalid
CLI example from newly supported T09 to T10.

Commands/results:
- `uv run profitlab demo --through T09 --run-id demo-t09`: initial demo passed;
  preserved as an initial artifact set. Its share-note scale issue was found/fixed
  using the independent gold acceptance gate. Use the corrected v2 demo below.
- `uv run profitlab demo --through T09 --run-id demo-t09-v2`: passed. 17 numeric
  candidates (including comparative/repeated amendment presentations), five exact
  narrative passages, five rejected fixture citations, two ambiguous comparative
  periods and two unsupported inline-XBRL contexts. Repeated presentations are
  intentionally retained until T10; this is not independent corroboration.
- `uv run pytest tests/task_gates/test_t09.py`: five passed. Gate exercises offline
  real service/storage/UI with network forbidden, independent gold expectations,
  negative parentheses, Decimal scale/per-share units, merged headers, wrong years,
  quarterly/adjusted/segment distractors, hidden facts, missing contexts,
  unsupported transforms, malformed grouping, fabricated IDs, wrong raw values,
  wrong block/table ownership, scale mismatch, restart persistence, highlight
  links and non-replacing Company Facts conflicts.
- `uv run pytest`: 56 passed after updating the obsolete T01 future-task input.
  Earlier run was 53 passed/one obsolete-input failure, now fixed.
- `uv run pytest tests/task_gates/test_t09.py tests/task_gates/test_t01.py`:
  11 passed. Final T09 gate rerun after comma-grouping/sign hardening: five passed.
- `uv run ruff check .` and `git diff --check`: passed. Existing upstream
  Starlette/AnyIO deprecation warning only. Dependencies/lockfile unchanged.
- `uv run profitlab stage live-sec-t04 extract --filing-id filing-000032019325000079 --chunk-id chunk-b3adc82acbe89d50f942a5fe`:
  passed as a partial subset. Nine inline-XBRL income/EPS/share candidates across
  2023–2025; no new provider request needed. Unsupported concepts/layouts and
  unavailable table-only intervals remain visible diagnostics.
- Saved original download's raw HTML facts and stored cells agree for 2025 net
  income `112,010` USD millions → `112010000000`, diluted EPS `7.46` USD/share,
  and diluted shares `15,004,697` thousands → `15004697000`. Exact fiscal interval:
  2024-09-29 through 2025-09-27. NetIncomeLoss stays consolidated income; it is
  not silently relabeled common-shareholder earnings. This is a saved-source
  spot check, not a general extraction accuracy benchmark.
- `uv run profitlab serve`: running at http://127.0.0.1:8000. `/health` and
  `/runs/demo-t09-v2/candidates` returned successful HTTP responses.

Open http://127.0.0.1:8000/runs/demo-t09-v2/candidates. Click an accepted diluted
EPS candidate's **Open source drawer** to inspect raw text and the highlighted
row/year/cell. Expand a rejected proposal to inspect its invented citation. Open
Trace with stage=extract for actual fixture-backed framework messages.
Real saved table: http://127.0.0.1:8000/runs/live-sec-t04/candidates.

Visual verification unrun: CUA inventory has no browser connectors; Safari returned
“Computer Use was not approved to use Safari.” HTTP checks do not count as visual
inspection. Independent SEC-original browser confirmation of three cells remains
pending; raw original downloaded bytes were inspected locally. No new live LLM
extraction or Company Facts request is claimed. Tables lacking exact intervals,
non-USD units, unsupported transformations/dimensions and ambiguous scope stay
unsupported/ambiguous. Model proposals lacking mechanically provable source context
cannot become accepted selections. Next task: T10.

## T08 task handoff

Task: T08 — Jev relevance screening and coverage recovery.
Implemented: five complete, versioned Noul questions sent together per chunk,
separate excerpt/metadata/source instructions, typed persisted ScreeningDecisions,
experimental configurable thresholds, explicit structural table overrides retaining
original probabilities, and one bounded label/neighbor recovery pass with lineage.
Retained candidate coverage is filing/report-end-year/metric scoped and uses unique
primary source identities; it is not extracted numeric fact coverage. No global top-k.
Failed/unknown answers remain retained and never become successful cache entries.
Limits, omitted chunks and missing label coverage produce a partial stage.

Caches hash source/chunk/prompt contents, endpoint/model, fixture mode and policy.
Original calls and returned models survive reuse; latest aliases disclose uncertainty.
Immutable snapshots preserve prior judgments and recovery decisions. The inspector
shows the latest selection, all five score links, decision/reasons, override/recovery,
coverage, retained text totals, unique blocks/cells and historical/new-request usage.
Other chunks in a subset remain explicitly unknown. CLI adds screen, --max-chunks
and repeatable --chunk-id; no provider substitution. Nested live adapter/HTTP events
use stage=screen (probe remains the default for existing callers).

Commands/results:
- `uv run pytest tests/task_gates/test_t08.py`: 3 passed. Offline gate forbids socket
  connections and covers real persisted service/UI, all decisions, unchanged low
  table scores, overlap deduplication, recovery, unknown/malformed/failed responses,
  request limits, cache reuse and source/prompt/model/endpoint/policy invalidation,
  alias uncertainty, restart persistence and configured-secret redaction.
- `uv run pytest`: 51 passed (before final bounded selection/tracing additions).
- Final `uv run pytest tests/task_gates/test_t08.py tests/task_gates/test_t07.py`:
  11 passed after those additions; existing upstream Starlette/AnyIO warning only.
- `uv run ruff check .` and `git diff --check`: passed.
- `uv run profitlab demo --through T08 --run-id demo-t08`: passed, 57 fixture
  evaluations; 7 ordinary keeps, 5 structural keeps, 5 uncertain, 40 drops.
- Final `uv run profitlab demo --through T08 --run-id demo-t08-v2`: passed.
- `uv run profitlab stage live-sec-t04 chunk --filing-id filing-000032019325000079`:
  passed; 135 chunks from the saved Apple 2025 10-K.
- `uv run profitlab stage live-sec-t04 screen --filing-id filing-000032019325000079 --max-chunks 5`:
  passed as a partial subset; five low-scored cover-material chunks, five actual
  requests, 3,938 input/445 output tokens, returned model jev-1.13.0.
- `uv run profitlab stage live-sec-t04 screen --filing-id filing-000032019325000079 --chunk-id chunk-cf12f77b4bf34bd2079bd083 --chunk-id chunk-b3adc82acbe89d50f942a5fe --chunk-id chunk-2211585aba51a1891c3557e4`:
  partial subset as intended, two new requests plus one cache hit; new usage
  2,099 input/178 output tokens. Cover dropped (maximum 0.04); income/EPS table
  retained (income 0.99, EPS 0.98, shares 0.95); EPS note retained (0.98 for all
  three metrics). Returned model jev-1.13.0. Exact saved text and typed answers
  inspected in persisted artifacts; this is a spot check, not an accuracy benchmark.
- `uv run profitlab serve`: running at localhost:8000. Escalated localhost HTTP
  checks passed /health and /runs/demo-t08/chunks with visible screening markup.

Open http://127.0.0.1:8000/runs/demo-t08-v2/chunks. Compare the annual EPS table,
uncertain management explanation, dropped prose and low-scored diluted-share table
with Structural override. Click a probability to open the exact call in Trace.
Real sample: http://127.0.0.1:8000/runs/live-sec-t04/chunks (only three selected
chunks have current results; all others unknown, stage visibly partial).

Visual verification unrun: CUA inventory has no browser connectors; Safari returned
“Computer Use was not approved to use Safari.” HTTP checks are not visual inspection.
No dependency/lockfile changes. UTF-8 estimates and safety budgets remain provisional;
fixture scores are explicitly labeled and never presented as measured Jev behavior.
Recovery performs label/neighbor retention using existing answers rather than a
second inference pass; its original-to-recovered decision lineage is traced.
Changed chunk configurations remain separate immutable inputs; choosing a pipeline
configuration across versions belongs to T13. Next task: T09.

## T07 task handoff

Task: T07 — Jev and OpenAI-compatible provider adapters.
Implemented: separate live/fake Jev Noul clients and typed request/response/usage
contracts; explicit configured OpenAIChatModel/OpenAIProvider factory using the
installed Pydantic AI 2.44.0 API and OpenAI SDK 3.14.1. Compatibility agent calls
the harmless local read_probe tool exactly once and validates its returned marker.
The fixture uses the actual agent framework with FunctionModel, not a scripted
conversation. Configured URL/model/output mode are honored without fallback.
A shared transport owns bounded retries; SDK transport retries are disabled.
Jev 429/529 and transient errors back off; authentication, validation and LLM
exhausted quota stop immediately. Structured-output repairs are tracked separately.
Requests/full responses, actual returned models, usage, native message snapshots,
tool call IDs, validation feedback and interrupted histories persist redacted.
Doctor live probes share the service and print a trace URL even on failure.

Commands/results:
- `uv run pytest tests/task_gates/test_t07.py`: five-test gate passed at initial handoff; follow-up full suite covers eight T07 tests. Gate covers full T07 offline progression
  with socket connections forbidden and absent keys, fake transport retries,
  auth/validation/quota errors, malformed probabilities/IDs/output, custom URL/model,
  actual SDK Chat Completions requests, real agent tools, independent repair budgets,
  native history round-trip, cancellation, persisted/exported secret redaction and UI.
- `uv run pytest`: 48 passed after follow-up fixes; existing Starlette/AnyIO deprecation warning.
  Updated obsolete T01 invalid-input examples to T08/unknown provider so automated
  checks no longer invoke newly supported live commands.
- `uv run ruff check .`: passed.
- `uv run profitlab demo --through T07 --run-id demo-t07-v3`: passed.
  Earlier `demo-t07` retained a failed initial usage-serialization attempt;
  `demo-t07-v2` and final v3 are successful and remain inspectable.
- `uv run profitlab doctor --live jev`: passed, `probe-jev-898d593055c2`;
  returned model jev-1.13.0, 311 input/20 output tokens, one HTTP 200 request.
- `uv run profitlab doctor --live llm`: failed, `probe-llm-51ceec570bc0`;
  three HTTP 429 insufficient_quota/credit_balance_exhausted responses.
  Added nonretryable exhausted-quota classification based on this observed response.
- User added LLM credits; `doctor --live llm` retried as `probe-llm-da62f895dc55`;
  still HTTP 429 insufficient_quota, now stops after one request. Final delayed
  retry `probe-llm-f36f7dcc9a8f` also returned exhausted quota on one request.
- `uv run profitlab serve`: running at http://127.0.0.1:8000.
- `git diff --check`: passed.

Open http://127.0.0.1:8000/runs/demo-t07-v3/trace. Expand fake-jev to see the
state/question fixture and fixture-jev-1 response. Expand Fixture agent history
or filter kind=conversation, then Full result JSON to inspect native tool calls,
returns and typed marker. Actor=agent_tool shows the actual framework-dispatched
read_probe call. Live Jev and failed LLM runs have their own trace URLs.

Visual inspection unrun: CUA inventory returned no browser connectors; selecting
native Safari returned “Computer Use permissions are not granted.” HTTP acceptance
is not visual inspection. Live LLM tool/schema capabilities passed in `probe-llm-516a2123c5de` after
reasoning-effort, decompression and Decimal-serialization fixes (details below). No silent
provider substitution and no invented live agent/tool conversation. Probe success
is not a financial accuracy or screening benchmark. Jev supports only the Noul
primitive required for T08; other TypeSafe primitives are outside this slice.
Native JSON-schema output mode is explicit; live mode compatibility is not assumed.
Probe budgets: 30-second requests, 120-second total, three HTTP attempts, one
structured repair, four model requests, two tool calls, 2MB HTTP response cap.
Fixture framework token estimates are labeled and separate from provider usage.
No dependencies or lockfile changes. Next task: T08.

## T06 task handoff

Task: T06 — Table-aware chunking and chunk inspector.
Implemented: deterministic filing-scoped blocks-1 chunker, configurable 1500/180
prose target/whole-block overlap, table context, intact tables beyond target,
row-group splitting under a separate safe request budget, repeated multi-level
headers/units/captions, rowspan-connected row groups, explicit oversized errors.
Chunks persist content hashes, primary/overlap/context blocks, cell identities,
source anchors, estimator identity and full request estimates. Versioned immutable
indexes include source hash and parser version. CLI `stage <run-id> chunk` and
T06 demo use the same service; traces preserve requests/results and failures.
The inspector filters filing/heading/size and links preceding/following chunks
and saved source blocks. No fabricated screening scores or provider usage.

Commands/results:
- `uv run pytest`: 40 passed, one existing Starlette/AnyIO deprecation warning.
- T06 gate: two acceptance tests covering complete block/cell coverage, repeated
  hashes, source scope, intact/split tables, header/unit context, overlap, request
  limits, unsupported rows, idempotent progression, persistence and HTTP filters.
- `uv run ruff check .`: passed.
- `uv run profitlab demo --through T06 --run-id demo-t06`: passed.
- `uv run profitlab serve`: local server on localhost:8000.
- `git diff --check`: passed.

Open http://127.0.0.1:8000/runs/demo-t06/chunks. Filter heading to
“Chunk boundary examples”, inspect prose overlap, the intact 160-row table, and
pieces of the 1,800-row table. Follow Primary blocks to the saved original table;
Following chunk advances with repeated annual year/unit headers. Synthetic values
are illustrative, not extraction expectations.

Visual inspection unrun: CUA inventory had no browser connector; native Safari
returned “Computer Use permissions are not granted.” HTTP checks do not constitute
visual verification. No live services or paid calls used. UTF-8 bytes/3 estimates
and 24,000-token budget with 2,000 reserved overhead are conservative provisional
proxies, not a verified Jev tokenizer or provider ceiling. Full oversized prose
blocks fail explicitly; header layouts without usable context also fail visibly.
Whole-block overlap may be smaller than 180. Multiple immutable configurations
remain visible in the inspector; future pipeline selection belongs to T13.
Dependencies and uv.lock unchanged. Next task: T07.

## T05 task handoff

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

- 2026-09-17, TypeSafe /v1/systemone: `doctor --live jev`, run
  `probe-jev-898d593055c2`, passed; actual model `jev-1.13.0`, HTTP 200,
  311 input/20 output tokens. Typed Noul answer validated; no screening benchmark.
- 2026-09-17, configured OpenAI-compatible Chat Completions, requested model
  `gpt-5.6-luna`: `doctor --live llm`, run `probe-llm-51ceec570bc0`, failed
  with HTTP 429 `insufficient_quota` / `credit_balance_exhausted` on three attempts.
  No actual returned model, tool call or typed output; native partial history saved.
- 2026-09-17, same configured LLM after user added credits: `doctor --live llm`,
  run `probe-llm-da62f895dc55`, still HTTP 429 exhausted quota on one request.
  Tool/typed-output live verification remains pending; account/key billing state
  may need propagation or correction. No credential values recorded.

- 2026-09-17, final delayed LLM retry after credit update, `doctor --live llm`,
  run `probe-llm-f36f7dcc9a8f`, HTTP 429 exhausted quota again, one request.
  Live tool/schema compatibility remains unverified. Local acceptance is complete.

## T07 follow-up — Live Chat Completions compatibility

User live run `probe-llm-86c3afb529cb` returned HTTP 400: function tools with
reasoning are unsupported for gpt-5.6-luna in Chat Completions; the API instructed
using Responses or reasoning_effort=none. Kept the specified Chat Completions
adapter and model, and explicitly set none for this model on api.openai.com when
not otherwise configured. Added overrideable LLM_REASONING_EFFORT and traced the
effective model settings. Other models/endpoints get no automatic reasoning setting.
Official model docs confirm none is supported; endpoint/tool restriction is based
on the observed API error, rather than an inferred capability from the model page.

Run `probe-llm-4f0e938f2c0b` then received HTTP 200, returned model gpt-5.6-luna,
with a real requested read_probe call and usage of 173 prompt/13 completion tokens.
The call was not dispatched because the transport rebuilt a decoded response with
its original gzip header, causing httpx to decode it twice. Fixed by removing wire
content-encoding/content-length when rebuilding decoded responses, while retaining
original headers in trace payloads. Added regression checks for gzip responses,
explicit default reasoning, configured overrides and exact transmitted reasoning.

Final `doctor --live llm`, `probe-llm-e82b18c948e1`, again received HTTP 429
insufficient_quota/credit_balance_exhausted on its first request. The HTTP 400 and
double-decompression defects are fixed locally, but a complete live read-only tool
invocation plus validated typed response is still pending available account quota.
No successful live probe or tool invocation claimed. Dependencies/lockfile unchanged.

## T07 follow-up — Decimal usage serialization and successful live probe

User run `probe-llm-ee4d9ef3d9a8` received HTTP 200 but failed when recording
RunUsage.cost, which Pydantic AI represents as Decimal. Shared trace redaction
now converts Decimal to an exact string before JSON encoding, without conversion
to float or loss of precision. Added a FunctionModel regression with explicit
Decimal usage costs checking completed tool/typed-output flow, snapshots and
exported payloads. Framework cost values are estimates; native provider token
counts and raw usage remain separately inspectable.

`uv run profitlab doctor --live llm`: PASSED, `probe-llm-516a2123c5de`.
Two HTTP 200 Chat Completions requests, actual model gpt-5.6-luna in both responses;
173/13 then 203/22 prompt/completion tokens (376 input, 35 output total).
Exactly one real framework-dispatched read_probe call,
call_vFjFqb120qxgmQScLuK1ELMg, completed with matching call IDs. Final typed output
value=profitlab-probe-v1; zero structured-output repairs. Native observable message
history, request bodies, raw responses and usage persisted successfully.
Open http://127.0.0.1:8000/runs/probe-llm-516a2123c5de/trace and filter
actor=agent_tool for the tool, or kind=conversation for native messages.
Visual verification remains pending; successful live compatibility is not a
financial extraction/quality benchmark. No dependencies or lockfile changes.
`uv run pytest`: 48 passed; existing Starlette/AnyIO warning.
`uv run ruff check .` and `git diff --check`: passed. Next task remains T08.

- 2026-09-17, OpenAI Chat Completions, `doctor --live llm`, run
  `probe-llm-516a2123c5de`, PASSED with actual model gpt-5.6-luna, two HTTP 200
  responses, one executed read-only tool and validated typed marker. Native history
  persisted; 376 input/35 output tokens total, no repairs. Earlier quota and local
  compatibility failures remain saved and are historical, not current blockers.

- 2026-09-17, TypeSafe screening on saved Apple 2025 10-K, `live-sec-t04`:
  bounded five-cover-chunk sample and three-chunk relevant/irrelevant comparison,
  seven new requests total, 6,037 input/623 output tokens, actual model jev-1.13.0.
  Typed responses validated; relevant table/note retained, cover dropped. Subset
  remains partial; visual inspection pending. No screening-accuracy claim.

## UI follow-up — Easier figure verification

User requested a clearer interface after inspecting Apple candidates. Candidate
pages now show compact year tables with readable metric names, reported-scale
values/units and one View source action per figure. Raw Decimals, parser method,
validation and evidence JSON remain inside Details. Narrative passages and
extraction issues are collapsed separately; unrequested Company Facts detail is
hidden. No candidate selection or reconciliation was added.

Source links show only the cited table with its existing row/year/cell highlights,
a Back to figures link and an optional View full filing link. Source hashes and
block identifiers are collapsed, and coordinate controls appear on hover/focus.
Overview pipeline details and potentially huge artifact lists are collapsed.
Removed the repeated report heading from every page. Synthetic/partial disclosures
remain visible. These are presentation changes; stored evidence remains intact.

Verification: existing candidate, source and bootstrap gates run for this follow-up;
results: initial run had 17 passes and one full-filing anchor compatibility failure;
fixed by making table focus an explicit query option on candidate links. Final
`uv run pytest tests/task_gates/test_t05.py tests/task_gates/test_t09.py`: 12 passed;
bootstrap gate also passed in the initial run. `uv run ruff check .` and
`git diff --check`: passed. Running server returned the simplified Apple page;
HTML verification confirmed three year tables, nine figure rows and nine source
links with diagnostics collapsed. A real persisted Apple source link was checked
through TestClient: one highlighted table and Back to figures, HTTP 200.
Browser visual inspection remains unavailable because
Computer Use access to Safari was not approved. Next numbered task remains T10.
