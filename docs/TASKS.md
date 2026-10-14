# Implementation task history and execution policy

This file retains the completed implementation scopes and the task execution policy.
The final pipeline UI acceptance task, [T60](PIPELINE_IMPROVEMENT_TASKS.md), is
closed; its status and evidence are in [PROGRESS.md](PROGRESS.md). The active architecture
starts at T14, is specified in [V2_IMPLEMENTATION_PLAN.md](V2_IMPLEMENTATION_PLAN.md),
and intentionally does not migrate or read previous run data.

Planned fact-source debugging work is tracked as
[T61–T64](PIPELINE_IMPROVEMENT_TASKS.md#t61--retain-sec-presentation-locations-for-selected-facts):
SEC presentation provenance, exact canonical-line mapping, evaluation/Facts UI,
and real-filing acceptance. T61–T64 are DONE; T64's two-company automated
acceptance passed and the user confirmed cell, year and scale visibility.
T63 UI review is user-confirmed; manual visual reviews for T61–T62 remain pending.
Presentation rows are not exact canonical-line mappings.

Planned discovery explanation adjustments are tracked as
[T65–T68](PIPELINE_IMPROVEMENT_TASKS.md#t65t68-execution-contract--separate-fresh-context-agents).
Each task is assigned to a separate fresh-context agent, executed sequentially:
shared purpose/README, Source/Outline/Sections, Chunks/Evidence, then Findings.
They explain current behavior without changing runtime or Facts/Evaluate.

Commands and checks below are acceptance contracts to implement, not claims that they already exist.

The next runtime improvement is planned in
[JEV-led Findings, T69–T77](FINDINGS_JEV_IMPLEMENTATION_PLAN.md).
Different fresh-context agents execute its tasks sequentially when implementation
is requested. It replaces Findings in place with concept candidates, JEV line
assignment/context assembly/ranking, then selected-evidence LLM conversion. UI and
runtime activation are one task; the current local V2 database may be discarded.
Planning does not start implementation, create a v3 or require compatibility.

Completed pipeline UI scopes T48–T59 are in
[PIPELINE_UI_COMPLETED_TASKS.md](PIPELINE_UI_COMPLETED_TASKS.md). The current
[pipeline page design brief](PIPELINE_PAGE_DESIGN.md) owns UI decisions; the
[review](PIPELINE_IMPLEMENTATION_REVIEW.md) records the original findings. The
T39–T47 card layout rules below are historical.

## Execution policy for every task

Apply this policy to an active task; completed scopes below are historical.

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
| T28 | Scale-aware Jev evaluation verdicts | T27 |
| T29 | Readable evaluation comparison cards | T28 |
| T30 | Random eligible ticker picker | T29 |
| T31 | Jev retrieval benchmark against simple baselines | T30 |
| T32 | Complete measured real-data demonstration | T31 |
| T33 | Fresh-only storage schema with migration history removed | T32 |
| T34 | Live-SEC-only source workflow with offline fixture mode removed | T33 |
| T35 | Evidence-backed evaluation redesign decision | T34 |
| T36 | Overall cross-run evaluation scorecard | T35 |
| T37 | Sequential random-report batch runner | T36 |
| T38 | Versioned run timing and evaluation cohorts | T37 |

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
2. Require typed findings with an exact quote, source chunk/range, and required Decimal amount matched to the quote. Period, visible scale/unit, attribution, and limitations are optional; do not request narrative prose.
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
   while each retained chunk supplies numbered core evidence lines and separately
   labeled context lines. Require every finding to name one core source line and
   quote an exact substring of that line; context may inform interpretation but
   must never be cited. Preserve source-range identities and enforce the configured
   request budget.
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
retain an exact quote from their declared core source line; the exact quote need
not repeat period/unit/scale context from another retained visible line; missing
source support cannot silently produce a year, unit, scale, or attribution claim.

**Next: T28.**

## T28 — Scale-aware Jev evaluation verdicts

**Goal:** distinguish a genuine discovery mismatch from the same reported value
shown at a different explicitly visible scale or unit.

**Read:** V2 plan sections 8–10 and 15. Dependency: T27.

**Implement:**

1. Keep the existing deterministic exact Decimal comparison as the baseline. For
   bounded candidate finding/fact pairs that are not exact, call Jev after both
   findings and Company Facts are sealed. This is an evaluation-only provider call:
   no Company Facts value, verdict, or evaluation output may enter outline,
   scoring, chunking, or findings requests.
2. Send the judge the finding's required amount, optional period/unit, declared
   core evidence line, separately labeled retained context lines, and the candidate
   structured fact's amount, unit, and fiscal period. Ask one constrained boolean
   question only: whether the visible finding and structured fact represent the
   same annual metric/value after applying an explicitly visible scale or unit.
   “Insufficient visible support,” different period, metric, attribution, or unit
   must answer `false`; the judge must not invent a conversion.
3. Persist the boolean verdict, the exact finding/fact IDs, prompt/configuration
   version, model identity, and sanitized request/response trace. Cache by the
   pair and visible-context hash. Bound the number of candidate pairs and provider
   calls per run; do not send every combination of findings and facts.
4. Add evaluation states that distinguish deterministic exact matches, Jev-confirmed
   scale-aware equivalence, and rejected/inconclusive candidate pairs. A `true`
   verdict may improve the evaluation display and metrics, but never rewrites the
   finding amount, unit, period, citation, or Company Fact.
5. Add controlled fixtures for the same amount expressed in units and thousands,
   a genuine value mismatch, and missing scale context. Render the deterministic
   comparison and Jev boolean verdict side by side with source jumps and provider
   provenance.

**Manual verification handoff:** open an evaluation with a finding such as
`237,789` and a Company Fact `237,789,000`, where the retained context states
“in thousands.” Confirm the exact comparison remains non-exact, the Jev verdict
is `true`, and the UI labels it as scale-aware equivalence. Open a same-period
but genuinely different amount and confirm the verdict is `false`.

**Acceptance gate:** Jev receives only post-seal evaluation pairs and sanitized
visible context; a boolean `true` requires visible scale/unit support and never
mutates discovery or Company Facts; false/inconclusive pairs remain visible;
exact-match reporting remains separately available; cache/call bounds and model
identity are inspectable.

**Next: T29.**

## T29 — Readable evaluation comparison cards

**Goal:** make every evaluation result understandable at a glance, including exact,
scale-aware, rejected, unresolved, and missing outcomes.

**Read:** V2 plan sections 10–11. Dependency: T28.

**Implement:**

1. Replace the dense evaluation table with one compact comparison card per expected
   fact and a separate clearly labeled card for additional visible findings. Make
   metric, requested/current fiscal year, status, discovered amount, structured
   amount, unit/scale, and evidence source the primary visual hierarchy.
2. Present deterministic comparison and any Jev boolean verdict together without
   collapsing their meanings. State plainly whether a result is exact, confirmed
   scale-aware equivalent, rejected by Jev, unresolved, or missing; never present
   a Jev verdict as a changed source value.
3. Put the exact quote, declared evidence line, source jump, retained scale/period
   context, fact provenance, provider/model identity, and diagnostic JSON behind
   compact progressive-disclosure controls. Avoid raw JSON or long prose in the
   default card view.
4. Add status-specific visual treatments and accessible text labels; retain a
   sortable/filterable summary for all outcomes. The layout must remain legible on
   a narrow viewport and with a mix of matched, missing, and additional findings.
5. Add template-level and focused UI tests for a scale-aware match, genuine
   mismatch, missing fact, and additional finding. This task changes presentation
   only: it does not alter evaluation verdicts, provider requests, or metrics.

**Manual verification handoff:** open an evaluation containing all four outcome
types. Identify the status and both amounts of each card without opening details;
then expand one card and follow its finding quote and fact provenance links.

**Acceptance gate:** the default evaluation view contains no opaque raw payloads;
each result makes its comparison state, amounts, and source direction clear;
deterministic and Jev-assisted decisions remain visibly distinct; keyboard and
narrow-screen views retain all essential information.

**Next: T30.**

## T30 — Random eligible ticker picker

**Goal:** let a user start a run without having to choose a ticker manually.

**Read:** V2 plan sections 4, 11, and 12. Dependency: T29.

**Implement:**

1. Add a **Random eligible ticker** control to the fresh-run form. It must populate
   the existing ticker input and leave run creation under the user's explicit
   control; selecting a ticker must not itself start a provider or SEC filing run.
2. Reuse the SEC ticker-directory/cache path to construct a deduplicated candidate
   pool. Sample without a fixed demonstration-company list and record only the
   directory provenance/version needed to explain the selection.
3. Before presenting a candidate, use bounded existing filing-discovery rules to
   confirm it has an eligible recent 10-K for the supported workflow. Retry a
   small fixed number of candidates; if none qualify or SEC prerequisites are
   unavailable, show an actionable error and preserve the manually entered ticker.
4. Make the selection auditable but privacy-preserving: record the displayed
   ticker, selection timestamp, directory provenance/cache status, and eligibility
   result. Do not expose a giant ticker list or retain unrelated company data.
5. Add focused tests for deterministic injected randomness, duplicate ticker
   handling, an ineligible candidate followed by an eligible one, exhausted
   selection, and the guarantee that pressing the control does not create a run.

**Manual verification handoff:** open the home page, press **Random eligible ticker**,
confirm the ticker field changes while no run appears, then create the run explicitly.
Repeat after forcing no eligible candidate and confirm the manual field remains intact
with a clear remediation message.

**Acceptance gate:** each displayed random ticker has passed the supported 10-K
eligibility check; no run/provider call starts before the user submits the form;
selection retries and failures are bounded and inspectable; manual ticker entry
continues to work unchanged.

**Next: T31.**

## T31 — Retrieval benchmark and baselines

**Goal:** measure whether Jev improves discovery efficiency while preserving required visible evidence.

**Read:** V2 plan sections 14–16. Dependency: T30.

**Implement:**

1. Create immutable development and held-out datasets split by company/accession, with reviewed source ranges for relevant facts, misleading quarterly/segment/non-GAAP values, explanations, comparability passages, and irrelevant sections.
2. Add baselines: keep all, heading/keyword rules, structural rules, Jev section scoring, and Jev section-plus-chunk scoring.
3. Pin model/question/prompt versions. Never tune thresholds on held-out companies.
4. Measure relevant-range recall, structured-fact coverage, exact value accuracy, recall at retained-source budget, source percentage explored, calls, usage, latency, and time to first matching fact.
5. Report Jev-only, application-policy, and optional recovery results separately. Never treat an XBRL-unlabeled passage automatically as irrelevant.
6. Add an evaluation view with configuration comparison and clickable missed source ranges.

**Manual verification handoff:** compare at least two strategies, open one miss and one false-positive candidate, and confirm live/fake/replayed provider identity and sample counts are visible.

**Acceptance gate:** gold ranges and structured facts never enter Jev requests; overlap is deduplicated; denominators are explained; initial held-out targets remain at least 95% relevant-range recall, 100% required-fact coverage, and no wrong selected metric/year values, or the UI clearly reports that the targets were not met.

**Next: T32.**

## T32 — Final real-data, real-time demonstration

**Goal:** prove the streamlined V2 pipeline works end to end on varied real filings and remains inspectable when imperfect.

**Read:** all V2 plan sections. Dependency: T31.

**Implement:**

1. Run at least three real companies with materially different filing structures and one to four requested annual filings.
2. Verify source sanitization, outline navigation, section/chunk scores, quote-backed findings, post-discovery facts, and fact comparison for each run.
3. Exercise cancellation, resume, provider overload, malformed outline/finding output, missing structured fact, and quote-validation failure.
4. Record source percentage explored, exact fact coverage, Jev/LLM calls and usage, time to first finding, total runtime, database size, and UI payload/route timings.
5. Complete concise setup and two-minute verification documentation. Do not claim population accuracy from the small sample.

**Manual verification handoff:** start a live ticker from the home page and watch every stage update. Inspect one selected section, one retained chunk, one exact quote, one fact match, one miss/limitation if present, and the final report.

**Acceptance gate:** real calls and data are clearly identified; Jev receives only sanitized visible source content; every published claim has an exact quote; structured facts load only after discovery; refresh/resume works; misses remain visible; the configured demo budget completes a representative run or reports the precise exhausted limit.

**Final handoff:** provide the startup command, one representative run URL, measured results for each real company, remaining unsupported cases, and the shortest path for verifying that XBRL data did not enter Jev requests.

## T33 — Fresh-only storage schema; remove migrations

**Goal:** reduce persistence complexity by supporting only a newly created V2 database. Existing local run data may be discarded.

**Decision:** the user explicitly authorizes deletion of the current local V2 data for
this cleanup. Preserve no migration, export, compatibility, or recovery path for it.

**Implement:**

1. Replace the versioned SQLite migration chain with one authoritative, current-schema creation path.
2. Remove every V2 schema migration function, version-upgrade branch, compatibility shim, and migration-specific test.
3. On opening an existing or incompatible V2 database, fail with a concise, actionable message explaining that stored data is unsupported and must be removed before starting again. Do not attempt conversion, partial reuse, or automatic deletion.
4. Update setup/help/docs to make the destructive compatibility boundary explicit and give the exact local data-directory reset instruction.
5. Preserve a focused clean-database integration test and add a controlled incompatible-database test. Delete tests that exist only to preserve upgrade behavior.

**Manual verification handoff:** start from an empty data directory and create a live run. Then point the application at a deliberately old database and confirm it refuses to start without altering that file; remove the local data directory, restart, and confirm a new database is created.

**Acceptance gate:** a clean V2 database has the full current schema; static search finds no V2 migration/version-upgrade code; no old data is read or silently modified; the reset path is documented and tested.

**Next: T34.**

## T34 — Remove offline fixture source mode

**Goal:** simplify the product to one real-data path: a live SEC filing source followed by configured provider calls.

**Implement:**

1. Remove `offline` as a V2 run/source mode, the home-page selector and explanatory copy, fixture source generation, fixture-provider branches, and offline-only V2 CLI behavior.
2. Make new V2 runs require a ticker and configured SEC contact; validate missing live prerequisites before creating a run, with clear remediation text.
3. Remove fixture-only runtime persistence, labels, limitations, and UI conditions. Keep narrowly scoped test doubles only where they test a deterministic contract without exposing an offline product path.
4. Replace end-to-end offline acceptance tests with saved real SEC documents/responses where practical, and retain unit tests that do not misrepresent synthetic output as an application mode.
5. Simplify README, task handoffs, and run instructions around the live workflow.

**Manual verification handoff:** open the home page and confirm only the ticker/live filing workflow is offered. With a configured SEC contact and provider credentials, create a run and confirm its source provenance is SEC; with credentials absent, confirm the page explains exactly what must be configured.

**Acceptance gate:** static search finds no supported V2 offline mode, fixture source option, or fixture-provider branch; no UI or CLI offers an offline run; live prerequisite errors are actionable; focused tests cover live-mode validation and the retained source contracts.

**Next: T35.**

## T35 — Diagnose and redesign exact-match evaluation

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

## T36 — Overall cross-run evaluation scorecard

**Goal:** make aggregate quality measurable across every V2 run without hiding
failed, incomplete, or incomparable runs behind a favorable score.

**Read:** V2 plan sections 10, 14, and 16, plus the T35 decision record. Dependency:
T35.

**Implement:**

1. Define a versioned evaluation unit from T35's approved metric, period, oracle, and
   normalization contract. Aggregate every persisted V2 run in the current database:
   completed evaluable runs contribute units; cancelled, failed, incomplete, and
   unsupported/incomparable runs appear in a run-accounting ledger with their exact
   exclusion reason and are never silently dropped.
2. Build a global confusion matrix over reviewed evaluation units. Report true
   positives (accepted, correct visible evidence), false positives (accepted but
   incorrect/additional evidence), false negatives (required facts without accepted
   correct evidence), and true negatives only when the reviewed negative-candidate
   denominator makes them meaningful. Do not invent a true-negative count from the
   unbounded filing text.
3. Compute precision, recall, and F1 from the matrix with explicit zero-denominator
   behavior and both micro and per-metric/per-period breakdowns. Keep deterministic,
   Jev-assisted, and any T35 semantic-review outcomes separately selectable; do not
   combine their denominators by default.
4. Persist the aggregation configuration, run IDs, evaluation-contract version,
   calculation timestamp, counts, and warnings. Recompute deterministically when a
   run's evaluations change; do not call SEC, Jev, or an LLM to calculate scores.
5. Add a bounded overall-score UI showing run coverage, exclusion reasons, confusion
   matrix, precision/recall/F1, and links from every matrix cell to the contributing
   run/comparison records. Make an unavailable or statistically non-meaningful metric
   visibly unavailable rather than displaying `0%`.
6. Add one hand-constructed multi-run aggregate invariant test, one incomplete-run
   accounting test, and one route/UI test that verifies the displayed denominators and
   links. Include regression coverage for no positives, no predicted positives, and no
   reviewed negatives.

**Manual verification handoff:** open the overall score page after at least two
completed live runs and one incomplete/failed run. Confirm every run appears in either
the included set or exclusion ledger, trace one TP, FP, and FN to its comparison, and
confirm the displayed precision, recall, and F1 reproduce the matrix counts.

**Acceptance gate:** every stored V2 run is accounted for; the scorecard names its
evaluation contract and denominators; matrix cells are inspectable; precision, recall,
and F1 agree exactly with the persisted counts; no unsupported or incomparable unit is
classified as a false negative; no provider call is caused by score aggregation.

## T37 — Sequential random-report batch runner

**Goal:** run a user-chosen bounded number of independently selected eligible-company
reports, one at a time, without requiring repeated manual ticker selection.

**Read:** T30 picker behavior, V2 plan sections 2, 11, and 12, and T36 aggregation.
Dependency: T36.

**Implement:**

1. Add a batch control that accepts an explicit integer `n` within a conservative
   configured maximum. It creates a durable batch record and executes at most `n`
   reports sequentially: choose one random eligible ticker, complete or terminally
   fail that run, then choose the next. Never launch two report pipelines concurrently.
2. Reuse the eligible-ticker picker and its current-workspace exclusion policy. Within
   one batch, exclude every ticker already attempted by that batch; explain if the
   candidate pool is exhausted before `n` runs can be started. Do not use a fixed
   demonstration-company list.
3. Before each new report, recheck live prerequisites and eligibility. Treat a picker
   failure, no eligible filing, cancellation, provider failure, or source failure as a
   recorded terminal batch item and continue only when the configured batch policy
   permits it. Bound retries and total work; never spin indefinitely.
4. Persist batch status, requested count, attempt order, selected ticker, linked run
   ID when created, timestamps, terminal outcome, and concise error/remediation. Show
   progress as completed/failed/skipped/requested and link each created run. Do not
   duplicate source or provider payloads in batch records.
5. Provide cancellation that prevents future selections after the in-flight run reaches
   a safe terminal state, and resume that continues only the remaining count with the
   same uniqueness rules. Surface batch errors without hiding already completed runs.
6. Add focused tests for deterministic injected random selection, strict one-at-a-time
   execution, within-batch uniqueness, exhaustion before `n`, failed-run accounting,
   cancellation/resume, and the invariant that batch orchestration itself makes no
   extra provider calls beyond its child runs.

**Manual verification handoff:** start a batch of `n=3`, open its progress page, and
confirm only one child run is active at any moment. Follow each report link, confirm
the selected tickers are distinct within the batch, cancel after one completes, then
resume and verify only the remaining reports are selected. Open T36 afterward and
confirm completed/evaluable runs and failed/incomplete runs are all accounted for.

**Acceptance gate:** a batch runs no more than `n` reports and never runs them in
parallel; every attempted selection has a persisted outcome; tickers are not repeated
within a batch unless an explicit exhausted-pool fallback is shown; cancellation and
resume are durable; each child run remains independently inspectable; aggregate
scoring can account for every resulting run.

## T38 — Versioned run timing and evaluation cohorts

**Goal:** make every run reproducible and comparable by recording its implementation
version, every stage runtime, and total run runtime; aggregate evaluation only within
one identical-version cohort.

**Read:** V2 plan sections 2, 3, 10, and 12, plus T36/T37. Dependency: T37.

**Implement:**

1. Define an immutable run-version identifier at creation time. It must identify the
   executable/application revision and all behavior-affecting evaluation and pipeline
   configuration versions (including prompts, models, target definitions, and score
   contract); record a clear `unknown`/non-comparable state when a component cannot be
   resolved. A later code or configuration change never mutates an existing run's
   version.
2. Persist monotonic elapsed timing for every pipeline stage and the complete run,
   including queued, active-work, retry/backoff, cancellation, and terminal timing as
   separately labelled components where applicable. Keep wall-clock timestamps for
   chronology, but calculate reported durations from monotonic measurements so clock
   changes cannot corrupt them.
3. Update the run workspace and batch views to show total elapsed time and a compact
   stage timing breakdown with status, while preserving partial/cancelled timing and
   clearly marking unavailable timings. Do not imply that sum-of-stage active work
   equals wall-clock runtime when queueing or backoff occurred.
4. Add version and timing provenance to each evaluation record and to the T36 overall
   score page. The default aggregate must select exactly one run version and include
   only runs with that exact version. Other versions appear as separate cohorts with
   their run counts and exclusion notice; never pool them into precision, recall, F1,
   or confusion-matrix denominators.
5. Add a version selector and direct cohort/run links. If no cohort has enough
   evaluable runs, show its accounting and metrics as unavailable rather than combining
   incompatible data. Batch T37 may create multiple cohorts if the application changes
   between child runs; show that explicitly.
6. Add tests for stable version capture, changed configuration yielding a different
   version, completed/failed/cancelled timing, deterministic total-vs-stage accounting,
   and an aggregate fixture proving identical-version runs are included while a
   different-version run is excluded from every score denominator.

**Manual verification handoff:** create or inspect two completed runs with the same
version and one with a deliberately changed versioned setting. Open each workspace to
compare stage and total timing, then open the overall evaluation: select the shared
version and confirm only its two runs contribute to the matrix/precision/recall/F1;
select the other version and confirm it is shown as its own cohort.

**Acceptance gate:** every newly created run has immutable version provenance and
total/stage timing; terminal and partial states retain honest durations; all aggregate
evaluation denominators contain exactly one selected run version; cross-version runs
are visibly accounted for but never silently pooled; timing/version data require no
provider calls to inspect.

## T39 — Pipeline-card layout scaffold

**Goal:** replace the current compact, multi-column architecture map with a spacious
vertical pipeline layout before adding real per-stage card content. This is a layout
task only: use deliberately obvious placeholder card copy, not inferred runtime
details.

**Dependency:** T38. Complete this before any T40–T47 card task.

**Implement:**

1. On the default `/v2/runs/{run_id}/pipeline` overview, arrange the discovery path
   as one readable top-to-bottom line: `Source → Outline → Sections → Chunks →
   Evidence → Findings → Evaluate`. Place `Facts` below `Evaluate` with a directional
   connector flowing upward into `Evaluate`. The picture must make clear that Evaluate
   is the only merge point, while not implying that Facts runs concurrently with
   Findings.
2. Increase card size enough to reserve a stable anatomy for a visual process summary,
   a short plain-language description, and a prompt tooltip/control. Use fixed
   placeholders for those regions in this task; do not expose service internals,
   provider traces, or new data on the overview yet.
3. Preserve existing links, live status/progress/duration updates, keyboard focus,
   non-colour status text, and selected-stage pages. Keep the layout responsive: at
   narrow widths it remains a single directional reading order with no overlapping
   connector or inaccessible card.
4. Write the visual contract into `docs/UI_PIPELINE_REORGANIZATION_PLAN.md`, including
   the vertical ordering, the Facts-to-Evaluate upward input, card anatomy, and mobile
   behavior. Replace or clearly supersede the earlier two-horizontal-lane diagram so
   later tasks have one source of truth.
5. Add focused overview/template/CSS tests for ordering, the facts-to-evaluate
   relationship, placeholder-only scope, links, and keyboard/accessibility hooks.

**Not in scope:** real descriptions, prompt strings, provider request inspection,
changing execution order, or changing any stage service.

**Manual verification handoff:** open a completed and a running Pipeline overview.
Confirm the large placeholder cards form the specified vertical route; follow Facts
up into Evaluate visually; tab through every card; then check the narrow layout.

**Acceptance gate:** the overview communicates the intended flow using placeholder
content only, all eight cards remain reachable and live-updating, and no product
behavior or provider payload changes.

## Shared contract for T40–T47 — truthful card content and prompt provenance

Each following task owns exactly one stage card. The card must explain what that
stage actually does in the current code, not an aspirational workflow. It must contain
a compact visual input → operation → output summary, a short description, and a
keyboard- and touch-accessible “Prompt used” tooltip/control.

For a provider-backed stage, the tooltip text must be derived from the same prompt
builder/value passed in the request path (for example, an exposed read-only prompt
view-model derived from `OutlineService._prompt`, `FindingsService._prompt`, or the
`NoulQuestion.instructions` values used to build `JevRequest`). A copied prose
description, prompt version label, trace record, or independently maintained UI string
does not satisfy this contract. Preserve redaction and never put filing text, secrets,
or a full request payload into the tooltip. If the prompt is parameterized, show the
actual instruction template with its dynamic inputs represented safely and identify
the current prompt version/model where the request code does.

For a stage with no LLM/Jev prompt, its control must explicitly say “No model prompt:
[actual operation]” and identify the relevant code-owned operation/configuration;
it must not invent a prompt. Tooltips must remain usable by keyboard, screen readers,
and touch, and must not interfere with the card’s stage link.

Every task must add a regression test that proves the rendered tooltip comes from the
request-construction source (or proves the no-prompt path), plus a route/UI test of the
card’s visible process summary. Do not start another card task in the same session.

## T40 — Source card: SEC filing to canonical visible lines

**Goal:** make the Source card truthfully show the SEC acquisition and visible-HTML
canonicalization performed by `V2SourceService.acquire`.

**Dependency:** T39.

**Implement:** depict `ticker → SEC primary filing HTML → sanitized, line-addressable
canonical document`; describe filing discovery, hidden Inline XBRL removal, visible
HTML preservation, source hash, and numbered lines in concise user-facing language.
The prompt control must state that no model prompt is used and point to the actual SEC
acquisition/canonicalization operation and its configured request identity. Surface
only persisted, safe run facts such as form, report date, line count, and source hash
status when available; never display raw HTML or credentials in the card.

**Acceptance gate:** the card does not claim LLM/Jev involvement, accurately reflects
`V2SourceService`, and its visual outputs match the persisted source-stage artifacts.

## T41 — Outline card: canonical lines to validated navigation ranges

**Goal:** make the Outline card show the windowed LLM navigation pass implemented by
`OutlineService`.

**Dependency:** T40.

**Implement:** depict `numbered canonical-line windows → configured LLM → validated,
reconciled outline sections`; state that generated topics are navigation metadata while
titles/quotes/ranges are validated against source. Derive its tooltip from the exact
`OutlineService._prompt` value supplied to the chat-completions call, with safe dynamic
input placeholders and the configured outline model/prompt version. Represent actual
window count, validated ranges, rejected proposals, cached batches, and model outcome
only when persisted.

**Acceptance gate:** changing the outline request prompt changes the tooltip through
the shared source, and the card never presents generated navigation as source text.

## T42 — Sections card: visible outline descriptors to Jev relevance scores

**Goal:** make the Sections card show the visible-only Jev scoring and deterministic
selection policy in `SectionScoringService`.

**Dependency:** T41.

**Implement:** depict `validated outline descriptors → Jev target questions → score
vectors → selected/uncertain/skipped sections`; describe the allowed visible context
and the separation between Jev scores and local selection policy. Build the tooltip
from the exact `TARGETS` instruction values inserted into `_request` as
`NoulQuestion.instructions`, not a duplicated target list. Show actual target coverage,
batch/cached-call counts, and selection totals where available.

**Acceptance gate:** every displayed Jev question is sourced from the request builder,
and the card clearly states that Company Facts/evaluation values are excluded.

## T43 — Chunks card: selected sections to bounded source ranges

**Goal:** make the Chunks card show the deterministic range chunking performed by
`SourceRangeChunker`.

**Dependency:** T42.

**Implement:** depict `selected outline sections → boundary-aware split → core ranges
plus overlap context`; explain that core ranges own coverage and overlap is context,
not independent evidence. Its prompt control must explicitly identify the no-model
path and derive the relevant boundary/size configuration from the chunker used by the
pipeline. Show actual selected-section, chunk, core-line, and bounded-size values when
available.

**Acceptance gate:** no model prompt is implied; the card’s content agrees with the
stored `TextChunk` ranges and never treats overlap as separately discovered evidence.

## T44 — Evidence card: chunks to ranked retained evidence

**Goal:** make the Evidence card show detailed Jev chunk scoring and the local
diversity/budget policy in `ChunkScoringService`.

**Dependency:** T43.

**Implement:** depict `bounded visible chunks → Jev target questions → score vectors
→ diverse retained/uncertain/skipped evidence`; explain the overlap-deduplication,
target/section/year diversity, and retained-text budget without portraying them as Jev
decisions. Derive the tooltip from the actual `TARGETS` instruction values placed in
the chunk-scoring `JevRequest`. Show real input chunks, live/cached batches, token use,
retained characters, and policy counts only when they exist.

**Acceptance gate:** the tooltip and provider questions share their source, and the
visual separates model scoring from deterministic evidence retention.

## T45 — Findings card: retained evidence to quote-validated numeric findings

**Goal:** make the Findings card show constrained LLM extraction and quote validation
in `FindingsService`.

**Dependency:** T44.

**Implement:** depict `retained visible chunks + navigation context → configured LLM
→ proposed findings → exact-quote/Decimal validation → published findings`; state that
invalid proposals are rejected or receive one bounded repair attempt and unresolved
metadata is not guessed. Derive the tooltip from the exact `FindingsService._prompt`
value used in `_live`, including safe representation of the repair variant. Show actual
retained chunks, requests, rejected items, fallback status, and published finding count
when persisted.

**Acceptance gate:** the card cannot imply that uncited model prose is published, and
the rendered tooltip changes with the real findings prompt builder.

## T46 — Facts card: sealed findings to independent SEC Company Facts

**Goal:** make the Facts card show the post-discovery SEC retrieval and conservative
normalization in `CompanyFactsService`.

**Dependency:** T45.

**Implement:** depict `sealed findings + filing CIK → SEC Company Facts JSON →
configured annual facts and retained alternatives`; describe the strict ordering gate,
selected accession/form/annual-period filtering, concept mapping, and independent
oracle role. Its prompt control must state that no model prompt is used and derive the
visible mapping/configuration from `FACT_TARGETS` and the actual loader path. Show safe
persisted provenance, supported-fact count, and alternatives count when available.

**Acceptance gate:** the card makes clear that Facts is an independent bottom input to
Evaluate and never says structured facts were available to earlier Jev/LLM stages.

## T47 — Evaluate card: independent facts and findings to comparison outcomes

**Goal:** make the Evaluate card show both deterministic comparison and the bounded,
conditional Jev scale-aware verdict in `EvaluationService`.

**Dependency:** T46.

**Implement:** depict the two inputs explicitly: `quote-backed findings` from above
and `SEC Company Facts` from below, converging into `exact Decimal comparison →
conditional Jev scale/unit check → inspectable outcomes`. Describe that evaluation is
non-mutating and that a miss remains a miss. The prompt control must provide two
truthful branches: no model prompt for deterministic comparison, and, when the
scale-aware provider path is applicable, instructions derived from the exact
evaluation `JevRequest`/`NoulQuestion` construction. Show actual comparison states,
provider/cached-call data, and evaluation contract/version only when persisted.

**Acceptance gate:** the card accurately represents the sole merge point, does not
claim Jev runs for every comparison, and its conditional prompt text is coupled to the
same request-building source used by evaluation.
