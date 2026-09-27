# Progress and next task

## Current state

- Product: ProfitLab, a local SEC earnings-growth research experiment.
- Implementation status: V2 has one product path: a ticker creates a live SEC filing
  run, followed by configured LLM and Jev provider calls. Synthetic source and provider
  paths no longer exist in V2 runtime code or UI.
- Current task (this branch): V3 source-grounded graph experiment. The runnable
  `profitlab v3 answer TICKER QUESTION` path acquires one live 10-K into an isolated
  repository, explores bounded canonical-source windows, validates model-proposed
  generic graph evidence, and emits only answers with cited accepted graph paths.
  V3 storage remains under `data/evidence-graph-experiment/`; V2 remains the product
  baseline and is neither read nor written by V3.
- Completed V3 proof: live command `uv run profitlab v3 answer MSFT "What does the
  filing say about revenue growth?"` completed as experiment
  `v3-b010c04ebc0276c8` against accession `0001193125-26-323660`. Its limited answer
  cited accepted graph paths to canonical lines 102, 245, and 263, and explicitly
  declined to claim a quantitative growth rate absent from its supplied evidence.
  The source/graph/answer audit is in the experiment-local database. Focused and full
  tests passed (`47 passed`) after this implementation; V2 storage isolation is covered.
- G3 dynamic graph exploration planner: V3 now seeds one generic bounded canonical
  source window rather than sweeping the filing. A model response may request a next
  bounded window only with a non-empty model reason and accepted/uncertain node
  provenance from that action; rejected or unknown evidence, out-of-document spans,
  and over-size windows become explicit action partials. Exact normalized intervals
  are visited once, so a repeated model request cannot create an unbounded loop.
  Every action persists its parent path, reason, source/call/wall-time budget state,
  request, response, and validation state. The terminal `exhausted` or
  `budget_exhausted` manifest snapshot is persisted before answer synthesis, so an
  unsupported graph remains inspectable and no answer is fabricated. This uses no
  document-layout/financial-target policy, V2 reads, or evaluation data. Focused
  `uv run pytest tests/task_gates/test_v3_graph.py -q` — **10 passed** in 1.04s;
  `uv run pytest -q` — **49 passed** (one existing Starlette/AnyIO deprecation
  warning); `uv run ruff check .` and `git diff --check` passed. The focused suite was extended
  with dynamic accepted/uncertain expansion provenance and equivalent-window revisit
  coverage; no obsolete tests were removed. No live check was attempted because it
  requires configured SEC and LLM credentials. Manual inspection after one-time
  `uv run profitlab serve` is not yet available (G4); inspect the experiment-local
  `actions` and manifest snapshots under `data/evidence-graph-experiment/` to confirm
  the parent path, reason, budget state, and terminal frontier state.
- G4 graph explorer UI: the experiment-only `/v3/experiments` workspace now lists
  isolated V3 experiments and opens one persisted provenance path at a time. It
  explicitly separates model labels/relationships and answer candidates from
  immutable canonical source text; every displayed path evidence range links to its
  canonical lines. The frontier trace answers why a window was explored (reason and
  parent path), and exposes response status, request hash, elapsed/cache state,
  per-action budgets, and the terminal frontier state without making raw database
  rows or provider payloads the review surface. Accepted, uncertain, and rejected
  nodes/edges remain distinct, including when they cannot form an answer path. V3
  data remains exclusively in its experiment repository; no V2 path changed.
  Focused `time uv run pytest tests/task_gates/test_v3_graph.py -q` — **11 passed**
  in 1.23s (1.60s wall time; one existing Starlette/AnyIO deprecation warning);
  `uv run ruff check .` and `git diff --check` passed. The focused gate gained one
  UI integration path over a persisted accepted/uncertain/rejected graph; no
  obsolete tests were removed. Browser automation was not run per task policy.
  Manual verification: after one-time `uv run profitlab serve`, open
  `http://127.0.0.1:8000/v3/experiments`, select an experiment, follow a canonical
  line link from the selected provenance path, then compare its frontier card's
  reason/parent path/budget with the terminal frontier notice. Confirm uncertain and
  rejected inventory entries remain visibly non-promoted. No live check was attempted
  because it requires configured SEC and LLM credentials.
- G5 graph-grounded answer validation: V3 now persists each material answer claim
  with its own exact canonical ranges and selected graph-path IDs. The answer request
  is bounded to those path packets and labels remain navigational metadata, never
  source. A citation outside its selected path is rejected; missing/mangled opaque
  path IDs can only be mechanically derived from exact citations and make the result
  limited. An uncertain subgraph (or an accepted `contradicts` relationship) is
  explicitly limited rather than allowed to force a conclusion. The explorer now
  renders each claim's source links and inspectable full path. This remains isolated
  in the V3 repository and does not read or write V2 Findings.

  Focused `time uv run pytest tests/task_gates/test_v3_graph.py -q` — **14 passed**
  in 1.30s (1.67s wall time; one existing Starlette/AnyIO deprecation warning).
  Full `time uv run pytest -q` — **53 passed** in 2.93s (3.28s wall), with the same
  warning. `uv run ruff check .` and `git diff --check` passed. The focused gate adds
  claim/path persistence, out-of-path-citation rejection, and uncertainty-limited
  answer coverage; no obsolete tests were removed. No live check was attempted: it
  requires configured SEC and LLM credentials, and local fixtures are not presented
  as live evidence. Browser automation was not run per policy.

  Manual verification: after the one-time `uv run profitlab serve`, open
  `http://127.0.0.1:8000/v3/experiments`, choose an experiment, and inspect an answer
  card's **Claim-to-source paths**. Open every canonical-line and path link; confirm
  each claim maps to its exact visible source and that a limited answer exposes its
  limitation rather than a forced conclusion.

  Follow-up compatibility fix: an existing experiment returned a 500 because its
  pre-G5 persisted answer had no `claims` field. `AnswerCandidate` now derives one
  legacy claim from the existing answer/path/range fields during read validation;
  the explorer route has a regression test. Focused V3 tests now pass **15** and the
  full suite **54** (`time uv run pytest -q`, 2.90s test time / 3.19s wall); Ruff and
  diff checks pass.
- G6 post-seal rubric implementation: V3 now accepts a frozen, explicitly held-out
  cohort containing graph, V2-packet, and bounded-window artifacts, without opening
  V2 storage. It validates every reviewer range against the linked immutable V3
  canonical document and scores source coverage, citation validity, graph-path
  fidelity, reviewer-recorded answer support and ambiguity handling, provider
  calls/tokens, and latency. The `profitlab v3 score COHORT.json` command persists
  the deterministic result only in the V3 repository; `/v3/comparisons/<cohort-id>`
  renders the inspection view. Rubric records have no graph-service call path and
  are not provider inputs. Focused `uv run pytest tests/task_gates/test_v3_graph.py
  -q` — **17 passed** in 1.65s; full `uv run pytest -q` — **56 passed** in 3.11s;
  Ruff and `git diff --check` passed. No obsolete tests were removed. The focused
  gate covers the non-leak/no-additional-provider-call invariant, all three frozen
  methods, persisted/UI inspection, required held-out status, and out-of-path graph
  citation invalidation.

  G6 remains **IN_PROGRESS** until a genuinely held-out, frozen three-method cohort
  is collected and reviewed. Existing G5 live evidence cannot honestly fill that
  role. See [V3_G6_RUBRIC_COHORT.md](V3_G6_RUBRIC_COHORT.md) for the immutable input
  format and manual review flow; do not tune prompts, relation vocabulary, budgets,
  or model while collecting it.

  G6 live development diagnostic (2026-09-27): two authorized live graph runs used
  explicit revision `g6-heldout-cohort-20260927` and the unchanged
  `evidence-graph-v4` configuration for the question “What exact annual net income,
  diluted earnings per share, or diluted shares does this filing visibly report?”
  CRVL experiment `v3-3d48becbd41c7d7d` reacquired the exact frozen V2 source hash
  `063e9bcaec1b…` and SPRO experiment `v3-d736ca619cf0de87` likewise matched
  `3fe3f61118e9…`. Both emitted exact, accepted graph paths but stopped at the cover
  fiscal-year line and Item 8 table-of-contents line, then correctly persisted a
  limited non-answer rather than fabricating a financial claim. WOR also completed
  under this revision with a matching source and limited result. An initial SPRO
  attempt produced no result and was retried once successfully. These are development
  diagnostics, not a held-out cohort or a graph-performance result. Remaining calls
  were intentionally stopped because repeating the same unaddressed planner failure
  would not be a meaningful comparison.

  G6a insufficiency-directed graph continuation (2026-09-27): every exploration
  action now persists the validated model `answerability` (`sufficient` or
  `insufficient`; malformed responses remain visibly null/partial). Only a
  `sufficient` frontier can call answer synthesis. An `insufficient` frontier must
  issue an unvisited, bounded, accepted/uncertain-evidence-linked continuation or
  persist terminal frontier `partial`; it cannot synthesize an answer. No-revisit,
  exact range validation, and source/action/wall-time budgets remain unchanged. The
  generic request now states the configured maximum continuation size and is versioned
  `evidence-graph-v5`; no financial, layout, table, or heading policy was added.
  Focused contracts cover continuation, no-continuation partials, sufficient-only
  synthesis eligibility, and the no-answer-call invariant. Focused V3 tests pass
  (`19 passed`); full-suite revalidation passes (`58 passed`). Fresh live development
  pilot `v3-358e57c01e560ea2` used revision
  `g6a-pilot-20260927-v5` and the annual net-income/EPS/shares question on MSFT. Its
  first insufficient frontier validly continued from L1–120 to L121–240 through an
  accepted parent node, demonstrating source-path progress. The second insufficient
  frontier proposed malformed exact evidence/provenance, so validation persisted
  `partial` and made no answer call. This is a development diagnostic, not a held-out
  result. Do not begin the frozen five-case G6 cohort yet; CRVL, SPRO, and WOR remain
  excluded when a cohort is separately authorized.
- G6 held-out graph arm (2026-09-27): one newly selected FGN case ran under the
  fixed revision `g6-heldout-cohort-20260927-v5`, unchanged
  `evidence-graph-v5` configuration, and the frozen annual net-income/EPS/shares
  question. Experiment `v3-18dc33e36fd6ecff` reacquired the exact sealed V2 source
  hash `448c2d998090…`. Its first L1–120 frontier declared `insufficient` and
  requested the accepted-evidence-linked L121–240 continuation; the second frontier
  declared `sufficient`, then the answer cited visible net earnings (loss) at
  canonical lines 133–134. This is one graph arm only, not a completed held-out
  comparison or a performance claim: the independently reviewer-entered required
  ranges plus frozen `v2_packet` and `bounded_window` artifacts are still required
  before creating the immutable three-method cohort. Focused
  `time uv run pytest tests/task_gates/test_v3_graph.py -q` — **19 passed** in
  1.57s (1.95s wall, one existing Starlette/AnyIO deprecation warning); `uv run
  ruff check .` and `git diff --check` passed. No source tests were changed.
  Manual verification: after one-time `uv run profitlab serve`, open
  `http://127.0.0.1:8000/v3/experiments/v3-18dc33e36fd6ecff`, inspect the L1–120
  insufficient frontier and its L121–240 continuation, then follow the answer
  citation to lines 133–134. Confirm the FGN result remains isolated from V2 and
  is not presented as a scored comparison.
- Deferred V2 follow-up: define one bounded evaluator-representativeness task from
  the T41 cohort; do not tune Findings prompts, vocabulary, or thresholds from that
  cohort on this graph branch.
- Separate-branch architecture experiment: the checked-out
  `source-grounded-document-graph` branch has an explicit G0–G6 plan in
  [SOURCE_GROUNDED_DOCUMENT_GRAPH_EXPERIMENT.md](SOURCE_GROUNDED_DOCUMENT_GRAPH_EXPERIMENT.md).
  It preserves the T41 cohort evidence and isolates a model-built, source-cited,
  question-conditioned graph from V2. The graph must not use deterministic
  document-type/layout inference; only provenance validation, budgets, storage, and
  traversal are deterministic. Graph output cannot alter V2 or
  receive Company Facts, findings, expectations, comparisons, rubrics, or evaluation
  output as provider input.
- T41 15-run cohort review: three completed five-report batches
  (`batch-83e0ad9b5ed5`, `batch-c6b6c5f091f8`, and `batch-ec73ec4723d6`) produced
  FGN, RHNO, SPRO, SKYX, ALL-PJ, WOR, KPEA, LRMR, IVDA, GBCS, DBB, CRAC, CRVL,
  NCPL, and EFSI under `v2-5d00a512aa114aaa`. Every source through evaluation
  stage completed. The corrected audit recorded 525 packet cores sent (345
  target-shaped and 180 measured reserve) and 4,142 visible retained lines explicitly
  outside the reserve; no planned core was excluded by the Findings request-size
  budget. It recorded 37 first-pass valid findings, 31 invalid citation proposals
  (30 amount/quote mismatches and one attempt to cite a non-core line), and three
  repair-produced valid findings. Thus quote/core validation contained malformed
  model output, but repair recovered only a small portion.

  The independent comparison states were 2 exact matches, 10 scale-aware
  equivalents, 7 Jev-rejected candidate comparisons, 19 structured-fact misses,
  5 value matches with period unresolved, 6 additional visible values, and 6
  unsupported/unresolved findings. These totals do not support a claim that the
  packet layout improved precision or recall. They do expose evaluator limits:
  it maps every `annual_profit` finding to consolidated net income while separately
  treating common-shareholder net income as required, even when the discovered value
  visibly corresponds to the latter (FGN and ALL-PJ); it treats Company-Facts gaps
  (CRAC has none and LRMR/DBB have one) as additional visible output; and its scale
  verdict lacks a declared table-precision/scale contract. Five numeric matches are
  separated solely because the pipeline did not publish a usable period. The next
  safe slice is therefore post-seal evaluation coverage/linkage diagnostics using
  packet provenance and visible source rows, never as Findings input, before changing
  retrieval or prompting. Review commands: read-only repository inspection plus
  `uv run pytest -q` — **39 passed** (one existing Starlette/AnyIO warning),
  `uv run ruff check .`, and `git diff --check` passed.

  The same cohort's persisted provider profile identifies a separate non-behavioral
  performance opportunity: source-context diagnostics consumed 555 Jev calls, versus
  117 detailed chunk-score calls, 23 Findings calls, and 35 finding-type calls. Those
  diagnostics do not currently affect retention or Findings inputs, so a versioned
  sampled/opt-in diagnostic policy can reduce latency and cost without being presented
  as a retrieval improvement. Any model/prompt optimization must instead be a frozen-
  input ablation with quote-valid yield, source-coverage funnel, token/call count, and
  latency recorded independently.
- T41 first live cohort review: batch `batch-8f51756183f1` completed five reports
  (KIM, AAP, TFC, PNFP-PB, GNSS) under version `v2-c8ba15f4b5935cfe`.
  Each Findings request contained all planned packets: respectively 51, 34, 40,
  46, and 42 cores, including the measured 12-core non-target reserve and 39, 22,
  28, 34, and 30 target-shaped cores. Findings published 4, 3, 4, 4, and 3
  quote-valid findings. GNSS made one bounded repair: three first-pass citations
  failed Decimal/quote validation, then one repair-produced finding was valid.
  The aggregate independent outcomes were two exact matches, four scale-aware
  equivalents, three Jev-rejected comparisons, eight structured-fact misses, and
  seven unsupported additional findings. This mixed result does not demonstrate a
  precision or recall gain over the prior cohort.

  Review found a provenance defect in that cohort's persisted selection audit only:
  non-target lines outside the 12-core reserve were incorrectly labelled as
  `packet excluded by findings request size budget`. They were never packet cores or
  provider inputs; the saved request payload proves every planned packet was sent.
  The implementation now distinguishes `not_in_bounded_uncertainty_reserve` from a
  true size-budget packet exclusion, with focused contracts passing. Because historical
  audit rows are immutable and cannot be relabelled, this cohort cannot close T41's
  fully-auditable live gate. Run one fresh 5–10 report cohort under an explicit new
  application revision before deciding whether the compact layout trade-off is useful.
- T41 local implementation slice: Findings now sends bounded, versioned, source-order
  packets of independently citable visible core lines. A core is included when it
  matches the existing product-shaped source vocabulary, with a separately measured,
  bounded source-order reserve for non-matching lines; this is layout reduction, not
  an eligibility or top-N recall gate. Each core carries only a small local
  heading/table-header/adjacent-row context, while validation permits a quote only
  from the exact included core line. The request trace persists packet identifiers,
  per-line inclusion kind, sent packet, and explicit request-size exclusions beside
  the existing proposal, quote-validation, and type-classification audits. Packet,
  reserve, request-size, and prompt settings are cohort-versioned; no XBRL, Company
  Facts, review expectations, findings, or evaluation values enter the request.
  Focused contracts include reserve behavior, core-only citations, size exclusions,
  and versioning. Local acceptance: `uv run pytest -q` — **39 passed** (one existing
  Starlette/AnyIO deprecation warning); focused `uv run pytest tests/task_gates/test_t39.py
  tests/task_gates/test_t40.py tests/task_gates/test_t41.py -q` — **19 passed**
  (one existing warning); `uv run ruff check .` and `git diff --check` passed. No
  live cohort was run.
- T39 experiment record: [recall investigation](T39_RECALL_INVESTIGATION.md). It
  documents failed live cohorts and the controlled next experiment; do not treat its
  unverified working-tree changes as an accepted approach.
- T39 operating rule: after every bounded implementation slice, run a small live
  cohort and explore its persisted source rows, decisions, traces, findings, and
  evaluation before selecting the next slice. Local tests validate contracts only;
  the live evidence must show whether the work is moving in the right direction.
- T39 first slice: persisted source-range-bound `SourceContextDecision` records,
  bounded visible expansion rings, and versioned configuration are implemented and
  locally tested. They are diagnostics beside flat-chunk retention, not a recall gate.
- T39 inspector slice: persisted decisions now appear in the Chunk inspector and in
  bounded Chunk/Chunk Score/Findings workspace surfaces as an evidence-core/context/
  expansion graph. It keeps the stage rail as checkpoint navigation, labels context as
  non-citable, and explicitly says flat chunk retention is unchanged. The next bounded
  slice batches independent retained-core line decisions in source order (default eight
  cores per Jev request), preserving each core's own visible context, response fields,
  range, and expansion history. A versioned maximum live-call budget (default 36)
  counts malformed/failed attempts and produces explicit partial decisions rather than
  failing the baseline stage. Focused coverage includes response-invalid partial state
  and source-order batching; `uv run pytest -q` — **26 passed** (one existing
  Starlette/AnyIO deprecation warning); `uv run ruff check .` and `git diff --check`
  passed.
- T39 batched live replay: on 2026-09-26, direct diagnostic replay of the saved IWAL
  run `v2-aa2f7a4a731e` classified its 107 already retained canonical lines with 36
  Jev calls. It persisted 109 decisions: 88 completed and 21 explicit budget partials
  (two recorded expansion attempts), compared with the earlier per-line wiring's 36
  calls / 111 decisions / 75 partials. The baseline Findings/Evaluation rows were not
  changed. All completed role judgements were `uncertain` (notably evidence scores
  below the configured threshold), so batching improves diagnostic coverage only; it
  does not demonstrate semantic usefulness or retrieval improvement. The replay used
  execution revision `t39-context-batch-v1`, but was intentionally applied to a saved
  run and therefore does not create a persisted new version cohort. Remaining: record
  source-row expectations for the controlled replay set and diagnose this all-uncertain
  response shape before changing prompts, thresholds, retention, or Findings inputs.
- T39 source-row replay slice: added a checked-in, source-hash-bound IWAL current-year
  expectation set for the three statement rows (lines 291–293), and a strictly post-run
  trace from flat retention through the actual Findings request, proposal validation,
  Jev type classification, publication, and independent comparison. The findings trace
  now persists structural proposal/validation audit entries for new runs without
  duplicating generated quotes or amounts. The replay surface is visible only in the
  Findings/Evaluate workspace and explicitly states that reviewed rows are never
  provider inputs. Read-only replay of the saved live IWAL run verified all three rows
  were flat-retained, sent, classified, and published; the profit row independently
  matched. Its older trace predates proposal auditing, so proposal and quote-validation
  states correctly render as unknown rather than failures. `uv run pytest -q` — **27
  passed** (one existing Starlette/AnyIO deprecation warning); `uv run ruff check .`
  and `git diff --check` passed. Next bounded experiment: execute one newly versioned,
  controlled IWAL replay to populate the proposal audit, then inspect the first loss
  point before altering any prompt, threshold, retention, or findings input.
- T39 controlled IWAL replay: on 2026-09-26, created fresh run `v2-5e82c4ba9063`
  under application revision `t39-iwal-audit-v1` / version
  `v2-3432655c44f7a869`. It used the pinned accession
  `0001498372-26-000002` and expected source hash. All three reviewed statement rows
  (291–293) were flat-retained, sent to Findings, proposed, quote-validated,
  type-classified, and published. The annual-loss row independently exact-matched;
  EPS and diluted-shares rows are valid published values but have no corresponding
  available Company Facts target, so evaluation records them as additional visible
  values rather than retrieval failures. This controlled trace therefore has no
  product-pipeline loss point for its three rows. T39 context diagnostics remained
  109 `uncertain` decisions (88 completed, 21 budget partials, 36 calls), proving
  neither semantic usefulness nor a context-driven retrieval effect: flat chunk
  retention remains the active path. Next bounded slice: inspect the persisted
  completed/partial Jev response shape and its expansion history before changing
  any prompt, threshold, retention, or Findings input.
- T39 score-shape diagnostic slice: persisted the complete finite Jev score vector
  with every completed `SourceContextDecision` and exposed its role/sufficiency
  scores in the bounded context inspector; partial and historical decisions state
  that scores are unavailable. This changes no prompt, threshold, expansion policy,
  retention, or Findings input. A fresh direct replay of the same 107 IWAL
  flat-retained source lines under application revision `t39-score-shape-v1` created
  `v2-10d253c64e2b` / `v2-a3c9381780e9992a`: 109 decisions, 88 completed, 21
  explicit request-budget partials, and 36 Jev calls. Of completed decisions, 69
  were uncertain/sufficient, 18 uncertain/insufficient, and one
  evidence/sufficient (line 290, a heading/context line eligible only for
  earnings-change/comparability). The reviewed annual-loss row 291 remained
  uncertain despite sufficient context (evidence 0.64 vs the 0.65 role threshold;
  annual-profit eligibility 0.47); rows 292–293 had evidence 0.62 but
  diluted-shares eligibility 0.87. The two pass-1 expansions again consumed the
  remaining call budget and became explicit partials. This is response-shape
  evidence, not a retrieval result or a basis to tune a threshold from one filing.
  An accidental otherwise-identical replay `v2-8c12a9fdc6eb` inherited revision
  `0.1.0`; it is marked partial and excluded from controlled cohorts. Local
  acceptance: `uv run pytest tests/task_gates/test_t39.py -q` — 8 passed (one
  existing Starlette/AnyIO warning); `uv run ruff check .` and `git diff --check`
  passed. Next bounded experiment: define the fixed multi-filing source-row replay
  set named in the recall investigation before evaluating any calibrated role or
  eligibility alternative.
- T39 fixed replay-set slice: expanded the checked-in, source-hash-bound review-only
  source-row expectations to the exact CQP, VLOSU (now SEC ticker VLOS), ATLC, NBHC, and RANI filings named
  in the recall investigation, alongside IWAL. Every case has its accession and the
  three current-year annual-profit/loss, diluted-EPS, and diluted-share rows; CQP and
  VLOSU preserve mixed-table/noise coverage, ATLC/NBHC the Decimal JSON protocol, and
  RANI the Findings timeout case. The rows remain strictly post-run diagnostics, and a
  changed source hash cannot inherit a case. Next bounded experiment: run one freshly
  versioned controlled replay of this fixed set, then inspect its persisted source-row
  loss points before changing role calibration, eligibility, routing, prompts,
  retention, or Findings input.
- T39 CQP fixed-set replay: on 2026-09-27, fresh run `v2-b77c75aa8adc` under
  application revision `t39-fixed-replay-v1` / version `v2-5e400dda6f984ca5` matched
  the pinned CQP source hash. All three reviewed rows (292–294) were flat-retained,
  sent, proposed, quote-validated, type-classified, and published: no source-row loss
  point was observed in the mixed-table case. Annual profit `2987`, diluted EPS `5.17`,
  and diluted shares `484.0` remained additional visible values under the current
  Company Facts scale/target contract; this is not an accuracy result. Context
  diagnostics made 36 calls for 250 retained lines and persisted 254 decisions, 174
  explicit budget partials. Next bounded experiment: replay the VLOSU/VLOS mixed-table
  case from the same fixed set, then inspect its persisted source-row trace before
  changing role calibration, eligibility, routing, prompts, retention, or Findings
  input.
- T39 VLOS fixed-set replay: on 2026-09-27, fresh controlled run
  `v2-dd7ff6d041be` under application revision `t39-fixed-replay-v2` / version
  `v2-b9a2cf7c5ed5d24a` matched pinned VLOS accession
  `0001213900-26-027060` and source hash. The annual-profit row (1148) and
  diluted-EPS row (1154) were flat-retained, sent, proposed, quote-validated,
  classified, and published; annual profit `5,778,750` exact-matched its
  independent Company Facts target, while the Class-B EPS `0.16` remained an
  additional visible value. The diluted-shares row (1326) was not flat-retained,
  so it was never sent or proposed: its enclosing lines 1261–1331 “Significant
  accounting policies” outline section scored skipped (annual-profit `0.09`,
  diluted-EPS `0.09`, diluted-shares `0.13`, below the `0.20` uncertain threshold),
  hence no chunk covered that row. This is the first observed VLOS source-row loss
  point, upstream of chunk scoring, source-context diagnostics, Findings, and
  evaluation. The unchanged diagnostics made 36 Jev calls for 148 retained lines,
  persisting 150 decisions with 74 explicit budget partials. This is evidence about
  one section-selection miss, not a basis to alter a threshold or make adaptive
  context a gate. Next bounded experiment: inspect the fixed ATLC decimal-protocol
  case and persist its first source-row loss point before changing role calibration,
  eligibility, routing, prompts, retention, or Findings input. Focused local
  acceptance after recording the evidence: `uv run pytest tests/task_gates/test_t39.py
  -q` — **9 passed** (one existing Starlette/AnyIO warning); `uv run ruff check .`
  and `git diff --check` passed.
- T39 ATLC fixed-set replay: on 2026-09-27, fresh controlled run
  `v2-a5d6fb510af8` under application revision `t39-fixed-replay-v3` / version
  `v2-96a40c089fb37d78` matched pinned ATLC accession
  `0001437749-26-007972` and source hash. All three reviewed rows were
  flat-retained and sent to Findings. The diluted-share denominator (1594) was
  proposed, quote-validated, type-classified, published, and independently
  scale-aware equivalent. The annual-profit (1586) and diluted-EPS (1596) rows
  were not proposed, so their first observed loss point is Findings proposal
  selection, before quote validation and classification. The run did publish
  quote-backed annual-profit and diluted-EPS findings from other retained lines
  (971 and 975); those are not a recovery of the reviewed source rows. This is
  source-row evidence for the decimal-protocol case, not a prompt/parser result or
  a basis to alter routing, prompts, retention, role calibration, eligibility, or
  Findings input. The unchanged context diagnostic made 36 calls for 250 retained
  source lines and persisted 250 decisions with 178 explicit budget partials; the
  completed pipeline is therefore marked partial only for that diagnostic budget.
  Next bounded experiment: replay NBHC from the fixed set and persist its first
  source-row loss point before changing product behavior.
- T39 NBHC fixed-set replay: on 2026-09-27, fresh controlled run
  `v2-fba0dfa336e5` under application revision `t39-fixed-replay-v4` / version
  `v2-57fddeed5d0c6b62` matched pinned NBHC accession
  `0001104659-26-019119` and source hash. All three reviewed rows—the current-year
  annual-profit (2684), diluted-share (2689), and diluted-EPS (2691) rows—were not
  flat-retained, so none was sent, proposed, quote-validated, classified, or
  published. Their enclosing earnings-per-share section (2678–2694) received
  meaningful raw Jev target scores (0.48 annual profit, 0.60 diluted EPS, 0.56
  diluted shares) but was marked `skipped` because the configured 12-section
  selection limit was reached. The first observed loss point is therefore bounded
  outline-section selection, upstream of chunking, Findings, and the Decimal JSON
  amount protocol. The unchanged diagnostics made 36 calls for 250 retained source
  lines and persisted 254 decisions, including 182 explicit request-budget partials;
  the run is partial only for that diagnostic budget. Next bounded experiment: replay
  RANI from the fixed set and persist its first source-row loss point before changing
  product behavior. A direct-worker attempt `v2-94b4dded91fe` was interrupted after
  source acquisition and is explicitly excluded from this cohort.
- T39 uncertain-section routing experiment: two fresh NBHC runs tested the bounded
  reserve change under revisions `t39-nbhc-uncertain-chunk-v1` and
  `t39-nbhc-uncertain-chunk-v2`. Run `v2-6390282b93e0` moved the reviewed EPS
  section into chunking and scored its chunk highly (`0.92` annual profit, `0.97`
  diluted EPS, `0.96` diluted shares), but the chunk was still crowded out by the
  12-chunk retention cap. The follow-up reserve implementation increased detailed
  retention to 16 chunks, but run `v2-cd5da26653b3` saw the same section drift to
  `0.59` diluted EPS and fall outside the five-section uncertain band; Findings
  published zero findings. These runs do not establish an improvement. They show
  Jev score instability/saturation makes another threshold or reserve-size tweak
  unsafe. The next bounded slice is deterministic target-shaped source reserve
  routing, measured against the fixed replay rows before changing evaluation.
- T39 target-shaped source-reserve routing slice: added a versioned, bounded
  visible-source vocabulary reserve (at most three sections and one detailed
  Jev-qualified chunk per reserved section). It does not read replay expectations,
  XBRL, facts, findings, or evaluation outputs, and it still requires detailed Jev
  scoring and exact quote validation. A normal live NBHC acquisition under
  `t39-target-shaped-reserve-v1` fetched the same accession but a different canonical
  source hash, so the fixed replay contract correctly refused to bind it. Two fresh
  controlled replays then used only the already persisted hash-pinned NBHC source:
  `v2-9a1fe9973166` / `t39-target-shaped-reserve-v2-controlled` first flat-retained
  the reviewed EPS section but let its normal detailed-selection reason lose reserve
  provenance, so Findings request-budget fallback dropped all three rows. The measured
  correction preserves source-reserve provenance even when the chunk is selected by
  the ordinary detailed policy. In `v2-79e5397852d8` /
  `t39-target-shaped-reserve-v3-provenance`, section 2678–2694 was selected as the
  bounded target-shaped source reserve (scores 0.91 annual profit, 0.97 diluted EPS,
  0.97 diluted shares); all three fixed rows (2684, 2689, 2691) were flat-retained and
  sent to Findings. None was proposed, quote-validated, classified, or published.
  Thus routing is no longer the first observed loss point for this NBHC source, but
  this one replay does not establish a retrieval or accuracy improvement; Findings
  proposal selection is now the first observable loss point. Local acceptance:
  `uv run pytest tests/task_gates/test_t39.py -q` — **14 passed** (one existing
  Starlette/AnyIO warning); `uv run ruff check .` and `git diff --check` passed.
  Next bounded experiment: replay one other source-hash-pinned fixed-set case with
  this unchanged reserve and inspect whether it preserves source-row routing without
  creating a new proposal-selection failure before altering prompts or Findings input.
- T39 Findings-selection audit slice: persisted bounded per-retained-core-line audit
  entries beside the existing structural proposal audit: whether a line was sent or
  dropped by Findings request budgeting, proposal and quote-validation counts, and
  finite Jev type-classification scores/reason when a quote-valid proposal exists.
  It is diagnostic-only, never provider input, and renders on the fixed source-row
  trace. Fresh controlled NBHC replay `v2-15f081775e3b` under
  `t39-findings-line-audit-v1` reused the hash-pinned source. All three reviewed rows
  (2684, 2689, 2691) were sent to Findings with zero proposals; the model instead
  proposed lines 723, 727, and 735 (plus one repaired line 630). This confirms that
  proposal selection—not source routing, request-budget dropping, or quote validation
  of the reviewed rows—is the active loss point for this source. The run again had
  zero exact matches of four independent expected facts. Next bounded experiment:
  inspect the same audit on one other source-hash-pinned replay before changing
  Findings proposal behavior or type classification.
- Fresh five-run cohort after local-data reset (all application revision `0.1.0`):
  TOL, TRC, RSCF, MCHB, and NRP confirm mixed behavior rather than a single universal
  failure. MCHB recovered all three intended types (one exact and two scale-aware
  outcomes) but also published three unrelated unresolved values; TOL emitted all
  three intended types with one scale-aware outcome; TRC omitted diluted EPS despite
  all 430 audited retained lines reaching Findings; NRP dropped 168 of 397 retained
  lines at the Findings size fallback and emitted only annual profit. RSCF exposed a
  deterministic repair-path defect: two first-pass quote-valid findings were discarded
  when two unrelated invalid proposals triggered repair, leaving zero published
  findings and three misses. This defect is the next safe implementation slice, now
  recorded as T40. T41 is intentionally deferred until T40 has a fresh RSCF replay and
  a new cohort. The new task contracts are in `docs/TASKS.md`.
- T40 citation-repair preservation slice: the Findings service now retains every
  quote-valid first-pass finding while passing only invalid proposals to its one bounded
  repair call. Quote-valid repair output is combined with the retained first-pass set
  before the existing exact-quote/Decimal deduplication, so an unrelated invalid
  proposal cannot erase a valid finding. The persisted proposal audit now labels
  first-pass valid findings, invalid proposals, and repair-produced findings without
  duplicating generated quotes or amounts. Focused contracts cover both a failed repair
  retaining a valid first-pass finding and a valid repair merging without an equivalent
  duplicate: `uv run pytest tests/task_gates/test_t40.py -q` — **2 passed**;
  `uv run pytest tests/task_gates/test_t39.py -q` — **14 passed** (one existing
  Starlette/AnyIO deprecation warning); `uv run ruff check .` and `git diff --check`
  passed. The required next step remains a fresh RSCF replay under a new explicit
  application revision, followed by its persisted selection-audit and Findings/
  Evaluation review; no accuracy improvement is claimed from local contract coverage.
- T40 post-implementation five-run cohort observation: on 2026-09-27, fresh runs
  `v2-20ce18218fba` (DXCM), `v2-8fac68c9a1d4` (MDRR), `v2-d4bb088cd2ea`
  (DBVTF), `v2-2bc1c9632f29` (MGM), and `v2-88b68473aece` (CAR) all used
  application revision `0.1.0`, so they are not the required explicitly versioned
  T40 RSCF replay. Each made one Findings extraction call, published only first-pass
  quote-valid findings (respectively 4, 3, 4, 5, and 4), and persisted zero invalid
  proposals, repair attempts, or repair-produced findings. The cohort therefore shows
  that the normal exact-citation path remains intact but does not exercise or verify
  T40's mixed-response preservation branch. No citation-repair behavior change is
  supported before the RSCF gate. MDRR retained three quote-valid but unresolved
  findings because its type-classification requests exceeded their visible-context
  budget; this is post-extraction metadata, not a citation loss. CAR and DBVTF also
  surfaced quote-valid competing/older-period values, while MGM surfaced unrelated
  visible values. These are observations for the deferred T41 core-selection question,
  not a basis to change T40 prompts, routing, thresholds, classification, or
  evaluation. The next required evidence remains a fresh RSCF run under a new explicit
  application revision whose persisted audit includes both a first-pass valid finding
  and an invalid proposal, then confirms the valid finding survives the bounded repair.
- T40 RSCF mixed-response replay (provenance excluded): run `v2-4013d843a59f` on
  2026-09-27 did exercise the target repair path. Its first Findings response had two
  invalid proposals (both amount-not-visible errors on lines 529 and 532) and two
  quote-valid first-pass findings: annual loss `459,028` on line 261 and diluted shares
  `85,217,785` on line 535. Its one bounded repair call returned two still-invalid
  proposals; nevertheless both independent first-pass findings survived publication.
  The audit therefore records two `first_pass_valid_finding` entries, four
  `invalid_proposal` entries (two with `repair_attempted`), zero repair-produced
  findings, two Findings calls, and two final rejected citations. Evaluation independently
  exact-matched the diluted shares, marked the annual loss scale-aware equivalent, and
  missed diluted EPS. This confirms the intended preservation behavior without weakening
  exact quote or Decimal validation, but must not close T40's live gate: the run persisted
  application revision `0.1.0` rather than a new explicit T40 revision. Rerun the same
  RSCF replay under a new immutable `PROFITLAB_APPLICATION_REVISION`, then inspect the
  same audit before beginning T41. No additional code change is supported by this replay.
- T40 RSCF live gate: on 2026-09-27, fresh run `v2-13f3c7582c1a` used explicit
  application revision `t40-rscf-replay-v1` / version `v2-7e6d908ec96e5ea3`.
  It completed all eight stages on RSCF's 2023-12-31 10-K. The persisted Findings
  audit records two first-pass invalid proposals (lines 529 and 532, both
  `amount is not visible in the exact quote`) and two independent quote-valid
  first-pass findings: annual loss `459,028` (line 261) and diluted shares
  `85,217,785` (line 535). The single bounded repair call returned two still-invalid
  proposals for the same lines, but both first-pass valid findings were published,
  exactly as T40 requires. Evaluation independently exact-matched diluted shares,
  marked annual loss scale-aware equivalent, and missed diluted EPS. This closes
  T40's live gate without changing exact quote/Decimal validation, prompts, routing,
  thresholds, classification, or evaluation. T41 must still not begin: its required
  fresh post-T40 small report cohort has not been created and reviewed.
- T40 post-gate cohort review: the user reset local data and ran batch
  `batch-9ba7b20075c1` on 2026-09-27. Four reports completed (ALIS, SPEGU, JBL,
  and PLUS); its fifth bounded picker attempt was explicitly skipped because no
  eligible ticker was found. The runs retain the then-default revision `0.1.0`,
  which denotes the current checkout rather than old code but is not a useful
  experiment label. The persisted line audits establish T41's trigger: SPEGU's
  Findings size fallback sent 148 retained core lines and dropped 39, then published
  competing Class A and Class B diluted-EPS values; ALIS published competing
  class-specific diluted-EPS and diluted-share values. JBL published three intended
  types with scale-aware outcomes; PLUS published all three intended types but its
  annual-profit and diluted-share comparisons were Jev-rejected. All 16 proposals
  across the completed runs were quote-valid first-pass findings; no repair call ran.
  This is cohort evidence of the broad-request precision/layout problem, not a claim
  that a new packet design will improve accuracy. T41 is now unblocked.
- Automatic application revision slice: new Settings instances now default to a
  deterministic Git commit plus tracked-worktree/untracked-file-manifest fingerprint,
  rather than static package label `0.1.0`. An explicit
  `PROFITLAB_APPLICATION_REVISION` still overrides it for named experiments. This
  makes new local pipeline runs comparable only when they share both checkout and
  worktree state; focused T38 provenance coverage passed (5 tests).
- Latest verified task: T31 local acceptance; manual browser inspection and reviewed
  real-case benchmark verification remain pending.
- Last runnable T13 demo: `demo-t13-20260920` (complete offline managed workflow and validated synthetic report).
- Earlier runnable demos: `demo-t11` and `losses-t11` (annual calculations and preliminary metrics tables; latest calculation snapshots use finalized code). Earlier demos remain readable.
- Decisions: Python + uv; Pydantic; Pydantic AI; configurable OpenAI-compatible Chat Completions provider; separate Jev API; FastAPI/Jinja local UI; SQLite plus bounded source/payload blobs. Previous run data is unsupported by the active plan.
- Scope: up to four fiscal years of 10-Ks; common-share earnings and diluted EPS, with supporting share-count information. Actual investment return is outside this version.
- Data-retention decision: the user authorizes discarding the current local V2 data when
  the fresh-only schema/storage cleanup is performed; no compatibility or preservation
  work is required for existing local runs.
- Current external blockers: browser visual inspection lacks Computer Use permissions. Live Jev and LLM compatibility probes passed after the follow-up fixes; SEC discovery/download checks remain recorded below.

## T35 decision record

The reviewed real-run sample and chosen exact-evaluation contract are in
[`T35_EVALUATION_DECISION.md`](T35_EVALUATION_DECISION.md). It records DV
(`0001104659-26-020499`), NOEM (`0001213900-26-027784`), and TRC
(`0001628280-26-019685`) with raw comparison counts, representative visible
source lines, oracle limitations, false-positive/false-negative risks, and the
approved split between strict exact audit units and separate semantic review.
The result is **both** a source-to-finding metadata improvement and an
evaluation-contract redesign: incomparable values are excluded rather than
being called discovery misses.  The immediately applied safe correction makes
Company Facts concepts ordered fallbacks per metric, preventing `NetIncomeLoss`
and `ProfitLoss` from becoming duplicate expected facts for a new run.  The
remaining versioned review unit, UI denominator, and cross-run aggregation are
T36; visible scale/attribution extraction belongs to T39.
The Evaluation UI now labels its historical counts as a diagnostic comparator,
names the SEC Company Facts / annual / exact-Decimal / literal-unit contract,
and does not present the old metric-period count as the new strict-exact
denominator.

### T35 local acceptance and handoff

- Reviewed three persisted real SEC primary-filing runs on 2026-09-24: DV
  `v2-b95f2d36e162` / `0001104659-26-020499`, NOEM
  `v2-833668489686` / `0001213900-26-027784`, and TRC
  `v2-36c40a279e2b` / `0001628280-26-019685`. The review used their stored
  source quotes, findings, Company Facts facts, and comparisons; it made no
  SEC, Jev, or LLM call.
- Inspected the changed evaluation area first. No dedicated T22/T28 evaluation
  tests remain after prior cleanup; `test_t35.py` is the focused replacement
  contract. It covers the confirmed TRC duplicate-concept conflict and the DV
  explicit-thousands unit mismatch. The saved fixture is a narrow, controlled
  extract of reviewed Company Facts values, not an offline application mode.
- `time uv run pytest tests/task_gates/test_t35.py -q` — **2 passed** in 0.59s
  (0.93s wall). `uv run ruff check .` and `git diff --check` passed.
- Browser automation was not run per task policy. Manual verification: start
  `uv run profitlab serve`, then open each reviewed run's **Evaluate** stage:
  `/v2/runs/v2-b95f2d36e162/pipeline/evaluate`,
  `/v2/runs/v2-833668489686/pipeline/evaluate`, and
  `/v2/runs/v2-36c40a279e2b/pipeline/evaluate`. Open the diagnostic evidence
  for DV's scale-aware cards, NOEM's additional/unsupported cards, and TRC's
  duplicate-oracle card; compare the linked quotes with the decision record's
  classifications. These historical cards remain diagnostic until T36 adds the
  versioned eligible/incomparable denominator.
- Next: **T36 — Overall cross-run evaluation scorecard**.

## T36 local acceptance and handoff

- Added a persisted `t36-strict-exact-v1` scorecard snapshot (superseded by the
  clarified `t36-strict-exact-v2` contract below). It fingerprints both
  its contract and all persisted run/comparison inputs, so unchanged aggregates are
  reused and changed evaluation data deterministically produces a new snapshot. It
  performs no SEC, Jev, or LLM call.
- The strict denominator includes only exact Company Facts annual/literal-unit/Decimal
  positives and explicitly missed comparable facts. Period, unit, scale, duplicate,
  and other T35 diagnostic ambiguities are counted as incomparable rather than false
  negatives. Deterministic and Jev-assisted matrices remain separate; true negatives
  stay unavailable because there is no reviewed negative-candidate denominator.
- Every persisted run is in the scorecard ledger. Completed evaluations with records
  are included; queued, failed, cancelled, partial, and empty evaluations carry their
  precise exclusion reason. The UI names the contract/denominators, shows matrix and
  per-metric/period metrics, and links each TP/FP/FN record to its Evaluate stage.
- Inspected the pre-existing scorecard and T35 tests first. Added
  `tests/task_gates/test_t36.py` for a hand-built multi-run matrix, incomplete-run
  accounting/zero denominators, and the route’s displayed denominator and record link.
  Updated the fresh-schema contract for `evaluation_scorecards`; no obsolete tests
  were removed.
- `time uv run pytest tests/task_gates/test_t36.py tests/task_gates/test_t35.py tests/task_gates/test_t33.py -q`:
  **8 passed** in 0.80s (1.17s wall), with one Starlette/AnyIO deprecation warning.
  Shared-storage scope also required `time uv run pytest -q`: **11 passed** in 0.84s
  (1.11s wall), with the same warning. `uv run ruff check .` and `git diff --check` passed.
- No live/provider validation was needed or attempted. Browser automation was not run
  per task policy. Manual verification: after `uv run profitlab serve`, open
  `/v2/benchmark`. With at least two completed runs and one incomplete run, confirm
  each appears in the ledger, choose either matrix’s TP/FP/FN record link, and confirm
  the linked Evaluate record and the displayed precision/recall/F1 reproduce its cells.
- Next: **T37 — Sequential random-report batch runner**.

## T37 local acceptance and handoff

- Added durable sequential report batches with a conservative configured requested-count
  maximum (default 5), a bounded selection-attempt limit, item-by-item outcome ledger,
  and links to every independently inspectable child run. The coordinator selects only
  after the preceding child is terminal and never creates parallel pipeline tasks.
- The existing live eligible-ticker picker now accepts an exclusion set. The batch also
  rejects an accidentally repeated picker result, records picker exhaustion/skips and
  child failures, and makes no provider request itself. Cancellation stops future
  selection after the current child reaches a terminal state; resume preserves all
  earlier attempts and selects only the remaining count.
- Added a home-page batch form and a bounded progress page with requested/completed,
  failed, cancelled, skipped, and active counts, per-attempt remediation, plus cancel
  and resume controls. No browser automation was run per task policy.
- Inspected the T36 scorecard/storage gates first. Added `tests/task_gates/test_t37.py`
  covering injected picker selection, one-at-a-time execution, duplicate rejection,
  picker exhaustion, cancellation/resume, and the batch form limit/progress route. No
  obsolete tests were removed.
- `time uv run pytest tests/task_gates/test_t37.py tests/task_gates/test_t36.py tests/task_gates/test_t33.py -q`:
  **9 passed** in 0.92s (1.28s wall), with the existing Starlette/AnyIO deprecation
  warning. Shared storage/orchestration scope required `time uv run pytest -q`:
  **14 passed** in 0.84s (1.12s wall), with the same warning. `uv run ruff check .`
  and `git diff --check` passed.
- No live SEC, Jev, or LLM calls were attempted; browser automation was not run per
  policy. Manual verification: run `uv run profitlab serve`, open `/`, set **Reports**
  to `3`, and click **Start sequential batch**. On its progress page, observe that
  only one attempt is active, open each created report link, and verify distinct
  tickers. Click **Cancel after active report**, wait for its terminal outcome, then
  click **Resume remaining reports**. Finally open `/v2/benchmark` and confirm the
  completed and incomplete child runs both appear in the scorecard ledger.
- Next: **T38 — Versioned run timing and evaluation cohorts.**

## T38 local acceptance and handoff

- New runs capture an immutable content-addressed version identifier from the declared
  application revision plus behavior-affecting pipeline, prompt, model, selection, and
  evaluation settings. An unknown application revision is visibly non-comparable.
- Run timing now persists monotonic total, queued, and active durations; each stage
  persists active, queued, and retry/backoff components. Cancelled active stages retain
  their elapsed monotonic active duration. Workspace and batch pages display compact
  version/timing provenance.
- The scorecard contract is now `t38-strict-exact-v1`. It selects one version cohort,
  accounts for all other cohorts separately, and never pools them into matrix or
  precision/recall/F1 denominators. The scorecard exposes direct cohort selectors.
- Added `tests/task_gates/test_t38.py` for immutable version capture, a changed setting
  producing a separate cohort, completed timing persistence, cancelled-stage timing,
  and cohort isolation. `uv run pytest -q` — **19 passed**; `uv run ruff check .` and
  `git diff --check` passed (with the existing Starlette/AnyIO deprecation warning).
- No SEC, Jev, or LLM calls were needed. Browser automation was not run per policy.
  Manual verification: create two runs with the same `PROFITLAB_APPLICATION_REVISION`
  and one after changing a versioned setting. Inspect each workspace for total/stage
  timing and version. Open `/v2/benchmark`, choose the shared cohort, and confirm only
  its runs contribute to the matrix; select the other cohort and confirm it remains
  separate.
- Next: **T39 — Context-aware Jev scoring and compact findings evidence.**

### T36 scorecard clarification

- An accepted visible finding whose assumed configured Company Facts target is absent
  or unsupported is now a false positive, not an incomparable record. The persisted
  scorecard contract is versioned as `t36-strict-exact-v2`; only genuinely undecidable
  oracle cases remain incomparable. The decision record and scorecard copy state this
  boundary explicitly. `time uv run pytest tests/task_gates/test_t36.py
  tests/task_gates/test_t37.py tests/task_gates/test_t35.py -q` — **9 passed** in
  0.97s (1.33s wall); `time uv run pytest -q` — **15 passed** in 0.88s (1.16s
  wall), both with the existing Starlette/AnyIO deprecation warning. Ruff and diff
  checks passed; live/browser verification remains pending.

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
| T15 | Canonical visible source and exact anchors | DONE | Offline source passed; live SEC/browser inspection pending |
| T16 | LLM outline with source-coverage validation | DONE | Fixture offline acceptance passed; live LLM/SEC and manual UI inspection pending |
| T17 | Jev section scoring | DONE | Offline fixture acceptance passed; live Jev/manual UI pending |
| T18 | Source-range chunking with bounded overlap | DONE | Manual browser inspection and live SEC/Jev source pending |
| T19 | Jev detailed chunk scoring | DONE | Offline fixture acceptance passed; live Jev/manual UI pending |
| T20 | Quote-backed findings | DONE | Manual browser and live LLM verification pending |
| T21 | Post-discovery SEC Company Facts | DONE | Offline fixture acceptance passed; live SEC/manual UI pending |
| T22 | Independent fact comparison | DONE | Offline fixture acceptance passed; live SEC/LLM/manual UI pending |
| T23 | Consolidated modern pipeline UI | DONE | Manual browser inspection pending |
| T24 | Provider, persistence, and resume optimization | DONE | Offline replay passed; live verification pending |
| T25 | Remove obsolete execution paths and tests | DONE | Not applicable |
| T27 | Outline-aware findings inputs | DONE | Offline request/input acceptance passed; live/manual inspection pending |
| T28 | Scale-aware Jev evaluation verdicts | DONE | Manual browser and live Jev verification pending |
| T29 | Readable evaluation comparison cards | DONE | Manual browser inspection pending |
| T30 | Random eligible ticker picker | DONE | Manual browser and live SEC picker verification pending |
| T31 | Retrieval benchmark and baselines | DONE | Not run |
| T32 | Final real-data demonstration | DONE | Eight live filings recorded; browser automation not run |
| T33 | Fresh-only storage schema; remove migrations | DONE | Not applicable |
| T34 | Remove offline fixture source mode | DONE | Live run not repeated; local prerequisite and source-contract checks passed |
| T35 | Diagnose and redesign exact-match evaluation | DONE | Three persisted live SEC runs reviewed; manual browser inspection pending |
| T36 | Overall cross-run evaluation scorecard | DONE | Manual browser inspection pending |
| T37 | Sequential random-report batch runner | DONE | Manual browser and live SEC/provider batch verification pending |
| T38 | Versioned run timing and evaluation cohorts | DONE | Manual browser inspection pending |
| T39 | Jev-directed adaptive source context and target eligibility | IN_PROGRESS | Batched IWAL diagnostic replay ran; no semantic improvement established |
| T40 | Preserve valid Findings through citation repair | DONE | Fresh, explicitly versioned RSCF mixed-response replay passed |
| T41 | Measured target-shaped Findings core batches | DONE | 15-run versioned cohort reviewed; no gain claim; evaluator linkage/coverage diagnostic is next |

## T32 final evidence

- Live prerequisites were present on 2026-09-24 (SEC contact, Jev key, and LLM
  configuration). The first real run, `v2-da452efc7988` for MSFT's 2026-06-30
  10-K, reached all eight implemented stages. Its primary visible filing source
  contained 1,970 canonical sanitized lines (source hash
  `96d03620b06dc4d1c4c556a8c2c447bab9026f0835e176d15c67dd8d46e3ecba`).
  It produced 71 validated outline sections, Jev-scored 71 sections in 18
  batches (12 selected, 4 uncertain), built 17 chunks from 362 primary lines,
  Jev-scored 17 chunks in five live batches (12 retained, one uncertain), and
  published four exact quote-validated findings. Facts started only afterward
  and normalized three annual independent Company Facts. Evaluation preserved
  zero deterministic exact matches and recorded three separate scale-aware Jev
  equivalences; it did not change discovery output.
- The source-to-first-run wall time was 509.3 seconds, including a deliberate
  resume after an observed finding-type context-size limit. Persisted evaluation
  measurements: 10.61% retained source, 2.46 seconds to first finding after the
  resumed findings work began, 9.30 seconds evaluation latency, five recorded
  provider requests with 16,241 input and 3,636 output tokens, plus three
  scale-verdict Jev calls (3,356 input/69 output tokens). The live run's local
  performance summary reports a 275,730,432-byte database at its measurement
  point; the shared `data/` directory was 3.1G after existing workspace data.
- Initial live Findings exposed a bounded failure: the post-extraction
  finding-type Jev payload exceeded its 30,000-character context budget. A
  quote-validated finding must not be discarded for that optional classification,
  so classification now leaves only that finding `unresolved`, records
  `classification_budget_limited`, and permits Facts/Evaluation to continue.
  The persisted run was successfully resumed from checkpoints. The web resume
  route was also made asynchronous; its prior synchronous form could persist a
  queued run before failing to schedule its worker. A queued run is resumable
  only when it already has a stopped stage, preventing fresh queued runs from
  being accidentally started through resume.
- Focused validation after those fixes:
  `time uv run pytest tests/task_gates/test_t14.py tests/task_gates/test_t20.py tests/task_gates/test_t24.py tests/task_gates/test_t27.py tests/task_gates/test_t31.py -q`
  — **17 passed** in 3.19 seconds (3.56 seconds wall time), with the existing
  Starlette/AnyIO deprecation warning. `uv run ruff check .` and
  `git diff --check` passed. Browser automation was not run per task policy.
- The existing local workspace supplied seven additional real completed filings:
  FIX, FLR, LILA, DSGN, GDOT, MFAN, and SPGI. They span materially different
  structures and include persisted misses, ambiguous duplicates, unsupported
  comparisons, an additional visible value, and two invalid/quote-rejected DSGN
  proposals. ENSC is retained as a live source failure with no fabricated later
  output. The concise setup, measurements, source provenance, limitations, and
  two-minute manual verification path are in `docs/T32_DEMONSTRATION.md`.
  Durable cancellation/restart and malformed/invalid quote contracts are covered
  by the focused tests listed above. Browser automation was not run by policy.
  This bounded sample is not a population-accuracy estimate.

## Instruction for the implementing agent

1. Read this file and the relevant specification before editing.
2. Select the first TODO task whose dependencies are DONE. Resume an IN_PROGRESS task first.
3. Announce the task and its user-visible result. Implement only that bounded task and necessary fixes.
4. Use `uv` for dependencies, scripts, and tests. Preserve `uv.lock`.
5. Run the task's automated checks and its offline demo. Inspect its browser page when browser tooling is available; otherwise record that visual verification remains unrun.
6. Record actual commands, results, artifact/run IDs, and limitations below. Never invent a successful live call or browser inspection.
7. Mark DONE only when the local acceptance criteria pass. A blocked external check stays visibly pending, and compatible later offline work may continue.
8. Stop after the task. Tell the user what to open, what to click, what they should see, and the next task ID.

## T33 handoff

Implemented: replaced the V2 SQLite upgrade chain with one authoritative schema
creation script. A new database is marked with a stable application identifier; an
existing unmarked, malformed, or incomplete database is refused with an actionable
message and is not converted, read for run data, or deleted. The README now states the
fresh-only boundary and the exact reset command: `rm -rf data/v2` (or the `v2`
subdirectory of `PROFITLAB_DATA_DIR`).

Tests inspected: `tests/task_gates/test_t14.py` remained the focused clean-storage and
pipeline integration coverage. Added `tests/task_gates/test_t33.py` for current-schema
creation and a deliberately legacy database whose bytes remain unchanged after refusal.
No migration-preservation tests remained; the upgrade code itself was removed.

Commands/results:

- Baseline: `time uv run pytest tests/task_gates/test_t14.py -q` — **4 passed** in
  1.17 seconds (1.58 seconds wall time).
- `time uv run pytest tests/task_gates/test_t33.py tests/task_gates/test_t14.py -q` —
  **6 passed** in 1.20 seconds (1.59 seconds wall time), with the existing
  Starlette/AnyIO deprecation warning.
- `time uv run pytest -q` — **49 passed** in 7.15 seconds (7.54 seconds wall time),
  with the same existing warning. `uv run ruff check .`, `git diff --check`, and a
  static V2-source/test search for migration or SQLite-version-upgrade code passed.

The authorized local reset was performed: removed `data/v2` (264 MB, containing the
former V2 SQLite files). It is intentionally not recoverable through ProfitLab.

## T34 handoff

Implemented: V2 runs no longer have a source mode. The run contract and fresh schema
no longer persist one; the home page has only the SEC ticker workflow; and source,
outline, section/chunk scoring, findings, Company Facts, and scale evaluation always
use their live adapters. Removed the synthetic source, fake provider, and synthetic
Company Facts runtime branches. Creating a run now requires a ticker and an
`SEC_USER_AGENT` containing a contact email before any run is persisted. The home page
returns the same actionable remediation when that setting is absent.

Tests: removed the obsolete fixture-pipeline acceptance suite, which asserted a
product path no longer offered. Added `tests/task_gates/test_t34.py` covering missing
SEC-contact refusal without persistence, successful live-contract creation, no mode
field/selector, and the retained canonical-source invariant.

Commands/results:

- `uv run pytest -q` — **5 passed** in 0.68 seconds, with the existing
  Starlette/AnyIO deprecation warning.
- `uv run ruff check .` and `git diff --check` passed.
- Static V2/UI search found no offline mode, synthetic source, or fixture-provider
  branch. The benchmark fixture remains a retrieval-evaluation dataset, not a V2
  source workflow.

Live status: not repeated; no external SEC or provider request was made for this
cleanup. Browser automation was not run per task policy.

Manual verification: run `uv run profitlab serve`, open `http://127.0.0.1:8000/`,
and confirm the form contains only a ticker and live SEC wording. Without
`SEC_USER_AGENT`, submit a ticker and confirm the page explains the contact-email
requirement. With SEC and provider credentials configured, create a ticker run and
confirm the Source stage identifies SEC primary filing HTML provenance. Next task: T35.

Follow-up source-parser fix: a newly observed live filing contained an element whose
`style` attribute was exposed as `None`, causing canonical source cleanup to fail before
the pipeline reached provider stages. `_is_hidden` now treats it as an empty style value.
Added a direct null-style regression and a canonical HTML integration case; `time uv run
pytest tests/task_gates/test_t15.py -q` passed **4 tests** in 0.97 seconds (1.35 seconds
wall time), with Ruff and diff checks clean.

Live verification is not applicable: this task performs no SEC or provider calls.
Browser automation was not run per task policy. Manual verification: stop a running
server, use an empty `PROFITLAB_DATA_DIR`, run `uv run profitlab serve`, and create a
live run from `/`; it should create the fresh database. Then leave an old V2 database
at `PROFITLAB_DATA_DIR/v2/profitlab-v2.sqlite3`, restart, and confirm startup refuses
with the reset instruction while the file is unchanged. Remove only that V2 directory,
restart, and confirm a clean workspace appears. Next task: T34.

## Latest task handoff

Task: T31 — Retrieval benchmark and baselines (complete local implementation).
Implemented: added an immutable, source-hash-bound benchmark manifest contract with
development/held-out case splits, reviewed source ranges, and required-fact source
locations. `RetrievalBenchmarkService` replays seven strategies after a run is sealed:
keep-all, heading/keyword, structural, Jev-section (Jev-only and application-policy),
and Jev-section-plus-chunk (Jev-only and application-policy). It reports relevant-range
recall, structured-fact coverage, exact-value accuracy, retained source percentage,
misleading-range retention, calls, latency, and first matching source line. Results pin
the score prompt/question/model identities, persist independently of discovery, clearly
label replayed provider identity, expose missed source ranges as links, and never invoke
or modify Jev/findings retrieval.

Tests inspected: `tests/task_gates/test_t22.py` and `tests/task_gates/test_t29.py` were
the closest comparison/UI contracts. Added `tests/task_gates/test_t31.py`, covering a
held-out immutable case, all strategies, exact fact/value accounting, persistence/UI,
and the non-leak guarantee that replay adds no section-scoring provider actions. No
obsolete tests were removed.

Commands/results:

- `time uv run pytest tests/task_gates/test_t31.py tests/task_gates/test_t29.py tests/task_gates/test_t22.py -q`:
  **7 passed** in 1.78 seconds (2.07 seconds wall time), with one pre-existing
  Starlette/AnyIO deprecation warning.
- `uv run ruff check .` and `git diff --check`: passed.
- `time uv run pytest -q`: **43 passed** in 6.01 seconds (6.31 seconds wall time),
  with the same warning.

Live verification and the held-out acceptance targets remain unrun: the checked-in
`fixtures/benchmark/v1.json` has no reviewed real company/accession cases, because no
saved real SEC source/provenance exists in this workspace to review honestly. The UI
therefore says it cannot extrapolate a benchmark to an unreviewed filing. Add immutable
reviewed cases (including their exact source hashes) before using the benchmark endpoint.
Browser automation was not run per task policy.

Follow-up UI correction: benchmark results now live on the separate cross-run
`/v2/benchmark` page, linked from Runs and every pipeline workspace; per-run Evaluate
pages no longer render an empty benchmark notice. The page lists every run's evaluation
and review status, then renders only persisted benchmark comparisons.

Follow-up automatic generation: each newly completed Evaluate stage now creates an
**automatic post-run replay** from that run's sealed findings, comparisons, Company
Facts, and persisted retrieval decisions. Existing completed runs can be populated with
the **Recalculate completed runs** control on `/v2/benchmark`; it makes no SEC, Jev, or
LLM requests. The page labels these as automatic operational metrics—not reviewed or
held-out truth—and retains reviewed cases as a distinct later mode. The automatic
generation/recalculation contract plus adjacent evaluation tests passed **7 tests** in
2.07 seconds; final `uv run ruff check .`, `git diff --check`, and full suite passed
with **43 tests** in 6.57 seconds (the existing Starlette/AnyIO warning remains).

Follow-up findings resilience: when assembled findings context exceeds the configured
request budget, Findings now keeps complete retained chunks in descending score order
until full-context capacity is reached. If needed it drops non-citable overlap and
unneeded outline navigation before returning an explicit empty limited result; it never
fabricates a finding or fails the entire run for that budget condition. The Findings
stage summary records the fallback. Added a controlled 1,000-character-budget contract;
the focused T20/T27 subset passed **7 tests** in 1.88 seconds and the final suite passed
**44 tests** in 6.74 seconds, with Ruff and diff checks clean.

Follow-up scorecard correction: automatic scorecards no longer report relevant-range
recall. Their old labels were derived from the same run's findings, making recall
circular and often 1.0. The cross-run page now calls this **Reviewed recall** and shows
**Not reviewed** for automatic runs; only immutable independently reviewed cases may
report recall and target achievement. Focused benchmark coverage and the final suite
passed (**44 tests** in 6.62 seconds), with Ruff and diff checks clean.

Manual verification once a matching reviewed case exists: start `uv run profitlab serve`
if needed, finish that exact run, POST to `/v2/runs/<run-id>/benchmark`, then open
`/v2/benchmark`. Confirm all strategy rows show their split, provider identity, pinned
configuration, targets met/not met, and any **Miss: lines** link opens the canonical
source range. The follow-up focused UI/test subset passed **10 tests** in 1.54 seconds;
Ruff and diff checks passed. The checked-in manifest intentionally has no fabricated
real-company reviews; adding independently reviewed development and held-out cases is
future benchmark-data work and does not change the completed implementation. Next task:
T32 — Final real-data demonstration.

Task: T30 — Random eligible ticker picker.
Implemented: added a **Start random eligible run** control beside the existing ticker
field. It calls a bounded picker endpoint that requires a configured SEC contact,
loads the existing SEC directory/cache, deduplicates normalized ticker symbols, and
confirms a one-year eligible 10-K through the existing discovery rules. It retries at
most five candidates (configurable, capped at 12), preferentially samples symbols not
already present in V2 runs, then creates and opens a `mode=live` run immediately.
When unavailable/exhausted it returns a clear error without creating a run. Compact
selection provenance remains stored for support purposes but is no longer rendered in
the UI. The form no longer exposes source mode and always posts `mode=live`; the
retained offline API is only for fixture/test workflows until T34.

Tests inspected: `tests/task_gates/test_t29.py` and `tests/task_gates/test_t14.py`
were the closest UI/storage coverage and passed in 1.77 seconds before the change; no
obsolete tests were removed. Added `tests/task_gates/test_t30.py` for injected
deterministic selection, duplicate symbols, an ineligible-then-eligible retry,
bounded exhaustion, an immediate successful live-run redirect, and preference for an
unprocessed ticker.

Commands/results:

- `time uv run pytest tests/task_gates/test_t29.py tests/task_gates/test_t14.py -q`:
  **7 passed** in 1.77 seconds (2.17 seconds wall time).
- `time uv run pytest tests/task_gates/test_t30.py tests/task_gates/test_t29.py tests/task_gates/test_t14.py -q`:
  **11 passed** in 1.83 seconds (2.17 seconds wall time).
- `time uv run pytest -q`: **41 passed** in 5.92 seconds (6.31 seconds wall time),
  with one pre-existing Starlette/AnyIO deprecation warning.
- `uv run ruff check .` and `git diff --check`: passed.

Live SEC selection was not attempted because this environment has no verified SEC
contact/configuration. Browser automation was not run per task policy. Manual
verification: start `uv run profitlab serve` if needed, open `/`, click **Start random
eligible run**, and confirm it redirects directly to a newly created live-run workspace.
Click again and confirm it favors a ticker not shown in prior V2 runs. With no SEC
contact or no eligible response, confirm the page gives the remediation message and
creates no run. Next task: T31.

Task: T29 — Readable evaluation comparison cards.
Implemented: replaced the dense evaluation table with a bounded page of compact cards:
one card per expected structured fact and clearly labelled separate cards for additional
visible findings. Each card leads with a four-part, unfilled comparison: **Finding**,
**Ground truth** (explicitly match or mismatch where applicable), **Heuristic
evaluator** (the exact-Decimal baseline), and **Jev verdict**. A confirmed Jev verdict
never appears as a changed source value. Status is expressed through plain language,
text color, and a border rather than colored backgrounds. Native controls filter by
outcome and reorder cards while the no-JavaScript view remains complete. Evidence
quote/source link, retained context, Company Facts provenance, provider model/prompt,
and diagnostic JSON are all behind progressive-disclosure controls. No evaluation data,
metrics, or provider requests were changed.

Commands/results:

- Inspected the affected T22, T23, and T28 evaluation/UI gates; no obsolete tests were
  removed because they continue to cover the data and workspace boundaries.
- Added `tests/task_gates/test_t29.py`: renders scale-aware confirmed, Jev-rejected,
  missing, and additional cards from persisted comparisons; verifies both amounts,
  separate baseline/verdict language, provenance and diagnostic disclosure, controls,
  and removal of the old evaluation table.
- `uv run pytest tests/task_gates/test_t29.py tests/task_gates/test_t22.py
  tests/task_gates/test_t23.py tests/task_gates/test_t28.py -q`: **7 passed** in
  1.69s, then **7 passed** in 1.86s after the layout clarification, with one existing
  Starlette/AnyIO deprecation warning. `uv run ruff check .` and `git diff --check`
  passed.
- Overlap-citation follow-up: evaluation still deduplicates an overlapping quote/value
  for its verdict and denominator, but now persists every matching finding ID on that
  comparison so the card displays every source citation. Added a regression for two
  identical persisted findings; `uv run pytest tests/task_gates/test_t29.py
  tests/task_gates/test_t22.py tests/task_gates/test_t28.py -q`: **6 passed** in
  1.77s, with the same warning; `uv run ruff check .` and `git diff --check` passed.
- Run-removal follow-up: Runs and the workspace expose a POST-only **Remove run**
  control. It cancels a still-running in-memory task, then atomically deletes only the
  selected run and its run-owned SQLite rows; shared provider caches remain intact.
  `uv run pytest tests/task_gates/test_t29.py tests/task_gates/test_t14.py
  tests/task_gates/test_t23.py -q`: **8 passed** in 1.97s, with the same warning;
  `uv run ruff check .` and `git diff --check` passed.
- Shared-cache/frontend-cache follow-up: Runs now exposes **Clear shared provider
  cache**, which removes reusable outline, section/chunk score, finding, and
  scale-verdict cache entries without touching runs or their source/results. Every app
  response, including static frontend assets, now sends `Cache-Control: no-store`.
  `uv run pytest tests/task_gates/test_t29.py tests/task_gates/test_t14.py
  tests/task_gates/test_t23.py -q`: **9 passed** in 2.09s, with the same warning;
  `uv run ruff check .` and `git diff --check` passed.
- Browser automation was not run per task policy. No live SEC or provider calls were
  made; manual browser and live-provider inspection remain pending.

With `uv run profitlab serve` running, create an offline `DEMO` run and open
**Pipeline → Evaluate**. Confirm every expected fact is a card whose status and both
amounts are readable without expanding details. Use **Status** and **Order** controls;
then expand a card to open its quote source link and Company Facts provenance. For the
saved scale-aware fixture, confirm **Confirmed scale-aware equivalent** still displays
the exact-Decimal baseline separately. On a narrow viewport, confirm the two amount
panels stack without hiding source direction or status.

Next: T30 — Random eligible ticker picker.

Task: T28 — Scale-aware Jev evaluation verdicts.
Implemented: exact-Decimal comparison remains the persisted deterministic baseline.
Only same-fiscal-period value mismatches become bounded evaluation candidates after
both findings and Company Facts are sealed. The new Jev request contains the finding
amount/optional period/unit, its declared core line, separately labelled retained
context, and one candidate fact amount/unit/period; it asks a single boolean question
and requires explicitly visible scale or unit support. A `true` verdict becomes
`scale_aware_equivalent`; a false verdict remains visible as `jev_rejected`, with the
original deterministic state, immutable input IDs, prompt version, and model identity.
The pair request is hash-cached, calls are bounded, and sanitized evaluation traces are
available on demand. No discovery service reads this post-seal material.

Commands/results:

- Timed predecessor boundary: `uv run pytest tests/task_gates/test_t22.py
  tests/task_gates/test_t27.py -q`: **6 passed** in 1.57s, with one existing
  Starlette/AnyIO deprecation warning.
- Added `tests/task_gates/test_t28.py`: controlled `237,789` versus `237,789,000`
  evidence with visible “in thousands” confirms scale-aware equivalence, while a
  genuine mismatch with no visible scale support is rejected. It also verifies the
  exact baseline remains non-exact, traces are persisted, and replay uses the pair
  cache without another fixture provider call.
- Final acceptance: `uv run pytest tests/task_gates/test_t14.py
  tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py
  tests/task_gates/test_t19.py tests/task_gates/test_t20.py
  tests/task_gates/test_t21.py tests/task_gates/test_t22.py
  tests/task_gates/test_t23.py tests/task_gates/test_t24.py
  tests/task_gates/test_t25.py tests/task_gates/test_t27.py
  tests/task_gates/test_t28.py -q`: **32 passed** in 4.36s, with the same warning;
  `uv run ruff check .` and `git diff --check` passed.
- Follow-up classification redesign: removed the prose-regex workaround. Findings now
  receive one Jev-visible-only finite-type classification—annual profit, diluted EPS,
  diluted shares, or unresolved—before the findings checkpoint is sealed. Evaluation
  uses only that sealed type and never reinterprets the quote. The later scale-aware
  judge receives the type but no XBRL concept mapping; the existing application-owned
  Company Facts mapping remains post-seal. Fixture Jev marks types unresolved rather
  than fabricating semantic certainty. `uv run pytest tests/task_gates/test_t14.py
  tests/task_gates/test_t15.py tests/task_gates/test_t16.py tests/task_gates/test_t17.py
  tests/task_gates/test_t18.py tests/task_gates/test_t19.py tests/task_gates/test_t20.py
  tests/task_gates/test_t21.py tests/task_gates/test_t22.py tests/task_gates/test_t23.py
  tests/task_gates/test_t24.py tests/task_gates/test_t25.py tests/task_gates/test_t27.py
  tests/task_gates/test_t28.py -q`: **33 passed** in 4.83s; `uv run ruff check .` and
  `git diff --check` passed.
- Type-classification cache follow-up: the exact persisted findings request now caches
  its sealed Jev type verdict alongside the validated proposals. `uv run pytest
  tests/task_gates/test_t20.py tests/task_gates/test_t22.py tests/task_gates/test_t24.py
  tests/task_gates/test_t27.py tests/task_gates/test_t28.py -q`: **13 passed** in
  2.42s; `uv run ruff check .` and `git diff --check` passed.
- Evaluation-context follow-up: same-value/same-period unit-label differences now enter
  the bounded Jev judgment rather than becoming both a missed fact and an additional
  finding. The judge receives the complete retained chunk core plus overlap context;
  it does not infer from an abbreviated quote. `uv run pytest tests/task_gates/test_t22.py
  tests/task_gates/test_t28.py -q`: **4 passed** in 1.32s; `uv run ruff check .` and
  `git diff --check` passed.
- Retrieval/type inspection follow-up: finding cards now show the highest source chunk
  retrieval label and score across the same three finite finding types beside the
  later Jev type classification. The page loads only score records for its bounded
  finding page. `uv run pytest tests/task_gates/test_t20.py tests/task_gates/test_t23.py
  tests/task_gates/test_t28.py -q`: **6 passed** in 1.70s; `uv run ruff check .` and
  `git diff --check` passed.
- Browser automation was not run per task policy. No live SEC or Jev calls were made;
  manual browser and live-provider verification remain pending.

With `uv run profitlab serve` running, create an offline `DEMO` run and open
**Pipeline → Findings** and confirm each fixture item is visibly **unresolved** rather
than fabricated as a semantic type; open the sanitized findings trace to inspect the
finite visible-only Jev type question. Then open **Pipeline → Evaluate**. Confirm exact Decimal results remain labelled separately.
For a controlled saved comparison whose finding is `237,789`, fact is `237,789,000`,
and retained source context says “in thousands,” confirm the state is **scale aware
equivalent** while the baseline says **period match value mismatch**. Open **Inspect
sanitized evaluation provider trace** to verify the boolean request and fixture/model
provenance. With configured live credentials, repeat this on a real visible scale label;
that live check remains pending.

Next: T29 — Readable evaluation comparison cards.

Task: T27 — Outline-aware findings inputs.
Implemented: the single bounded findings request now includes the complete persisted
validated outline once, with labeled generated topics, exact visible titles/quotes where
available, section IDs, and canonical line ranges. Every retained chunk identifies its
outline section and separates numbered core evidence lines from context lines. Every
finding must declare one core source line and quote only from that line; context cannot
be cited. Trusted filing `report_date` metadata supplies the requested current
fiscal-reporting year; the findings prompt asks for that year's values and treats both
the outline and year as orientation rather than evidence. The exact quote validates the
numeric value; period, unit, and scale may use separately retained visible chunk context.
Findings are structured values rather than model-written narrative: every published item
has a required Decimal amount mechanically matched to its quote, while period remains
optional.
Findings diagnostics and the workspace now report the requested year plus separate
outline-context and retained-evidence character counts. String `limitations` values are
normalized to a one-item list before validation. The findings prompt version is
`findings-v4-required-amount`, so previous findings batches are not reused.

Commands/results:

- Timed predecessor boundary: `uv run pytest tests/task_gates/test_t20.py -q`:
  **2 passed** in 0.96s, with one existing Starlette/AnyIO deprecation warning.
- Added `tests/task_gates/test_t27.py`: asserts the full persisted outline appears once
  in the findings request, chunks retain outline lineage, trusted report year `2025` is
  supplied, diagnostics record the separate payload sizes, and a current-year period can
  use separate retained visible context rather than the number quote itself. It also
  verifies a context line cannot be used as a finding citation.
- Focused acceptance: `uv run pytest tests/task_gates/test_t20.py
  tests/task_gates/test_t27.py -q`: **4 passed** in 1.26s, with the same warning.
- Affected regression: `uv run pytest tests/task_gates/test_t19.py
  tests/task_gates/test_t20.py tests/task_gates/test_t21.py
  tests/task_gates/test_t22.py tests/task_gates/test_t23.py
  tests/task_gates/test_t27.py -q`: **12 passed** in 2.34s, with the same warning;
  `uv run ruff check .` and `git diff --check` passed.
- Citation-boundary follow-up: the same affected command now reports **13 passed** in
  2.41s, with the same warning; `uv run ruff check .` and `git diff --check` passed.
- Required-amount follow-up: findings no longer accept model-written narrative. They
  require an `amount` Decimal that matches a numeric token in the declared core-line
  quote; `period` remains optional. `uv run pytest tests/task_gates/test_t20.py
  tests/task_gates/test_t27.py -q` reported **6 passed** in 1.42s, with the same
  warning; the broader contract/findings/evaluation/UI boundary reported **12 passed**
  in 2.07s. `uv run ruff check .` and `git diff --check` passed.
- Browser automation was not run per task policy. No live SEC or LLM calls were made;
  manual and live inspection remain pending.

With `uv run profitlab serve` running, create an offline `DEMO` run and open
**Pipeline → Findings**. Confirm the card summary shows requested fiscal year **2025**
and separate outline/evidence sizes. Open **Inspect sanitized provider trace** and
confirm the request has one `validated_outline` array, `current_report_year: "2025"`,
and `outline_section_id` on each retained chunk. With configured live credentials,
verify that a current-year value is found only when its exact quote visibly supports the
reported period.

Next: T28 — Scale-aware Jev evaluation verdicts.

Task: T25 — Remove obsolete execution paths and tests.
Implemented: deleted the V1 flat pipeline, file-per-artifact repository, historical
CLI commands, legacy web routes/templates, screening/extraction/reconciliation/
calculation/report services, and their T01–T13 gates. The supported CLI now exposes
only `profitlab serve`; the UI exposes only fresh V2 runs. SEC discovery/transport,
provider transports, redaction, and V2 contracts remain with direct V2 ownership.
README now documents the V2 workflow and explicitly says historical run data is
unsupported.

Commands/results:
- Timed predecessor boundary: `time uv run pytest tests/task_gates/test_t14.py
  tests/task_gates/test_t15.py tests/task_gates/test_t16.py tests/task_gates/test_t17.py
  tests/task_gates/test_t18.py tests/task_gates/test_t19.py tests/task_gates/test_t20.py
  tests/task_gates/test_t21.py tests/task_gates/test_t22.py tests/task_gates/test_t23.py
  tests/task_gates/test_t24.py -q`: **26 passed** in 3.51s (3.87s wall time), with one
  existing Starlette/AnyIO deprecation warning.
- Added `tests/task_gates/test_t25.py`: asserts the supported CLI has only the V2 server
  command, legacy routes return 404, the home page has no historical-run surface, and
  deleted module paths do not remain.
- Final acceptance: `time uv run pytest -q`: **27 passed** in 3.71s (4.08s wall time),
  with the same warning; `uv run ruff check .` and `git diff --check` passed.
- Browser automation was not run per task policy. No live SEC, Jev, or LLM calls were
  made because credentials were not assumed; manual and live inspection remain pending.

With `uv run profitlab serve` running, open `http://127.0.0.1:8000/`. Confirm that the
home page offers only **Create fresh V2 run**, that no historical run list or legacy
analysis form appears, then create an offline `DEMO` run and open **Pipeline →
Findings**. Confirm the source and provider-trace drill-downs work. With configured
live credentials, create a live ticker run; that live verification remains pending.

Next: T27 — Outline-aware findings inputs.

Task: T24 — Provider, persistence, and resume optimization.
Implemented: V2 outline requests now reuse one LLM HTTP connection pool across its
ordered windows. Independent Jev section-score batches share one provider connection
pool and obey `V2_PROVIDER_CONCURRENCY` (default 3); their sanitized request hashes,
prompt/questions, relevant configuration, and pinned model identity gate cache reuse.
Completed batches are persisted before progress updates, so a fresh replay reuses them
without changing the deterministic scoring policy. Diagnostic action payloads above
2 KiB are compressed in SQLite transparently. New lookup indexes cover score/chunk/action
paths, and the persisted performance summary records wall time, distinct live/cache
request counts, database bytes, plus the latest reader-route latency and rendered payload
size. No source/chunk text duplication was introduced.

Commands/results:
- Timed predecessor boundary: `time uv run pytest tests/task_gates/test_t23.py
  tests/task_gates/test_t22.py -q`: **4 passed** in 1.14s (1.50s wall time), with
  one existing Starlette/AnyIO deprecation warning. No obsolete tests were removed:
  they cover the immediately preceding reader workspace and evaluation boundaries.
- Added `tests/task_gates/test_t24.py`: repeat-fixture replay preserves every section
  score/policy decision while reporting cache reuse and persisted wall/database/reader
  measurements, verifies transparent large-diagnostic compression, and proves explicit
  resume does not repeat a completed source checkpoint.
- Final acceptance: `uv run ruff check .`, `git diff --check`, and `time uv run pytest
  tests/task_gates/test_t14.py tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py tests/task_gates/test_t19.py
  tests/task_gates/test_t20.py tests/task_gates/test_t21.py tests/task_gates/test_t22.py
  tests/task_gates/test_t23.py tests/task_gates/test_t24.py -q`: **26 passed** in
  3.57s (3.88s wall time), with the same warning.
- Browser automation was not run per task policy. No live SEC, Jev, or LLM call was
  made because credentials were not assumed; actual live latency/concurrency gains and
  an interruption during an in-flight paid request remain the live verification gap.

With `uv run profitlab serve` running, open `http://127.0.0.1:8000/`, create two fresh
offline V2 `DEMO` runs, and open **Pipeline → Section Score** on the second. Confirm its
summary says cached batches were reused, while the selected/uncertain/skipped decisions
match the first. Open **Findings → Inspect sanitized provider trace** to confirm the
trace still renders after compressed diagnostic persistence. With configured live SEC,
Jev, and LLM credentials, repeat a same-source replay and inspect the saved performance
summary for distinct live/cache counts and reader route measurements; that live check
remains pending.

Next: T25.

Task: T23 — Consolidated modern pipeline and report UI.
Implemented: V2 runs now expose **Runs** and one reader-facing **Pipeline** workspace.
Its findings and evaluation stage cards remain the canonical place for quote-backed
findings, coverage, limitations, exact Decimal values, and audit IDs. Pipeline stages
retain their eight-step rail and use bounded pages of at most 100 repeated records.
Provider request/response diagnostics are no longer embedded in the main workspace; a
per-stage on-demand trace page exposes at most 100 sanitized actions. Live updates
coalesce bursts and skip polling while the page is hidden.

Commands/results:
- Timed predecessor boundary: `time uv run pytest tests/task_gates/test_t22.py
  tests/task_gates/test_t21.py -q`: **4 passed** in 1.23s (1.63s wall time), with
  one existing Starlette/AnyIO deprecation warning. The old inline-diagnostic
  assertions in T17/T19 were consolidated to assert the new on-demand trace link.
- Added `tests/task_gates/test_t23.py`: single-workspace pipeline/trace route coverage
  plus a storage pagination invariant proving a 101-record stage returns 100 then 1
  record.
- Final acceptance: `uv run ruff check .`, `git diff --check`, and `time uv run pytest
  tests/task_gates/test_t14.py tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py tests/task_gates/test_t19.py
  tests/task_gates/test_t20.py tests/task_gates/test_t21.py tests/task_gates/test_t22.py
  tests/task_gates/test_t23.py -q`: **23 passed** in 2.86s (3.18s wall time), with
  the same warning.
- Browser automation was not run per task policy. No live SEC or provider request was
  made because credentials were not assumed; responsive/manual and real multi-filing
  checks remain pending.

With `uv run profitlab serve` running, open `http://127.0.0.1:8000/`, create a fresh
offline V2 `DEMO` run, and use the **Pipeline** rail to open **Findings** and
**Evaluate**. At both desktop and narrow widths, confirm focus-visible keyboard
navigation, live status, each source drill-down, figures, limitations, and audit
details. Use **Inspect sanitized provider trace** to verify diagnostics load separately
from the primary page. A configured real multi-filing run remains the outstanding live
responsiveness check.

Next: T24.

Task: T22 — Independent fact comparison.
Implemented: the V2 Evaluate stage runs only after findings and Company Facts complete.
It persists an exact-Decimal fiscal-year matrix with explicit match/miss states and
audit metrics, without changing discovery scores, findings, or quotes.

Commands/results:
- Timed predecessor boundary: `time uv run pytest tests/task_gates/test_t21.py
  tests/task_gates/test_t20.py -q`: **4 passed** in 1.18s (1.57s wall time), with
  one existing Starlette/AnyIO deprecation warning. No obsolete tests were removed.
- Added `tests/task_gates/test_t22.py`: a hand-constructed exact-Decimal contract for
  exact, mismatch, unresolved-period, and unsupported states plus a discovery
  immutability assertion; and an offline pipeline/workspace persistence path.
- Final acceptance: `uv run ruff check .`, `git diff --check`, and `time uv run pytest
  tests/task_gates/test_t14.py tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py tests/task_gates/test_t19.py
  tests/task_gates/test_t20.py tests/task_gates/test_t21.py tests/task_gates/test_t22.py -q`:
  **21 passed** in 2.76s (3.12s wall time), with the same warning.
- Browser automation was not run per task policy. No live SEC or LLM request was made
  because credentials were not assumed; real filing/provider and manual UI checks remain pending.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**, enter
`DEMO`, select **Offline fixture**, create a fresh run, and open **Evaluate**. Confirm
each row has an explicit match state, source-linked quotes open canonical lines, and
the expanded metrics report `deterministic_recovery_applied` and
`discovery_output_mutated` as `false`. Then confirm the **Findings** cards are unchanged.

Next: T23.

Task: T21 — Post-discovery SEC Company Facts adapter.
Implemented: the V2 Facts stage now runs only after Findings has completed and sealed.
It retrieves one Company Facts JSON dataset using the existing bounded SEC client,
identity, retry, and cache policy (or a clearly labeled saved synthetic fixture), stores
that raw dataset as one V2 source blob, and normalizes only configured annual facts.
The narrow mapping supports `NetIncomeLoss`, `ProfitLoss`, common-stockholder
basic/diluted income concepts, diluted EPS, and diluted weighted-average shares. Facts
must match the selected accession/form, FY duration, accepted unit, and selected report
period; exact Decimal, unit, interval, accession, form, and filed date are persisted.
Repeated candidates are selected deterministically while alternatives remain visible in
the Facts workspace. The source HTML is never parsed as Inline XBRL, and neither Jev nor
findings payloads gain access to Company Facts.

Commands/results:
- Inspected and timed the direct predecessor boundary: `time uv run pytest
  tests/task_gates/test_t20.py tests/task_gates/test_t19.py -q`: **4 passed** in
  1.25s (1.64s wall time), with one existing Starlette/AnyIO deprecation warning.
  No obsolete tests were removed: both directly cover the active discovery/finding
  boundary.
- Added `tests/task_gates/test_t21.py`: sealing-before-facts, exact Decimal/provenance,
  deterministic duplicate-alternative, non-leakage, and offline workspace coverage.
- Final acceptance: `uv run ruff check .`, `git diff --check`, and `time uv run pytest
  tests/task_gates/test_t21.py tests/task_gates/test_t20.py -q`: **4 passed** in
  1.18s (1.59s wall time), with the same warning.
- Browser automation was not run per task policy. No live SEC request was made because
  SEC contact credentials were not assumed. The remaining gap is a configured live MSFT
  run confirming the annual `NetIncomeLoss` series and manual Facts-stage inspection.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**, enter
`DEMO`, select **Offline fixture**, and click **Create fresh V2 run**. After it advances,
open **Facts**. Confirm that each row shows the metric-to-concept mapping, exact Decimal,
annual period/unit, accession, and filed date; open the duplicate alternatives and the
dataset-provenance details. Then open **Findings** and its request inspection to confirm
Company Facts never appeared there. With a real SEC contact configured, repeat for
`MSFT` and confirm the appropriate annual `NetIncomeLoss` series. This live check remains
pending.

Next: T22.

Task: T20 — Quote-backed findings and visible-number extraction.
Implemented: only T19-retained chunks, filing metadata, and target definitions now
reach the findings LLM. Typed output requires a narrative, exact quote, chunk ID,
observed raw number, optional Decimal proposal, unit/scale, period, attribution, and
limitations. The validator resolves each quote only within its referenced retained
chunk (core before overlap), then persists its exact canonical line/character span and
HTML anchor lineage. A raw number must be inside that exact quote; malformed Decimal
proposals, source references, or citations are rejected. A live run gets at most one
bounded citation-repair request; it never publishes an uncited fallback. Identical
quote/number pairs introduced by overlap collapse to one validated finding. The
Findings workspace renders cards with exact quotes, visible-number highlighting,
unresolved metadata, source jumps, and on-demand sanitized request/validation detail.
Offline fixture findings are explicitly marked as such; no provider inference is
claimed.

Commands/results:
- Inspected and timed the direct predecessor boundary: `time uv run pytest
  tests/task_gates/test_t19.py tests/task_gates/test_t18.py -q`: **4 passed** in
  1.07s (1.43s wall time), with one existing Starlette/AnyIO deprecation warning.
  No obsolete tests were removed: both directly cover active source-range and retained
  evidence behavior.
- Added `tests/task_gates/test_t20.py`: a controlled invalid quote rejection plus a
  source-coordinate/anchor invariant, and an offline pipeline/workspace path covering
  persistence, deduplication, and the visible-only request boundary.
- `uv run ruff check src/profitlab/v2 src/profitlab/web tests/task_gates/test_t20.py`
  passed; `time uv run pytest tests/task_gates/test_t20.py tests/task_gates/test_t19.py -q`:
  **4 passed** in 1.22s (1.60s wall time), with the same warning.
- Final acceptance: `uv run ruff check .`, `git diff --check`, and `time uv run pytest
  tests/task_gates/test_t14.py tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py tests/task_gates/test_t19.py
  tests/task_gates/test_t20.py -q`: **17 passed** in 2.06s (2.37s wall time), with
  the same warning.
- Browser automation was not run per task policy. No live LLM request was made because
  credentials were not assumed; the remaining gap is one real saved SEC filing and
  configured LLM request, including a deliberately invalid-quote repair observation.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**, enter
`DEMO`, select **Offline fixture**, and click **Create fresh V2 run**. Open
**Findings** after the run advances. Confirm every card contains an exact quote and a
source link; follow it and verify the same text is on the canonical source line and
the sanitized filing HTML anchor. Confirm an absent unit/scale, period, or attribution
is shown as unresolved, not guessed. Open **Inspect sanitized findings request and
validation results** and confirm it contains retained visible text and target
definitions only—never `contextRef`, `unitRef`, `us-gaap:`, Company Facts, or evaluation
values. With configured LLM/SEC credentials, repeat for a live filing and submit a
controlled invalid quote to verify its single repair/rejection behavior; this remains
pending.

Next: T21.

Task: T19 — Jev detailed chunk scoring and diverse top-N evidence.
Implemented: every V2 chunk is still reconstructed only from its selected-section
canonical source ranges, then submitted to Jev with exact visible chunk text, visible
heading path, and filing metadata through the existing XBRL/Company-Facts payload
guard. Scores are checkpointed after every bounded batch and separately retained from
the deterministic policy. The policy prioritizes uncovered targets, section and visible
year diversity, score, smaller chunks, and source order; it suppresses heavily
overlapping evidence, retains a bounded uncertain band, and enforces request, input,
elapsed-time, retained-text, and top-N budgets. Cache entries are keyed by sanitized
request hash, prompt version, relevant policy configuration, and model. The Chunk Score
workspace shows score vectors, policy decisions, budget use, source previews, and
on-demand sanitized provider request/response inspection. Offline fixture scoring is
explicitly labeled; no provider inference is claimed.

Commands/results:
- Inspected and timed T17/T18 focused baseline: `time uv run pytest
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py -q`: **5 passed** in
  0.84s (1.20s wall time), with one existing Starlette/AnyIO deprecation warning.
  No obsolete tests were removed: both remain direct active-boundary coverage.
- Added `tests/task_gates/test_t19.py`: one deterministic detailed-policy diversity
  invariant, plus one offline source-through-chunk-score workspace path that verifies
  persisted checkpoints, cache reuse in a second fresh run, and sanitized request
  inspection.
- `time uv run pytest tests/task_gates/test_t19.py tests/task_gates/test_t18.py -q`:
  **4 passed** in 1.05s (1.42s wall time), with the same existing warning.
- Final acceptance: `uv run ruff check .`, `git diff --check`, and `time uv run pytest
  tests/task_gates/test_t14.py tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py tests/task_gates/test_t19.py -q`:
  **15 passed** in 1.79s (2.08s wall time), with the same warning.
- Browser automation was not run per task policy. No live Jev request was made because
  credentials were not assumed; the remaining gap is live detailed-scoring request and
  workspace inspection against a real saved SEC filing.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**, enter
`DEMO`, select **Offline fixture**, and click **Create fresh V2 run**. Open **Chunk
Score** after the run advances. Confirm each chunk row has five target scores, a
selected/uncertain/skipped decision and reason, bounded budget summary, and source
preview link. Open **Inspect sanitized Jev requests and responses** and confirm it has
only exact visible chunk text, visible headings, and filing metadata—never `contextRef`,
`unitRef`, `us-gaap:`, Company Facts, or evaluation values. With configured SEC and Jev
credentials, create a live run and inspect a retained, uncertain, overlap-suppressed,
and skipped chunk; this live verification remains pending.

Next: T20.

Task: T18 — Source-range chunking with bounded overlap.
Implemented: selected (not uncertain or skipped) outline sections now split into
stable `TextChunk` records that store only a core `SourceRange`, separate preceding
context ranges, an estimated request size, and adjacent chunk IDs. Canonical
paragraph, list, heading, caption, and table-row lines remain atomic, so a table row
is never split. Core ranges provide exactly-once primary coverage; overlap is bounded
context within the same outline section and is not a second evidence owner. The
chunker rejects a single line that cannot fit the configured request budget instead
of truncating it. SQLite persists chunk metadata and normalized range rows, never a
duplicated authoritative text body. The Chunk workspace lists lineage, core/context
ranges, estimates, and source links; the lazy inspector reconstructs previews only
through `CanonicalDocument.slice` and shows neighboring chunks.

Commands/results:
- Inspected and timed the active T17 section-scoring and earlier chunk baseline:
  `time uv run pytest tests/task_gates/test_t17.py tests/task_gates/test_t06.py -q`:
  **5 passed** in 16.62s (17.00s wall time), with one existing Starlette/AnyIO
  deprecation warning. No obsolete tests were removed: T06 is legacy coverage and
  T17 remains the direct selected-section dependency.
- Added `tests/task_gates/test_t18.py`: one core-coverage/overlap/budget invariant
  including an indivisible oversized-line rejection, plus one offline source through
  chunk-stage workspace and lazy-inspector path.
- `uv run pytest tests/task_gates/test_t15.py tests/task_gates/test_t16.py
  tests/task_gates/test_t17.py tests/task_gates/test_t18.py -q`: **10 passed** in
  1.07s; `uv run ruff check .` and `git diff --check` passed.
- Final acceptance: `time uv run pytest tests/task_gates/test_t14.py
  tests/task_gates/test_t15.py tests/task_gates/test_t16.py tests/task_gates/test_t17.py
  tests/task_gates/test_t18.py -q`: **13 passed** in 2.45s (2.79s wall time), with
  the same existing warning. Final `uv run ruff check .` and `git diff --check` passed.
- Browser automation was not run per task policy. No live SEC or Jev request was
  made because configured credentials/contact were not assumed; the precise remaining
  gap is visual and live inspection of chunks from a real saved filing.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**, enter
`DEMO`, select **Offline fixture**, and click **Create fresh V2 run**. Open **Chunk**.
Confirm every row names a selected outline section, has a core source-range link,
and shows context separately where present. Open **Preview and lineage** for a
non-first chunk: its core and context links must open the correct canonical lines,
and the preview must match those lines exactly. With configured SEC and Jev access,
create a live run, open a large selected section, and confirm that table rows remain
whole and that adjacent overlap is bounded; this live verification remains pending.

Next: T19.

Task: T17 — Jev title/topic scoring and section discovery.
Implemented: validated outline sections now produce a strict `JevVisibleContext` that
contains only section ID, generated topic, exact visible heading, line size, a 600-character
exact preview, and filing metadata. A recursive payload guard rejects XBRL namespaces,
Company Facts/structured-fact data, evaluation fields, and similar forbidden material before
the typed Jev request is sent. Sections and all five versioned target questions are batched
within configurable descriptor count and request-size bounds. Scores are persisted separately
from the deterministic policy: it greedily retains high-score sections that cover previously
uncovered targets, then applies score, smaller-section, and source-order ties, and retains a
bounded uncertain band. The Section Score workspace shows each score vector, selected/
uncertain/skipped decision and reason, exact source-range link, and redacted persisted request/
response inspection. The offline path is explicitly fixture Jev scoring; it does not claim live
inference. The next chunk stage remains visibly unimplemented.

Commands/results:
- Inspected and timed the active T16 outline and T07 provider tests before implementation:
  `time uv run pytest tests/task_gates/test_t16.py tests/task_gates/test_t07.py -q`:
  **11 passed** in 9.57s (10.11s wall time).
- Added `tests/task_gates/test_t17.py`: one visible-context/payload-guard and deterministic
  policy contract, plus one source-to-outline-to-offline-section-score workspace path. No tests
  were removed: the inspected T16 and T07 tests still cover active source and typed-provider
  contracts.
- `time uv run pytest tests/task_gates/test_t07.py tests/task_gates/test_t14.py
  tests/task_gates/test_t15.py tests/task_gates/test_t16.py tests/task_gates/test_t17.py -q`:
  **18 passed** in 11.07s (11.56s wall time), with one existing Starlette/AnyIO deprecation
  warning. `uv run ruff check .` and `git diff --check` passed.
- After adding persisted per-batch progress events, `uv run pytest tests/task_gates/test_t17.py
  tests/task_gates/test_t16.py -q` passed: **5 passed** in 1.93s; final `uv run ruff check .`
  and `git diff --check` passed.
- Follow-up live-run regression: a legitimate filing use of “evaluation” previously triggered
  the broad text guard. The guard now rejects XBRL markers in any source string but rejects
  Company Facts/evaluation material only as payload field names. `uv run pytest
  tests/task_gates/test_t17.py tests/task_gates/test_t16.py -q`: **5 passed** in 0.93s;
  `uv run ruff check .` and `git diff --check` passed.
- Follow-up live-run regression: a real filing can make the configured eight-section batch
  exceed its visible-context budget. Batch packing now splits it into the largest compliant
  sub-batches, failing only when one already-bounded descriptor cannot fit. `uv run pytest
  tests/task_gates/test_t17.py tests/task_gates/test_t16.py -q`: **6 passed** in 1.97s;
  final `uv run ruff check .` and `git diff --check` passed.
- Browser automation was not run per task policy. No live SEC or Jev request was made because
  configured credentials/contact were not assumed; the precise remaining gap is a live scoring
  request inspection against a real saved SEC filing.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**, enter `DEMO`,
select **Offline fixture**, and click **Create fresh V2 run**. Open **Section Score** after the
run advances. Confirm every row has five target scores, a policy decision and reason, and a
source-range link. Open **Inspect sanitized Jev requests and responses** and verify the stored
request contains only visible descriptor fields; it must contain no `contextRef`, `unitRef`,
`us-gaap:`, Company Facts, or evaluation values. With configured SEC and Jev credentials,
create a live run and inspect a selected and skipped row; live verification remains pending.

Next: T18.

Task: T16 — Cheap LLM outline with source-coverage validation.
Implemented: bounded, overlapping canonical-line windows now feed a configurable,
separate cheap outline model in live mode. The default 900-line windows with a
60-line overlap reduce a 2,000-line filing to three calls. The strict response
accepts only generated topic, exact source title, range, optional exact quote,
section type, parent hint, and an explicit continuation marker. It requests exactly
two navigation levels: generated parent topic and generated child topic. Every later
window receives the preceding validated navigation context, so the model can mark a
continued section and merge it rather than make a duplicate at the window boundary.
Ranges must stay within the supplied window, while titles and quotes must occur
exactly in the referenced canonical lines. Invalid proposals are rejected and their
diagnostics remain visible as boundary warnings. Valid model boundaries, rather than
every HTML heading, form a contiguous primary partition: every nonblank canonical
line has one owner, with no duplicate ownership. Generated topics are visually
distinct from exact filing-derived titles and quotes.

The offline path deliberately uses the saved fixture outline generator rather than
claiming a live LLM call. Source-window batches cache in V2 SQLite by source-range
hash, prompt version, configuration hash, and model identity; stage summaries state
when cached batches were reused. The source and outline stages are complete in new
V2 runs; later stages remain explicitly unimplemented.

Commands/results:
- Inspected and timed the T15 source and T07 provider baseline before implementation:
  `time uv run pytest tests/task_gates/test_t15.py tests/task_gates/test_t07.py -q`:
  **10 passed** in 10.22s (10.81s wall time).
- Added `tests/task_gates/test_t16.py`: malformed-boundary/quote and full-coverage
  invariants, a multi-window continuity-context test, plus an offline
  source-to-outline-to-workspace path. It also proves cache reuse in a fresh run
  with the same saved source.
- `time uv run pytest tests/task_gates/test_t14.py tests/task_gates/test_t15.py
  tests/task_gates/test_t16.py -q`: **7 passed** in 1.07s (1.38s wall time), with
  one existing Starlette/AnyIO deprecation warning.
- Follow-up hierarchy check: `time uv run pytest tests/task_gates/test_t14.py
  tests/task_gates/test_t15.py tests/task_gates/test_t16.py tests/task_gates/test_t07.py -q`:
  **16 passed** in 11.15s (11.67s wall time), with one existing Starlette/AnyIO
  deprecation warning. `uv run ruff check .` and `git diff --check` passed.
  No obsolete tests were
  removed: the inspected focused V2 source/provider tests still cover their active
  contracts. The offline integration test is the task's offline run; no V2 CLI
  stage command is required.
- Browser automation was not run per task policy. No live SEC or LLM request was
  made because valid configured SEC contact and LLM credentials were not assumed.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**,
enter `DEMO`, select **Offline fixture**, and click **Create fresh V2 run**. Open
its **Outline** stage. Confirm generated parent topics group generated child topics,
each child line-range link opens the matching source page, and any boundary warning
is visible instead of a fabricated title. Create a second offline run with the same
fixture and confirm the outline summary says cached window batches were reused. With
configured SEC contact and LLM credentials, create a live run and repeat several
source jumps; live model output remains pending verification.

Next: T17.

Task: T15 — Canonical visible source and exact anchors.
Implemented: a V2-only source service that uses the saved 2025 fixture offline and
the existing bounded SEC discovery/download policy for live primary filing HTML.
It stores raw HTML separately from anchor-bearing sanitized HTML and canonical
line JSON. Canonical lines are contiguous, nonblank normalized visible text with
their element type, stable DOM-derived anchor, and raw-source hash. Inline XBRL
display elements are unwrapped; hidden facts, XBRL-only attributes and metadata
are removed before downstream persistence. `CanonicalDocument.slice(SourceRange)`
validates document/hash ownership and reconstructs only tracked lines. The V2
source view pages 100 lines at a time and each line links directly to its sanitized
HTML anchor. The home page now offers offline fixture or configured live-SEC V2
source runs; V1 storage is never read or created by this path.

Commands/results:
- Inspected the existing T05 source/download and T14 V2 shell coverage before
  implementation. Added one focused canonical invariant test and one offline
  source/viewer integration test in `tests/task_gates/test_t15.py`.
- `time uv run pytest tests/task_gates/test_t05.py tests/task_gates/test_t14.py tests/task_gates/test_t15.py -q`:
  **12 passed** in 1.52s (1.89s wall time); one existing Starlette/AnyIO
  deprecation warning.
- `uv run ruff check .` and `git diff --check`: passed.
- The V2 UI creates and starts a fresh offline source run directly; no V2
  `demo --through` command is required or supported.
- Browser automation was not run per task policy. No live SEC request was made:
  a valid `SEC_USER_AGENT` was not assumed, so the saved fixture is not presented
  as real filing validation.

With the server running, open `http://127.0.0.1:8000/`. In **V2 workspace**,
enter `DEMO`, select **Offline fixture**, and click **Create fresh V2 run**. Open
its **Source** stage, click the canonical document, and click several line
numbers. Each should open the matching sanitized HTML anchor; inspect a table row
and confirm it is one normalized line. For a configured SEC contact, select
**Live SEC filing**, create an MSFT run, and repeat the checks against the saved
primary 10-K; confirm the displayed source contains no hidden facts, `contextRef`,
`unitRef`, `scale`, or `us-gaap:` metadata.

Next: T16.

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
