# Active implementation tasks

Execute one task per session, in order. Completed implementation history is recorded in [PROGRESS.md](PROGRESS.md). The active architecture starts at T14, is specified in [V2_IMPLEMENTATION_PLAN.md](V2_IMPLEMENTATION_PLAN.md), and intentionally does not migrate or read previous run data.

Commands and checks below are acceptance contracts to implement, not claims that they already exist.

## Execution policy for every task

1. Read repository instructions, `PROGRESS.md`, the relevant specification sections, and the selected task. Resume an `IN_PROGRESS` task before starting a later task.
2. Mark the task `IN_PROGRESS` and state the concrete result the user will be able to inspect.
3. Reuse working SEC, provider, settings, redaction, Decimal, validation, FastAPI/Jinja, and cancellation code when it fits the active boundary. Prefer strong small abstractions over new code or compatibility wrappers.
4. Implement only the selected bounded task and necessary fixes. Keep service logic out of CLI/web handlers. Do not implement future stages or fabricate external results.
5. At the start, inspect and time tests covering the changed area. Delete or consolidate obsolete, redundant, mock-heavy, slow, or implementation-detail tests. Remove tests for code deleted by the task.
6. Prefer one focused contract/invariant test plus one integration path over many mocked tests. Prioritize saved real SEC documents, recorded real provider responses with provenance, and an explicit live smoke check when configured. Use synthetic fixtures only for controlled failures that are unsafe or impractical with real data.
7. Run the task gate and directly affected tests, record elapsed time, and run `uv run ruff check .`. Run the full suite only for shared storage/provider/orchestration changes, cleanup, and final gates. If the suite is slow because coverage is obsolete, remove that coverage rather than accepting permanent slowdown.
8. Do not run browser or UI automation. It is unreliable in this environment. End every task with manual verification instructions centered on the already-running UI: URL/click path, observations, and expected result. Do not require a `demo --through` or CLI stage command to exercise the delivered V2 behavior. Mention `uv run profitlab serve` only as the one-time local server prerequisite when needed.
9. Attempt live checks only with configured credentials. If unavailable, use saved real data, state the precise remaining gap, and never present replay/demo results as live validation.
10. Update `PROGRESS.md` with actual results, commands, real-data provenance, tests inspected/removed/consolidated, focused test duration, live status, limitations, manual verification steps, and next task.
11. End with a concise handoff. Do not automatically start the next task.

If a task is too large for one session, finish a coherent working slice, keep it `IN_PROGRESS`, and record the exact remaining work. Do not mark partial work `DONE` to preserve the schedule.

## Task summary

| Task | Visible result | Dependency |
| --- | --- | --- |
| T14 | Fresh run with an eight-stage live pipeline shell | Completed implementation history |
| T15 | Canonical line-numbered filing with exact HTML anchors | T14 |
| T16 | LLM-produced, source-validated filing outline | T15 |
| T17 | Jev-ranked outline sections with no XBRL input | T16 |
| T18 | Bounded overlapping chunks with exact source ranges | T17 |
| T19 | Jev-ranked chunks and diverse retained evidence | T18 |
| T20 | Quote-backed findings verified against source | T19 |
| T21 | SEC Company Facts loaded only after discovery | T20 |
| T22 | Visual comparison of findings and structured facts | T21 |
| T23 | Consolidated modern pipeline and report UI | T22 |
| T24 | Faster cached/resumable workflow with measured gains | T23 |
| T25 | Obsolete execution paths and tests removed | T24 |
| T26 | Jev retrieval benchmark against simple baselines | T25 |
| T27 | Complete measured real-data demonstration | T26 |

## T14 — V2 contracts, storage, and live pipeline shell

**Goal:** establish the replacement run model and a functional browser workspace before rebuilding domain stages.

**Read:** [V2_IMPLEMENTATION_PLAN.md](V2_IMPLEMENTATION_PLAN.md) sections 1–3 and 11–14. Dependency: completed implementation history only.

**Implement:**

1. Define the eight ordered stages: `source`, `outline`, `section_score`, `chunk`, `chunk_score`, `findings`, `facts`, `evaluate`.
2. Add the minimal shared contracts: `StageSnapshot`, `CanonicalDocumentRef`, `SourceRange`, `OutlineSection`, `TextChunk`, `ScoredItem`, `Finding`, `StructuredFact`, and `FactComparison`. Do not add a generic workflow/plugin framework.
3. Create a fresh V2 SQLite schema for runs, stages, high-level events, and later stage-owned rows. Use a new schema/data namespace; do not migrate or load V1 runs.
4. Reuse the current FastAPI/Jinja, settings, redaction, and cancellation concepts. Add a V2 run workspace with an eight-stage navigation rail and one selected-stage detail region.
5. Persist progress before publishing a high-level event. Add an SSE endpoint with a bounded polling fallback.
6. Implement a controlled offline run that advances through the empty shell and clearly marks unimplemented stages rather than fabricating output.

**Manual verification handoff:** create a fresh V2 run, open its workspace, select every stage, refresh, and confirm status and selected-stage navigation survive. No V1 artifact list appears.

**Acceptance gate:** fresh V2 runs persist and stream stage events; earlier runs are ignored; cancellation state is durable; no page renders raw artifact inventories; existing provider and SEC adapters remain importable for later reuse.

**Next: T15.**

## T15 — Canonical visible source and exact HTML anchors

**Goal:** provide one trustworthy line-addressable source representation used by every later stage.

**Read:** V2 plan section 4. Dependency: T14.

**Implement:**

1. Reuse SEC ticker, filing-discovery, download, retry, and access-policy code where it matches the new service boundary.
2. Treat the primary filing as visible HTML, not as an Inline XBRL data source. Remove hidden Inline XBRL content and unwrap visible Inline XBRL elements to ordinary text.
3. Strip taxonomy concepts, contexts, units, scales, formats, namespace attributes, and other XBRL-only metadata before downstream persistence.
4. Build `CanonicalDocument`: ordered nonblank content lines with line number, normalized visible text, element type, stable HTML anchor/DOM reference, and source hash.
5. Build `CanonicalDocument.slice(SourceRange)` and source-range-to-anchor resolution. All later text must be derived through this API.
6. Add a paginated line-numbered source viewer with heading/table-row markers and direct anchor links.

**Manual verification handoff:** inspect a real saved filing, jump from several numbered lines to the corresponding HTML elements, and search for a visible financial row. Confirm hidden XBRL content is absent.

**Acceptance gate:** canonical lines reproduce the visible source under the documented whitespace normalization; every line maps to an HTML anchor; source hashes detect mutation; scans find no `us-gaap:`, `contextRef`, `unitRef`, hidden facts, or XBRL scale metadata in downstream canonical data.

**Next: T16.**

## T16 — Cheap LLM outline with source-coverage validation

**Goal:** turn a long filing into a navigable topic outline without treating generated summaries as source text.

**Read:** V2 plan section 5. Dependency: T15.

**Implement:**

1. Send bounded windows of numbered canonical lines to a configurable low-cost LLM with modest boundary overlap.
2. Request only generated topic, exact source title when present, start/end line, optional exact representative quote, section type, and parent-topic hint.
3. Validate every proposed range against the supplied window and every exact title/quote against the referenced canonical lines.
4. Reconcile overlapping window proposals deterministically, preferring explicit source headings. Produce ordered primary ranges with no nonblank-line gaps or duplicate ownership.
5. Clearly separate generated topic metadata from exact source title/quotes in contracts and UI.
6. Cache outline batches by source-range hash, prompt version, and actual model. Record rejected or uncertain boundaries without inventing replacements.
7. Add an outline stage UI showing topic, exact title, line range, boundary warnings, and source jump.

**Manual verification handoff:** navigate a real filing through its generated outline and open several sections at their exact source ranges. Generated topics and source-derived labels are visually distinct.

**Acceptance gate:** every nonblank canonical line belongs to exactly one primary outline section; invalid ranges and non-matching quotes are rejected; cached and live batches are distinguishable; no generated prose enters canonical source content.

**Next: T17.**

## T17 — Jev title/topic scoring and section discovery

**Goal:** demonstrate Jev selecting promising filing sections from the navigation outline without access to structured facts.

**Read:** V2 plan sections 6 and 9. Dependency: T16.

**Implement:**

1. Define an allowlisted `JevVisibleContext` containing section ID, generated topic, exact visible heading, size, short exact preview, filing metadata, and no other fields.
2. Version the initial target questions: annual shareholder profit/net income, diluted EPS, diluted shares, explanation of earnings change, and restatement/comparability information.
3. Reuse the typed Jev adapter, tracing, retry owner, timeout, usage, and redaction code. Batch section descriptors/questions within the verified provider request budget.
4. Store the Jev score vector independently from application policy. Select high-score and bounded uncertain sections using deterministic ties: uncovered target, score, smaller section, then source order.
5. Add payload guards and canary tests that reject XBRL namespaces, concept IDs, structured-fact fields, or later evaluation values.
6. Add a live ranked-section UI with target scores, selected/uncertain/skipped state, policy reason, source range, and on-demand request inspection.

**Manual verification handoff:** watch section batches complete and inspect why selected and skipped sections differ. The page explicitly states that only sanitized visible filing content was supplied to Jev.

**Acceptance gate:** gold/Company Facts data cannot enter the scoring service by contract or payload; Jev score and policy decision remain separate; request/usage counts are accurate; a controlled score fixture reproduces the same selected order.

**Next: T18.**

## T18 — Source-range chunking with bounded overlap

**Goal:** split only selected sections into model-safe chunks while keeping exact lineage back to HTML.

**Read:** V2 plan section 7. Dependency: T17.

**Implement:**

1. Reuse useful size-estimation and table-boundary logic from the existing implementation, but replace flat filing-wide `Chunk` artifacts with `TextChunk` source ranges.
2. Keep small selected sections intact. Split large sections at canonical paragraph, list, heading, or table-row boundaries.
3. Never split a table row, mix filings, or combine unrelated outline sections.
4. Store a primary/core range and separate context/overlap ranges. Reconstruct chunk text only through `CanonicalDocument.slice`.
5. Deduplicate coverage by primary lines; overlap is context and never independent evidence.
6. Add a lazy chunk inspector showing section lineage, core/overlap lines, size estimate, adjacent chunks, preview, and source link.

**Manual verification handoff:** open a large selected section, inspect its chunk boundaries and overlaps, and follow core and context ranges back to the correct filing HTML.

**Acceptance gate:** every chunk exactly reconstructs from its source ranges and matching source hash; request-size limits are enforced; no line is silently truncated; primary coverage and overlap coverage are separately measurable.

**Next: T19.**

## T19 — Jev detailed chunk scoring and diverse top-N evidence

**Goal:** use Jev a second time to discard weak detail and retain a small, diverse evidence set.

**Read:** V2 plan section 7. Dependency: T18.

**Implement:**

1. Reuse `ScoredItem` and the same target-question vocabulary for detailed chunk scoring.
2. Supply exact chunk text, visible heading path, and filing metadata; retain the same XBRL non-leak boundary.
3. Score only chunks belonging to selected outline sections.
4. Deduplicate heavily overlapping chunks before top-N selection. Preserve diversity across filing, outline section, target, and visible fiscal-year labels when available from source text.
5. Enforce request, token, retained-text, and elapsed-time budgets. Checkpoint after every batch for cancellation/resume.
6. Add a ranked chunk UI with scores, selection reason, overlap relationship, budget use, source preview, and live progress.

**Manual verification handoff:** inspect a high-score retained chunk, an uncertain chunk, a duplicate suppressed by overlap policy, and a low-score skipped chunk.

**Acceptance gate:** only selected-section chunks incur calls; deterministic selection does not collapse onto near-duplicates; cached scores are reused only for matching source/prompt/model hashes; budget exhaustion yields an explicit partial stage.

**Next: T20.**

## T20 — Quote-backed findings and visible-number extraction

**Goal:** turn top evidence chunks into useful findings while guaranteeing that every published claim contains an exact source quote.

**Read:** V2 plan section 8. Dependency: T19.

**Implement:**

1. Supply only retained chunks, filing metadata, and the target definition to the LLM; never supply expected XBRL values.
2. Require typed findings containing concise narrative, exact quotes, source chunk/range, observed raw numbers, proposed Decimal normalization, visible scale/unit, period, attribution, and limitations.
3. Validate every quote as an exact substring inside the referenced chunk, then resolve it to line/character coordinates and an HTML anchor inside that source range.
4. Allow one bounded quote-repair attempt. Reject a finding if its quote remains invalid; never publish an uncited fallback.
5. Treat unclear period, scale, or attribution as unresolved instead of guessing. Deduplicate the same quoted number across overlapping chunks.
6. Add finding cards with narrative, exact quote, highlighted numbers, source jump, validation state, and model details on demand.

**Manual verification handoff:** open each published finding and confirm its quote highlights the same canonical text and HTML source. Inspect a controlled invalid-quote rejection.

**Acceptance gate:** every published finding has at least one exact validated quote; normalized numbers retain raw text and source range; invalid citations cannot enter later comparison/report stages; no XBRL data appears in LLM requests.

**Next: T21.**

## T21 — Post-discovery SEC Company Facts adapter

**Goal:** load independent structured facts only after Jev discovery and findings are sealed.

**Read:** V2 plan section 9. Dependency: T20.

**Implement:**

1. Reuse the bounded SEC transport, identity, retry, and cache policy to retrieve Company Facts once per company.
2. Do not parse Inline XBRL documents. Persist the raw dataset as one source blob plus normalized supported facts.
3. Add a narrow target configuration connecting the user-facing metric and Jev questions to accepted concepts, units, annual-period rules, and attribution labels.
4. Initially support `NetIncomeLoss`, `ProfitLoss`, common-stockholder basic/diluted income concepts, diluted EPS, and diluted weighted-average shares.
5. Filter by selected accession/form, annual duration, accepted unit, and requested fiscal periods. Resolve repeated comparative facts deterministically and retain alternatives for inspection.
6. Enforce ordering: findings are sealed before facts retrieval begins. Add a structured-facts stage UI that shows dataset provenance and concept mapping.

**Manual verification handoff:** complete discovery, then watch the Facts stage load. Confirm MSFT exposes the appropriate annual `NetIncomeLoss` series and that earlier Jev payloads remain unchanged.

**Acceptance gate:** Company Facts is unavailable to section/chunk scoring and findings services; normalized facts preserve exact Decimal, period, unit, concept, accession, and filed date; duplicate selection is deterministic; failures do not rewrite discovery output.

**Next: T22.**

## T22 — Independent fact comparison and measured discovery coverage

**Goal:** objectively compare quote-backed numbers with structured facts without allowing the oracle to repair discovery.

**Read:** V2 plan section 10. Dependency: T21.

**Implement:**

1. Match findings to structured facts by configured metric, normalized value, scale/unit, annual period, and selected filing scope.
2. Produce explicit states: exact match; value match/period unresolved; period match/value mismatch; structured fact missed; additional visible value; unsupported; ambiguous duplicate.
3. Deduplicate overlapping quote findings and repeated structured comparative facts before calculating denominators.
4. Measure expected facts, exact matches, misses, additional visible numbers, value/period accuracy, requests and source lines before first match, retained document percentage, latency, and provider usage.
5. Preserve Jev-only results separately from any deterministic recovery policy. Evaluation must never mutate scores, findings, or the report source set.
6. Add a fiscal-year comparison matrix linking each expected fact, discovered number, match state, quote, and source.

**Manual verification handoff:** inspect an exact match, a controlled miss, a scale/period ambiguity, and an additional visible number. Each state links to its independent inputs.

**Acceptance gate:** hand-constructed comparisons and denominators match expectations; evaluation runs strictly after discovery; a missed fact remains missed; exact equality uses normalized Decimal values rather than float tolerance.

**Next: T23.**

## T23 — Consolidated modern pipeline and report UI

**Goal:** make the complete system understandable from one responsive workspace without technical overload.

**Read:** V2 plan section 11. Dependency: T22.

**Implement:**

1. Consolidate primary navigation to Runs, Pipeline, Report, and Evaluation. Move raw provider payloads and storage diagnostics behind stage details.
2. Standardize every stage detail around purpose, progress, inputs, output summary, inspectable items, warnings, and on-demand trace.
3. Show live high-level activity rather than raw HTTP events. Coalesce updates and pause/reduce polling when the page is hidden.
4. Complete the source, outline, section score, chunk, chunk score, findings, facts, and comparison views using pagination/lazy loading.
5. Build a reader report with friendly currency/share/EPS formatting, quote-backed findings, coverage, and limitations. Keep raw Decimal values and IDs under audit details.
6. Enforce page limits: no initial view renders more than 100 repeated records or loads complete filing/provider payloads.

**Manual verification handoff:** follow one run from stage rail to report and evaluation at desktop and narrow widths. Verify keyboard access, visible focus, live status, and source drill-down.

**Acceptance gate:** a nontechnical user can understand the outcome; a technical user can inspect each decision; no unbounded artifact/chunk/trace page remains; default pages are responsive under a real multi-filing run.

**Next: T24.**

## T24 — Provider, persistence, and resume optimization

**Goal:** reduce live latency and storage cost without changing exploration semantics.

**Read:** V2 plan section 12. Dependency: T23.

**Implement:**

1. Reuse one HTTP client/connection pool per provider run and add provider-aware bounded concurrency for independent scoring batches.
2. Cache outline and score results by sanitized source/range hash, prompt/question version, pinned actual model identity, and relevant configuration.
3. Batch related SQLite writes; index run/stage/item/sequence lookup paths; store ranges rather than duplicated chunk text.
4. Keep one raw and one canonical blob per filing; compress large diagnostic payloads. Do not return to file-per-cell or file-per-attempt storage.
5. Restore priority queue, counters, and next work item after cancellation/restart without duplicating paid requests.
6. Record before/after request counts, wall time, database size, route latency, and UI payload size on the same fixture/live replay.

**Manual verification handoff:** resume an interrupted exploration, observe cache reuse labels, and confirm the same selected sections/chunks/findings and comparison results.

**Acceptance gate:** optimization preserves deterministic policy outcomes; live and cached results are distinct; no duplicate provider calls occur after a clean checkpoint; performance measurements are reported rather than inferred.

**Next: T25.**

## T25 — Remove superseded execution paths

**Goal:** finish the refactor by deleting code that only supports the obsolete flat pipeline.

**Read:** V2 plan section 13. Dependency: T24.

**Implement:**

1. Remove V1 flat screening, extraction fallback, reconciliation, calculation/report contracts, obsolete routes/templates, and compatibility tests once no V2 imports depend on them.
2. Remove file-per-cell/intermediate-attempt persistence and the global artifact inventory UI.
3. Keep only reused SEC, provider, settings, redaction, source, validation, and orchestration utilities that have clear V2 owners.
4. Simplify CLI/help/README around the V2 workflow. State that previous run data is unsupported and requires a fresh run.
5. Remove dead dependencies and settings after confirming no supported path uses them.

**Manual verification handoff:** start from a fresh data directory, run the implemented V2 demo, and click every primary route. No V1 tab, command, template, or status wording remains.

**Acceptance gate:** static/import search finds no obsolete execution path; full V2 tests pass; application starts cleanly; deletion reduces code without replacing it with compatibility adapters.

**Next: T26.**

## T26 — Retrieval benchmark and baselines

**Goal:** measure whether Jev improves discovery efficiency while preserving required visible evidence.

**Read:** V2 plan sections 14–15. Dependency: T25.

**Implement:**

1. Create immutable development and held-out datasets split by company/accession, with reviewed source ranges for relevant facts, misleading quarterly/segment/non-GAAP values, explanations, comparability passages, and irrelevant sections.
2. Add baselines: keep all, heading/keyword rules, structural rules, Jev section scoring, and Jev section-plus-chunk scoring.
3. Pin model/question/prompt versions. Never tune thresholds on held-out companies.
4. Measure relevant-range recall, structured-fact coverage, exact value accuracy, recall at retained-source budget, source percentage explored, calls, usage, latency, and time to first matching fact.
5. Report Jev-only, application-policy, and optional recovery results separately. Never treat an XBRL-unlabeled passage automatically as irrelevant.
6. Add an evaluation view with configuration comparison and clickable missed source ranges.

**Manual verification handoff:** compare at least two strategies, open one miss and one false-positive candidate, and confirm live/fake/replayed provider identity and sample counts are visible.

**Acceptance gate:** gold ranges and structured facts never enter Jev requests; overlap is deduplicated; denominators are explained; initial held-out targets remain at least 95% relevant-range recall, 100% required-fact coverage, and no wrong selected metric/year values, or the UI clearly reports that the targets were not met.

**Next: T27.**

## T27 — Final real-data, real-time demonstration

**Goal:** prove the streamlined V2 pipeline works end to end on varied real filings and remains inspectable when imperfect.

**Read:** all V2 plan sections. Dependency: T26.

**Implement:**

1. Run at least three real companies with materially different filing structures and one to four requested annual filings.
2. Verify source sanitization, outline navigation, section/chunk scores, quote-backed findings, post-discovery facts, and fact comparison for each run.
3. Exercise cancellation, resume, provider overload, malformed outline/finding output, missing structured fact, and quote-validation failure.
4. Record source percentage explored, exact fact coverage, Jev/LLM calls and usage, time to first finding, total runtime, database size, and UI payload/route timings.
5. Complete concise setup and two-minute verification documentation. Do not claim population accuracy from the small sample.

**Manual verification handoff:** start a live ticker from the home page and watch every stage update. Inspect one selected section, one retained chunk, one exact quote, one fact match, one miss/limitation if present, and the final report.

**Acceptance gate:** real calls and data are clearly identified; Jev receives only sanitized visible source content; every published claim has an exact quote; structured facts load only after discovery; refresh/resume works; misses remain visible; the configured demo budget completes a representative run or reports the precise exhausted limit.

**Final handoff:** provide the startup command, one representative run URL, measured results for each real company, remaining unsupported cases, and the shortest path for verifying that XBRL data did not enter Jev requests.
