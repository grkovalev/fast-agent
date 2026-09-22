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
| T27 | Outline-aware findings inputs | T25 |
| T28 | Jev retrieval benchmark against simple baselines | T27 |
| T29 | Complete measured real-data demonstration | T28 |
| T30 | Fresh-only storage schema with migration history removed | T29 |
| T31 | Live-SEC-only source workflow with offline fixture mode removed | T30 |
| T32 | Evidence-backed evaluation redesign decision | T31 |

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

**Next: T27.**

## T27 — Outline-aware findings inputs

**Goal:** give the findings model the existing validated filing outline as
navigational context alongside retained evidence, in its single bounded request.

**Read:** V2 plan sections 5, 7, 8, and 15. Dependency: T25.

**Implement:**

1. Load the persisted validated outline and render it once in the findings request,
   together with the retained chunks. Each entry retains its section ID, canonical
   line range, exact visible title or representative quote when available, and a
   clearly labeled generated topic. Link each retained chunk to its outline
   section.
2. Supply the filing's current fiscal-reporting year as explicit request metadata
   and instruct the findings model to look for values for that year. Derive it from
   trusted filing metadata, label it as the requested year rather than source
   evidence. The exact number quote does not have to repeat a period, unit, or
   scale header when that visible context appears elsewhere in the retained chunk.
3. Treat the outline as navigation metadata, not supporting evidence. Do not look
   for, infer, store, or resolve evidence-context bindings; do not add an outline
   LLM call or modify the outline response contract.
4. Keep the combined request bounded and structured: the full outline is sent once,
   while each evidence item remains the exact visible text of its retained chunk.
   Preserve source-range identities and enforce the configured request budget.
5. Keep exact-quote validation unchanged. The outline may help the model orient
   itself, but it cannot justify a guessed period, unit, scale, or attribution;
   use separately retained visible context when available, and leave missing or
   conflicting support unresolved.
6. Version the findings prompt/configuration cache key and report outline-context
   size separately from retained-evidence size. Add a focused request-shape test
   proving the outline and requested current fiscal year are supplied once and no
   additional outline request occurs.

**Manual verification handoff:** open a run's Findings stage and its sanitized
provider trace. Confirm the request contains the complete labeled outline once,
the current fiscal-reporting year, each retained chunk links to an outline section,
and every published finding still jumps to an exact visible quote. Confirm
ambiguous period, unit, scale, or attribution remains unresolved.

**Acceptance gate:** the findings request contains the persisted validated outline
exactly once and only retained chunk text as evidence; it creates no extra outline
request or persisted binding; no Company Facts or evaluation value enters the
request; it states the requested current fiscal-reporting year; valid findings
retain exact quotes; the exact quote need not repeat period/unit/scale context from
another retained visible line; missing source support cannot silently produce a
year, unit, scale, or attribution claim.

**Next: T28.**

## T28 — Retrieval benchmark and baselines

**Goal:** measure whether Jev improves discovery efficiency while preserving required visible evidence.

**Read:** V2 plan sections 14–16. Dependency: T27.

**Implement:**

1. Create immutable development and held-out datasets split by company/accession, with reviewed source ranges for relevant facts, misleading quarterly/segment/non-GAAP values, explanations, comparability passages, and irrelevant sections.
2. Add baselines: keep all, heading/keyword rules, structural rules, Jev section scoring, and Jev section-plus-chunk scoring.
3. Pin model/question/prompt versions. Never tune thresholds on held-out companies.
4. Measure relevant-range recall, structured-fact coverage, exact value accuracy, recall at retained-source budget, source percentage explored, calls, usage, latency, and time to first matching fact.
5. Report Jev-only, application-policy, and optional recovery results separately. Never treat an XBRL-unlabeled passage automatically as irrelevant.
6. Add an evaluation view with configuration comparison and clickable missed source ranges.

**Manual verification handoff:** compare at least two strategies, open one miss and one false-positive candidate, and confirm live/fake/replayed provider identity and sample counts are visible.

**Acceptance gate:** gold ranges and structured facts never enter Jev requests; overlap is deduplicated; denominators are explained; initial held-out targets remain at least 95% relevant-range recall, 100% required-fact coverage, and no wrong selected metric/year values, or the UI clearly reports that the targets were not met.

**Next: T29.**

## T29 — Final real-data, real-time demonstration

**Goal:** prove the streamlined V2 pipeline works end to end on varied real filings and remains inspectable when imperfect.

**Read:** all V2 plan sections. Dependency: T28.

**Implement:**

1. Run at least three real companies with materially different filing structures and one to four requested annual filings.
2. Verify source sanitization, outline navigation, section/chunk scores, quote-backed findings, post-discovery facts, and fact comparison for each run.
3. Exercise cancellation, resume, provider overload, malformed outline/finding output, missing structured fact, and quote-validation failure.
4. Record source percentage explored, exact fact coverage, Jev/LLM calls and usage, time to first finding, total runtime, database size, and UI payload/route timings.
5. Complete concise setup and two-minute verification documentation. Do not claim population accuracy from the small sample.

**Manual verification handoff:** start a live ticker from the home page and watch every stage update. Inspect one selected section, one retained chunk, one exact quote, one fact match, one miss/limitation if present, and the final report.

**Acceptance gate:** real calls and data are clearly identified; Jev receives only sanitized visible source content; every published claim has an exact quote; structured facts load only after discovery; refresh/resume works; misses remain visible; the configured demo budget completes a representative run or reports the precise exhausted limit.

**Final handoff:** provide the startup command, one representative run URL, measured results for each real company, remaining unsupported cases, and the shortest path for verifying that XBRL data did not enter Jev requests.

## T30 — Fresh-only storage schema; remove migrations

**Goal:** reduce persistence complexity by supporting only a newly created V2 database. Existing local run data may be discarded.

**Implement:**

1. Replace the versioned SQLite migration chain with one authoritative, current-schema creation path.
2. Remove every V2 schema migration function, version-upgrade branch, compatibility shim, and migration-specific test.
3. On opening an existing or incompatible V2 database, fail with a concise, actionable message explaining that stored data is unsupported and must be removed before starting again. Do not attempt conversion, partial reuse, or automatic deletion.
4. Update setup/help/docs to make the destructive compatibility boundary explicit and give the exact local data-directory reset instruction.
5. Preserve a focused clean-database integration test and add a controlled incompatible-database test. Delete tests that exist only to preserve upgrade behavior.

**Manual verification handoff:** start from an empty data directory and create a live run. Then point the application at a deliberately old database and confirm it refuses to start without altering that file; remove the local data directory, restart, and confirm a new database is created.

**Acceptance gate:** a clean V2 database has the full current schema; static search finds no V2 migration/version-upgrade code; no old data is read or silently modified; the reset path is documented and tested.

**Next: T31.**

## T31 — Remove offline fixture source mode

**Goal:** simplify the product to one real-data path: a live SEC filing source followed by configured provider calls.

**Implement:**

1. Remove `offline` as a V2 run/source mode, the home-page selector and explanatory copy, fixture source generation, fixture-provider branches, and offline-only V2 CLI behavior.
2. Make new V2 runs require a ticker and configured SEC contact; validate missing live prerequisites before creating a run, with clear remediation text.
3. Remove fixture-only runtime persistence, labels, limitations, and UI conditions. Keep narrowly scoped test doubles only where they test a deterministic contract without exposing an offline product path.
4. Replace end-to-end offline acceptance tests with saved real SEC documents/responses where practical, and retain unit tests that do not misrepresent synthetic output as an application mode.
5. Simplify README, task handoffs, and run instructions around the live workflow.

**Manual verification handoff:** open the home page and confirm only the ticker/live filing workflow is offered. With a configured SEC contact and provider credentials, create a run and confirm its source provenance is SEC; with credentials absent, confirm the page explains exactly what must be configured.

**Acceptance gate:** static search finds no supported V2 offline mode, fixture source option, or fixture-provider branch; no UI or CLI offers an offline run; live prerequisite errors are actionable; focused tests cover live-mode validation and the retained source contracts.

**Next: T32.**

## T32 — Diagnose and redesign exact-match evaluation

**Goal:** determine why quote-backed discoveries fail to match the exact structured facts currently used for evaluation, then make an evidence-backed decision to improve discovery, revise evaluation, or do both.

**Research and decide:**

1. Build a reviewed sample of real filings spanning at least three companies/accessions and record, for every expected fact, the structured fact, candidate visible source passages, discovered findings, and current match outcome.
2. Classify each mismatch before proposing changes: wrong metric/concept, fiscal-year or comparative-period ambiguity, unit/scale/rounding difference, attribution difference, duplicate fact, source-selection miss, extraction/normalization defect, or invalid/insufficient evaluation denominator.
3. Audit whether Company Facts is an appropriate oracle for each configured metric and filing scope. Document cases where a visible filing value legitimately cannot be expected to exactly equal a Company Facts value.
4. Compare at least two alternatives: improving the source-to-finding pipeline (selection, extraction, metadata normalization) and changing evaluation to a reviewed semantic/source-range or tolerance-aware protocol. Keep an exact-match metric only where its assumptions are demonstrably valid.
5. Write a short decision record with raw counts, examples, denominators, false-positive/false-negative risks, and a chosen follow-up implementation plan. Do not weaken evaluation merely to improve a score.
6. Add regression fixtures/tests for the confirmed mismatch classes and update the Evaluation UI and metrics only after the decision record specifies the valid comparison contract.

**Manual verification handoff:** open the evaluation report for each sampled real run, inspect one representative example from every observed mismatch class, and confirm the displayed denominator and match state follow the decision record.

**Acceptance gate:** every sampled non-exact result has a reviewed classification; all reported metrics name their oracle, scope, normalization, and denominator; the decision record explicitly chooses pipeline changes, evaluation changes, or both; no evaluation state treats incomparable data as a discovery failure.

**Final handoff:** provide the decision record, sample/run provenance, mismatch breakdown, selected metric definitions, and the next implementation task(s).
