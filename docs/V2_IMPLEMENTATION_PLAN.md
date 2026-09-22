# ProfitLab V2 — source-guided Jev discovery

This is the design authority for T14 onward. V1 remains historical context in `IMPLEMENTATION_PLAN.md`; V2 does not migrate or read V1 run data.

## 1. Objective and constraints

Demonstrate on real SEC filings, in real time, that Jev can navigate a long human-visible document, score promising regions, retain a small evidence set, and support quote-backed findings. Load SEC structured facts only after discovery and use them as an independent measurement source. Never supply XBRL metadata, concepts, oracle values, or evaluation labels to Jev or the findings LLM.

Initial targets are annual net income/shareholder profit, diluted EPS, diluted weighted-average shares, explanations of earnings changes, and restatement/comparability information.

- Reuse FastAPI/Jinja, SEC transport/discovery, provider adapters, settings, redaction, Decimal utilities, and cancellation/resume logic when they fit the new boundaries.
- Prefer a few strong contracts over new frameworks. Do not build a generic workflow/plugin engine or a frontend SPA.
- Previous runs and schemas are unsupported. Use a new V2 schema/data namespace and require fresh runs.
- Keep the application functional after every task. Each stage receives a usable detail UI when implemented.
- Use SQLite for queryable state and a few immutable/compressed blobs. Do not persist one file per source cell or intermediate attempt.
- Default views contain decisions and summaries. Raw payloads and diagnostics load only on demand.

## 2. Pipeline

The user-visible stages are:

1. `source` — retrieve and sanitize visible filing HTML into a canonical line document.
2. `outline` — use a low-cost LLM to propose source-ranged topics and titles.
3. `section_score` — use Jev to rank outline sections.
4. `chunk` — split only selected sections into bounded source-ranged chunks with overlap.
5. `chunk_score` — use Jev to rank detailed chunks and retain a diverse top set.
6. `findings` — use an LLM to create quote-backed findings and observed numbers.
7. `facts` — retrieve and normalize SEC Company Facts after discovery is sealed.
8. `evaluate` — compare independent structured facts with discovered visible evidence and build the report.

Statuses are `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`, and `interrupted`. Persist progress before emitting live events.

## 3. Core contracts

- `StageSnapshot`: stage status, completed/total work, timing, summary, limitation, error, and version hashes.
- `CanonicalDocument`: source hash, ordered visible lines, slicing, quote lookup, and HTML-anchor resolution.
- `SourceRange`: document ID, start/end lines, optional character coordinates, and source hash.
- `OutlineSection`: generated topic, exact source title, primary range, parent hint, and boundary warnings.
- `TextChunk`: section ID, core range, context ranges, request estimate, and lineage.
- `ScoredItem`: item ID, target score vector, model/call identity, policy decision, and reason. Reuse it for sections and chunks.
- `Finding`: narrative, exact quote spans, observed raw/normalized numbers, period/attribution hypotheses, limitations, and validation state.
- `StructuredFact`: concept, metric mapping, exact Decimal value, unit, period, accession, form, and filed date.
- `FactComparison`: expected fact, matching findings, comparison state, and discovery-cost measures.

All downstream source text must be obtained through `CanonicalDocument.slice(SourceRange)`. No stage may persist an untracked source copy as authoritative evidence.

## 4. Canonical visible source

Treat the primary filing as visible HTML only. Remove Inline XBRL headers and hidden facts, unwrap visible Inline XBRL elements, and strip taxonomy concepts, contexts, units, scales, formats, and namespace attributes. Preserve headings, paragraphs, lists, captions, and table rows in document order.

Each nonblank canonical line has a stable line number, normalized visible text, element type, HTML anchor/DOM reference, and source hash. Concatenated lines reproduce visible source text under a documented whitespace policy.

Quote resolution searches inside the finding's source range, chooses the first exact occurrence within that range, and resolves through the matching canonical line. Never use a global first-text match across the filing.

## 5. LLM outline

Send numbered canonical lines in bounded, overlapping windows to a configurable inexpensive model. Request only generated topic, exact visible title when present, start/end line, optional exact representative quote, section type, and parent hint.

Generated topics are navigation metadata, not source. Validate ranges against the supplied window and validate source titles/quotes exactly. Reconcile overlapping proposals deterministically, prefer explicit headings, and create an ordered partition in which every nonblank line has exactly one primary owner. Persist uncertainty instead of inventing boundaries.

Cache by source-range hash, prompt version, configuration, and actual model.

## 6. Jev section discovery

`JevVisibleContext` is an allowlist containing only section ID, generated topic, exact visible heading, size, short exact preview, and filing metadata. Reject extra fields.

Score each section against the initial target questions. Batch descriptors/questions within verified provider limits. Store raw Jev scores separately from application decisions. Selection prioritizes potential coverage of an uncovered target, higher Jev score, smaller exploration cost, then earlier source order. Retain a bounded uncertain band for recall. Never label a score as probability of financial correctness.

## 7. Source-range chunking and detailed scoring

Chunk only selected outline sections. Preserve small sections; split large sections at canonical block/table-row boundaries. Store one core range plus separate context/overlap ranges. Do not split table rows, combine filings, or join unrelated sections. Primary ranges establish coverage; overlap supplies context and is deduplicated.

Score exact chunk text with visible heading and filing metadata. Enforce request, input, retained-text, and elapsed-time budgets. Deduplicate overlapping chunks before top-N selection and preserve diversity across filing, section, target, and visible year labels. Checkpoint after every batch.

## 8. Quote-backed findings

Supply only retained chunks, filing metadata, and target definitions to the findings LLM. Require typed narrative, exact quotes, source range, observed raw numbers, normalized Decimal proposals, visible unit/scale, period, attribution, and limitations.

Every published finding must contain at least one exact quote validated inside its referenced chunk and canonical source. Permit one bounded quote-repair attempt; otherwise reject the finding. Unclear scale, period, or attribution remains unresolved. Deduplicate repeated quotes/numbers introduced by overlap.

## 9. XBRL isolation and structured facts

Structured facts are unavailable until findings are sealed. Then retrieve SEC Company Facts once per company; do not parse Inline XBRL from filing HTML.

Initial supported concepts include `NetIncomeLoss`, `ProfitLoss`, common-stockholder basic/diluted income concepts, `EarningsPerShareDiluted`, and `WeightedAverageNumberOfDilutedSharesOutstanding`. Target configuration defines accepted concepts, units, annual-period rules, and attribution labels.

Enforce non-leakage through the allowlisted Jev request contract, sanitization scans for XBRL namespaces/keys, stage ordering, canary tests using known fact values, persisted request inspection, and tests proving evaluation records cannot be read by discovery services. Visible numbers naturally printed in the filing are allowed; XBRL metadata and oracle data are not.

## 10. Independent comparison

Compare findings and structured facts by configured metric, exact normalized Decimal, unit/scale, annual period, and filing scope. States are exact match; value match/period unresolved; period match/value mismatch; structured fact missed; additional visible value; unsupported; and ambiguous duplicate.

Evaluation never repairs or mutates discovery. Report Jev-only outcomes separately from deterministic application policy or recovery. Measure expected facts, exact matches, misses, additional visible numbers, value/period accuracy, calls and source lines before first match, retained-source percentage, time to first finding, total latency, and provider usage.

## 11. Real-time UI

Primary navigation is Runs, Pipeline, Report, and Evaluation. The run workspace has an eight-stage rail and one selected-stage detail region. Every stage uses the same order: purpose, progress, inputs, output summary, inspectable items, warnings, and on-demand trace.

Stage views are: paginated numbered source lines; outline topics/ranges/warnings; ranked section scores and policy; core/overlap chunks; ranked detailed scores and budget; findings with exact quotes and source highlights; structured-fact provenance; and a year/metric comparison matrix.

Use Server-Sent Events for coalesced high-level updates and bounded polling fallback. Never render more than 100 repeated records initially. Provider payloads, complete text, and raw JSON load only on demand.

## 12. Storage and performance

Use normalized tables for runs, stages, filings, outline sections, scores, exploration actions, chunks/ranges, findings, structured facts, comparisons, and high-level events. Store one raw HTML blob and one canonical-document blob per filing. Store chunks as ranges, not duplicated text. Compress large diagnostic provider payloads.

Reuse one HTTP client/connection pool per provider run. Add provider-aware bounded concurrency only for independent scoring batches. Cache outline/scores by sanitized source/range hash, prompt/question version, pinned actual model, and relevant configuration. Batch database writes and index run/stage/item/sequence lookup paths. Resume from the persisted checkpoint without repeating completed paid calls.

## 13. Reuse and deletion

Reuse compatible SEC, provider, settings, redaction, Decimal, validation, and orchestration utilities. Replace V1 flat chunking/screening, extraction fallback, reconciliation, calculations/reporting, file-per-cell/attempt persistence, and unbounded artifact/trace views. Delete obsolete code only after its V2 replacement is functional and tested; do not add compatibility wrappers.

## 14. Testing and manual verification

For every task, inspect and time affected tests first; delete or consolidate obsolete, redundant, mock-heavy, and implementation-detail tests. Prefer one focused invariant test and one integration path. Use saved real SEC filings and recorded real provider responses with provenance; use synthetic fixtures only for narrow controlled failures.

Do not run browser automation. End each task with manual verification instructions: command, URL/click path, exact observations, and unresolved live checks. Run the full suite only for shared infrastructure, cleanup, and final gates.

## 15. Context-bound evidence

Outline generation also identifies a bounded set of source-validated evidence
context bindings. A binding associates a possible evidence range with the exact
visible ranges that establish its title/heading, period header, scale/unit, or
continuation notice. It is not a generated financial assertion. Bindings are
validated against the numbered outline window, reconciled across overlaps, and
stored independently of chunks. This source-range representation must work for
ordinary tables, div/span pseudo-tables, and prose; DOM structure may guide
candidate generation but is never a prerequisite.

Findings requests resolve bindings only for retained chunk cores and render exact
context separately from exact evidence. A model may normalize a number only when
the visible source supports the necessary attribution; otherwise it must preserve
the ambiguity. Company Facts and evaluation output remain unavailable.

## 16. Benchmark

Split immutable development and held-out samples by company/accession. Maintain reviewed source ranges for relevant evidence, misleading quarterly/segment/non-GAAP values, explanations, comparability passages, and irrelevant sections. Compare keep-all, keyword, structural, Jev section, and Jev section-plus-chunk strategies.

Report relevant-range recall, structured-fact coverage, exact value accuracy, recall at retained-source budget, source percentage explored, calls, usage, latency, and time to first match. Gold ranges and structured facts never enter Jev requests. Initial held-out targets are at least 95% relevant-range recall, 100% required-fact coverage, and no wrong selected metric/year values; report failure honestly when unmet.

## 17. Definition of done

- A fresh V2 run works with real SEC documents and configured real providers.
- The UI updates during every stage and survives refresh/cancel/resume.
- Jev requests contain only sanitized visible content and navigation metadata.
- Every published finding contains an exact source-validated quote.
- Structured facts load only after discovery and never repair it.
- Evaluation visibly reports matches, misses, efficiency, latency, and usage.
- No primary view is an unbounded artifact dump.
- Obsolete V1 execution paths and tests are removed.
- Manual verification instructions let the user inspect a complete run without browser automation by the agent.
