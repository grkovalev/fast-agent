# Pipeline UI work

**Next planned runtime/UI work: T69–T77**, in
[FINDINGS_JEV_IMPLEMENTATION_PLAN.md](FINDINGS_JEV_IMPLEMENTATION_PLAN.md).
These replace Findings discovery with JEV concept/line/context/bundle decisions
and retain the LLM only for selected-bundle conversion. Each task is assigned to a
different fresh-context agent, sequentially. T76 activates the replacement runtime
and its seven-station explanation together. The T65–T68 explanation-only scope
below is completed history and does not constrain this new runtime work.

T48–T59 are DONE; their implementation scopes are archived in
[PIPELINE_UI_COMPLETED_TASKS.md](PIPELINE_UI_COMPLETED_TASKS.md). The active
[design brief](PIPELINE_PAGE_DESIGN.md) owns durable UI decisions, and
[PROGRESS.md](PROGRESS.md) records implementation evidence.

**T60 — DONE.** Automated gates passed, and the user confirmed the remaining UI
verification on 2026-10-13. Detailed visual observations were not supplied.

**T61–T64 — DONE.** The user requested fact source lines in evaluation results
for debugging. These tasks include backend provenance acquisition and mapping;
statement row numbers alone do not satisfy the requested canonical-line links.
T61–T64 implementation and automated gates are complete. The user confirmed the
T63 UI review and T64 cell/year/scale visibility on 2026-10-14; detailed observations
were not supplied. T61–T62 broader manual visual reviews remain pending.

| Task | Result | Depends on | Status |
| --- | --- | --- | --- |
| T61 | SEC statement/report/row provenance for selected facts | Existing Facts stage | DONE |
| T62 | Verified mapping from fact occurrences to canonical filing lines | T61 | DONE |
| T63 | Fact source lines, quotes, and links in evaluation cards and Facts inspection | T62 | DONE |
| T64 | Real-filing acceptance of fact source debugging | T63 | DONE |
| T65 | Shared discovery purpose, target vocabulary, and README explanation | Existing discovery stages | DONE |
| T66 | Clear Source, Outline, and section-selection explanations | T65 | DONE |
| T67 | Clear chunk overlap and evidence-retention explanations | T66 | DONE |
| T68 | Clear extraction cardinality, validation, and finding classification | T67 | DONE |

## T65–T68 execution contract — separate fresh-context agents

These four tasks implement the discovery explanation adjustment agreed on
2026-10-14. Execute each task with a **different agent started with fresh context**;
do not rely on this conversation or another agent's memory. Execute sequentially
in dependency order because templates, inspection builders, and documentation are
shared. Creating this register does not start implementation.

Every agent must read `AGENTS.md`, the execution policy in [TASKS.md](TASKS.md),
[PIPELINE_PAGE_DESIGN.md](PIPELINE_PAGE_DESIGN.md), this execution contract, its
selected task below, and relevant recent [PROGRESS.md](PROGRESS.md) entries. Inspect
the worktree and preserve unrelated changes. Validate every behavior statement
against current runtime code; the checkpoints below describe the planning baseline,
not a replacement for reading code.

The objective is to explain **current behavior**, using copy and small bounded
examples first. Preserve the eight-stage route and existing card compositions;
only T68 anticipates a localized composition addition. Keep Facts, Evaluate,
evaluation results, and benchmark work outside scope. Do not fix runtime discovery
behavior, alter provider prompts/questions, selection policies, budgets, contracts,
storage, or canonical numbering as part of these tasks. Report discovered backend
gaps separately. Presentation wording may change in backend-owned inspection
builders, but the requests they describe must remain unchanged.

Overview and selected-stage inspection must agree. Reuse runtime-owned contracts,
request builders, question sets, and effective settings; do not introduce another
policy implementation or frontend contract model. Distinguish illustrative examples,
current configuration, and saved run data. Important explanations must be visible
without clicking, hovering, or enabling JavaScript.

For each task, mark progress accurately, run directly affected checks and the
repository-required lint/diff checks, and record commands, durations, limitations,
manual verification instructions, and the next task in PROGRESS.md. Follow the
existing no-browser-automation policy and use isolated test storage. Provide wide
and narrow layout, keyboard, no-JS, and 200% zoom review steps where markup changes.
Do not claim manual verification that was not performed. End with a self-contained
handoff and stop; the next task starts in a new agent context. No provider or SEC
calls are needed for this explanatory update.

## T65 — Establish discovery purpose and shared vocabulary

**Status:** DONE. **Dependency:** existing discovery stages.

**Visible result:** the reader understands what discovery seeks before following
its mechanics, and the README uses the same language as the pipeline page.

**Read code:** `v2/section_scoring.py` (`TARGETS`), `v2/chunk_scoring.py`,
`v2/findings_service.py` (type definitions and prompt), `v2/contracts.py` under
`src/profitlab/`. Read `README.md`, `web/templates/v2_workspace.html`, and the
scoring/Findings partials to choose terminology consistent with existing UI.

**Implement:**

1. Add a compact discovery-purpose introduction near the pipeline route. Explain
   three numeric output types: annual profit/net income or loss, diluted EPS, and
   annual diluted weighted-average shares. Explain the five retrieval targets,
   including earnings-change explanations and restatement/comparability passages.
2. Give a short practical reason for each target. Diluted shares is the EPS
   denominator context, not year-end shares outstanding. Earnings change and
   comparability help locate context but have no dedicated published output type.
   Do not describe the rationale as documented historical intent or imply the
   pipeline computes EPS from the other two values.
3. State that findings can retain an unresolved type. Distinguish retrieval
   relevance from financial correctness and from published evidence.
4. Update the README with a concise Source-through-Findings explanation using the
   same vocabulary. Preserve setup and existing Facts/Evaluate documentation.
5. Record this durable terminology in the design brief. Prefer existing styles
   and a compact text/table treatment; do not rebuild stage cards.

**Acceptance:** without opening inspection, a reader can name the three numeric
types, explain why there are five retrieval targets, and understand that explanatory
passages are not separate structured output categories. The README agrees. Labels
are derived from or checked against runtime owners rather than a new policy model.

**Checks:** focused page-render/inspection checks for the target/type distinction,
bounded content, and no provider I/O. Reuse existing gates where possible. Manual:
read the introduction and README, then locate the five targets in Sections/Evidence
and the three types in Findings. Record any stage wording deferred to T66–T68.

**Next:** T66 in a separate fresh-context agent.

## T66 — Clarify Source, Outline, and section selection

**Status:** DONE. **Dependency:** T65.

**Visible result:** the reader can follow primary HTML into a line-addressed topic
map and understand exactly what Jev sees during the single section-selection pass.

**Read code:** `v2/source_service.py`, `sec/service.py`, `v2/canonical.py`,
`v2/outline_service.py`, `v2/section_scoring.py`, and the corresponding path in
`v2/pipeline.py` under `src/profitlab/`. Inspect `web/templates/v2_workspace.html`,
`_pipeline_outline.html`, `_pipeline_scoring.html`, and their inspection builders.

**Implement:**

1. Describe acquisition as the primary supported annual filing HTML through SEC
   discovery. Explain removal of hidden/XBRL metadata while retaining visible text
   inside Inline XBRL wrappers. Show the five canonical element types. Explain
   concisely that selected HTML elements supply numbered lines; sanitized HTML
   may retain additional visible text outside that numbered representation.
2. Preserve the Outline window/validation/continuation/final-partition diagram.
   Add a bounded example of parent topic → child topic → source line range.
   Parent topics are navigation hints on flat stored ranges, not independently
   selected parent objects or an enforced nested hierarchy. Label sample provenance.
3. Explain that validated starts determine the final partition: each final range
   ends before the next boundary, covering every canonical line once. Preserve
   exact-title/quote checks, continuation, and warned unlabeled coverage explanations.
4. Make Sections input explicit: generated topic, exact heading when present,
   first 600 characters, source line count, and filing identity. This is descriptor
   scoring, not full-section scoring or concatenation with a neighboring section.
5. Explain one Jev scoring pass over stored ranges, followed by deterministic
   threshold/target-coverage/count policy. Only selected sections reach Chunks;
   uncertain sections remain inspectable. Preserve the existing scoring composition.
6. Align overview, relevant station inspectors, and selected-stage copy. Update
   the design brief with the descriptor and navigation distinctions where needed.

**Acceptance:** a reader can distinguish overlapping outline windows from the
final non-overlapping section partition, understand parent/child navigation, and
identify the section-scoring payload and policy owner. No two-pass hierarchical
selection, full-section scoring, or complete visible-text coverage is implied.

**Checks:** affected canonical/outline/section inspection and page-render gates;
verify shared scoring markup still explains Evidence correctly. Manual: trace a
bounded outline example, inspect the section request, check source links and the
selected/uncertain/skipped branches at wide and narrow widths.

**Next:** T67 in a separate fresh-context agent.

## T67 — Clarify preceding overlap and evidence retention

**Status:** DONE. **Dependency:** T66.

**Visible result:** the reader understands chunk core ownership, preceding context,
and why only some full-text-scored chunks enter extraction.

**Read code:** `v2/chunking.py`, `v2/chunk_scoring.py`, `v2/section_scoring.py`,
`v2/findings_service.py` (`_request_data`), and chunk orchestration in
`v2/pipeline.py` under `src/profitlab/`. Inspect `_pipeline_chunks.html`,
`_pipeline_scoring.html`, selected-stage copy, and associated inspection builders.

**Implement:**

1. Preserve the current core/context range composition. Emphasize deterministic
   splitting into adjacent core ranges and bounded preceding-line context within
   the same selected section. Avoid following-section or cross-section overlap.
2. Explain ownership and citation separately: repeated context owns no additional
   source coverage and cannot itself supply a finding citation for this chunk.
3. Contrast Evidence with Sections: Jev now reads full exact core plus context,
   with a visible heading path and filing identity, against the same five targets.
   Scores are relevance signals, not calibrated probabilities that a value exists.
4. Explain retention in plain language: thresholds, target coverage, section and
   visible-year diversity, overlap suppression, and count/text limits. Separate
   Jev scores from application decisions. Do not imply year diversity validates
   fiscal periods or that all high-scoring chunks necessarily continue.
5. Keep selected, uncertain, and skipped outcomes clear. Only selected chunks
   enter request assembly; uncertain candidates remain inspectable. Explain that
   Findings has an additional request-size limit, addressed in T68.
6. Align overview and station/selected-stage inspection. Keep actual limits owned
   by settings/builders. Update the design brief if durable clarification is needed.

**Acceptance:** the reader can point to new core versus repeated context, identify
which text is scored and citable, and explain why a high relevance score does not
guarantee downstream retention. Existing range/source/neighbor links still work.

**Checks:** affected chunk/range/policy inspection and rendering gates, including
all three decision outcomes and shared Sections markup. Manual: follow the example
from Chunk 1 to Chunk 2, inspect full scoring input and retention policy, and check
wide/narrow core/context readability without opening an inspector.

**Next:** T68 in a separate fresh-context agent.

## T68 — Explain extraction cardinality and publication guarantees

**Status:** DONE. **Dependency:** T67.

**Visible result:** the reader can follow multiple retained chunks into one bounded
extraction request, then distinguish candidate validation, repair, deduplication,
type classification, and publication.

**Read code:** `v2/findings_service.py` in full, `v2/contracts.py`,
`v2/section_scoring.py`, and Findings orchestration in `v2/pipeline.py` under
`src/profitlab/`. Inspect `_pipeline_findings.html`, `_pipeline_inspector.html`,
selected Findings rendering, relevant CSS/JS, and existing Findings/UI gates.

**Implement:**

1. Add a small bounded composition within the existing Findings card showing
   several retained chunks entering one initial extraction request and zero or
   more candidates per chunk leaving it. Label illustrations; do not fabricate
   historical requests or infer candidate-to-chunk counts absent saved data.
   Preserve the remaining card, station controls, saved results, and route.
2. Correct assembly fallback order: try the full retained set with full outline;
   if too large, pack complete chunks by descending score with full outline;
   if none fits, try the highest-scored chunk with its navigation entry and no
   preceding context; otherwise publish an explicitly limited empty set. Do not
   claim context is reduced before dropping chunks. Explain core CSV evidence
   and separate context without putting serialization mechanics into primary copy.
3. State that the extraction prompt seeks the current fiscal-reporting year,
   while deterministic validation checks chunk reference, core line membership,
   exact single-line quote, finite Decimal, and numeric presence in that quote.
   Do not claim deterministic validation proves year, unit, scale, attribution,
   or consolidated-versus-segment meaning. Unknown metadata can remain unresolved.
4. Keep conditional one-call repair and its replacement semantics explicit:
   the replacement response replaces the whole initial candidate set, including
   initially accepted candidates. Invalid proposals are diagnosed and excluded.
5. Explain deduplication as retaining the first candidate per identical quote
   and amount, not one finding per chunk or a Jev extraction-ranking step.
6. Show Jev's three allowed numeric types. Exactly one type crossing the runtime
   threshold assigns that type; zero or multiple supported types remain unresolved.
   Per-request classification size overflow also retains an unresolved finding.
   Preserve cached-type behavior; do not imply every provider/budget failure is
   gracefully unresolved. Unresolved type alone does not reject a validated finding.
7. Align saved-results labels, selected-stage copy, and inspectors with the above.
   Explain existing validation gaps without changing runtime: references are checked
   against stored chunks rather than strictly the extraction request's retained set;
   period/metadata support and hierarchy are not stronger guarantees than implemented.
   Put detailed limitations in inspection; keep the primary explanation readable.
8. Update the design brief, and finish with a focused Source-through-Findings
   terminology/relationship review across T65–T68. Make only necessary consistency
   fixes within discovery. Do not alter Facts/Evaluate or add a fifth implementation task.

**Acceptance:** without interaction, a reader understands batch extraction,
multiple findings per chunk, deterministic rejection, replacement repair,
quote/amount deduplication, three-type classification, and retained unresolved output.
Inspectors expose the actual guarantees and limits. Saved source/trace/result links
and bounded historical previews remain intact.

**Checks:** affected Findings validation/repair/deduplication/classification and
request-budget/rendering gates; reuse controlled fixtures and existing acceptance
paths without new live runs. Final focused discovery UI checks and lint/diff checks.
Manual: read the combined flow, inspect initial/replacement results where saved,
verify unresolved/empty outcomes and wide/narrow layout, keyboard, no JS, and zoom.
Record unperformed visual checks and any backend follow-ups separately; do not
mark those backend gaps fixed or claim evaluation acceptance.

**Next:** hand off the completed discovery explanation update; no automatic task.

## Shared constraints

- Read [PIPELINE_PAGE_DESIGN.md](PIPELINE_PAGE_DESIGN.md) before UI edits.
  Check any pipeline logic change against the page and selected-stage inspection.
- Preserve backend execution order, outputs, budgets, validation, and independent
  Facts/Evaluate boundaries. Type/refactor runtime payloads without changing their
  wire semantics. Surface discovered backend bugs separately instead of changing
  behavior to fit a drawing.
- Reuse actual domain classes. Shared presentation metadata may wrap domain objects
  but may not duplicate their field definitions or policy implementation.
- Keep replay entirely out of scope. Do not add recording, playback, migrations,
  a graph engine, a frontend framework, or new provider dependencies.
- Initial render must explain the route; clicking only adds inspection. Preserve
  existing selected-stage, exact-source, and sanitized-trace links.
- Keep illustrative contracts and current configuration distinct from persisted
  run data. Missing accounting is not zero; unavailable history is not current config.
- Use focused contract/integration checks. Follow the existing no-browser-automation
  task policy and provide manual UI verification steps with each UI handoff.
- Test pipeline behavior only with isolated test storage; do not start a second app
  against user run storage, where startup recovery can change active run state.
- Record results and limitations in PROGRESS.md. Outstanding required visual
  verification must remain explicit until it is completed.

## T60 — Verify the page's semantic and contract promises

**Result:** one documented acceptance pass covers the assembled page and backend coupling.

**Scope:** relevant existing task gates, focused contract/JS checks, manual checklist,
and PROGRESS.md. Depends on all stage composition tasks.

**Completed local work:** obsolete CSS/source-string assertions were consolidated
into route, contract, and behavior checks. Backend field/constraint and shared
prompt/question propagation, Decimal/range preservation, route branches and gates,
bounded overview loading, and no-provider rendering have focused coverage. The
commands and results are recorded in [PROGRESS.md](PROGRESS.md). No page-speed gain
is claimed without a measured comparison.

**Verification:** the user confirmed the remaining UI review. The individual
checklist observations below were not provided, so they are not claimed here.

**Acceptance:** all eight stages are usable without interaction; inspection is consistent;
running and terminal state agree after refresh; pending, zero, incomplete, example,
current configuration, and persisted data are distinguishable. No frontend contract
field copies or misleading provider paths remain. No replay behavior or storage was added.

**Checks:** focused backend/UI suites plus shared-change checks required by TASKS.md;
`git diff --check`; manual wide/mobile/zoom, keyboard, no JS, reduced motion, long
payloads, and available run states. Ask a reviewer to identify: what each stage accepts
and produces, what gets rejected, what repeats, and where independent facts first meet
findings. Record unresolved visual or comprehension issues as remaining work.

**Closure:** [PROGRESS.md](PROGRESS.md) records the passed checks and user
confirmation. No itemized visual observations are claimed. Replay requirements
remain open.

## T61 — Retain SEC presentation locations for selected facts

**Status:** DONE. Implementation, saved-real-data gates, and live SEC acquisition checks passed; manual UI review remains pending. See [PROGRESS.md](PROGRESS.md).

**Goal:** explain which financial statement and presentation row contains each
selected SEC fact. This is supporting provenance for T62, not an exact filing-line
mapping by itself.

**Implement:**

1. Read the SEC [Financial Statement Data Sets documentation](https://www.sec.gov/files/financial-statement-data-sets.pdf).
   Retrieve and cache the appropriate submission-quarter dataset using the
   filing's filing date; reuse SEC contact, throttling, retry, and size limits.
   Retain dataset URL, content hash, retrieval time, and matching accession.
   Bound archive download, decompression, parsing, and per-run projections; do
   not download or scan a quarterly archive from a page-render handler.
2. Select `PRE` rows by filing accession (`adsh`) and exact concept identity
   (`tag`, `version`/taxonomy). Join numeric records only with the correct period,
   duration, unit, value, and entity/dimensional context where supplied. Handle
   taxonomy-version differences explicitly. A name or amount alone is insufficient.
3. Retain all applicable locations: report number, statement type, presentation
   `line`, filer label, and available report link. One tag can occur in several
   statements; a presentation row may contain values for several periods. Do not
   collapse these into one invented origin. Validate rendered-report links against
   available filing metadata rather than guessing a file extension.
4. Add runtime-owned typed provenance contracts and persistence, associated with
   stable fact IDs. Keep Company Facts as the source of normalized comparator
   values. Presentation enrichment runs only after Findings is sealed and does
   not alter fact selection, Decimal values, comparison outcomes, or provider inputs.
5. Distinguish matched, ambiguous, missing, and retrieval-failed provenance. An
   unavailable enrichment dataset must not erase a valid Company Facts comparator
   or prevent its evaluation. Follow the repository's fresh-schema policy if a
   storage change is necessary; this task does not authorize deleting user data.

**Acceptance:** each enriched fact retains its independently verifiable SEC
statement locations and dataset provenance. `PRE.line` is explicitly a presentation
row number. Missing enrichment has a reason, not a made-up row or measured zero.

**Checks:** saved real SEC `PRE`/`NUM` data covering repeated concepts, comparative
periods, taxonomy versions, and duplicates; controlled missing/download-failure
cases; focused persistence and no-provider/page-render checks. Update Facts
inspection and the design brief in this task if its implemented explanation changes.

## T62 — Map fact occurrences to exact canonical filing lines

**Status:** DONE. **Dependency:** T61. Automated gates and live primary-HTML acquisition passed; manual T62 UI review remains pending. See [PROGRESS.md](PROGRESS.md).

**Goal:** a fact can identify verified visible line(s) in the retained filing,
with the original numeric cell and enough context to debug period and scale.

**Implement:**

1. Read the retained original filing HTML in the post-Findings provenance path.
   Inspect Inline XBRL fact elements, concept, context/period/entity/dimensions,
   unit, numeric format, sign, scale, and continuations. Match those occurrences
   to the selected fact using exact Decimal semantics. Any display transformation
   is recorded as provenance; it does not change the stored comparator value.
2. Map each verified visible occurrence to the existing canonical line and
   sanitized HTML anchor. Canonicalization currently removes XBRL wrappers and
   metadata, so raw-DOM paths cannot be assumed to equal sanitized-DOM paths.
   Establish a reproducible structural mapping and verify the rendered text.
   Preserve canonical numbering, source hashes, visible text, and existing finding
   links; reject a mapping when the retained raw and canonical sources disagree.
3. Persist a separate fact-source location contract with fact ID, document/hash,
   `SourceRange`, visible quote, numeric cell locator when available, relevant
   period/scale header context, mapping method/version, and SEC presentation
   references. Keep all verified occurrences, with bounded reader projections.
4. Separate verified, ambiguous, hidden-only, and unavailable source mappings with
   diagnostics. Missing `PRE` enrichment need not prevent a verified Inline XBRL
   match. Standalone XBRL or a separate rendered SEC report may supply a statement
   link without supplying a line in the canonical primary filing; label that case.
   Never treat a matching number or `PRE.line` as a verified canonical source line.
5. Keep this index outside Source/Outline/Sections/Chunks/Evidence/Findings inputs.
   Hidden XBRL metadata must not leak into canonical visible lines or discovery
   provider requests. Provenance enrichment must not become a recovery path for
   missing findings or input to scale/unit verification.

**Acceptance:** an exact source link resolves to a canonical line whose visible
cell, period/context, and recorded scale explain the independently selected fact.
Repeated appearances remain distinguishable. A hidden or unresolved occurrence
never receives a fabricated visible line. Existing discovery and evaluation outputs
remain unchanged apart from added diagnostic provenance.

**Checks:** saved real retained HTML plus matching SEC data for scaled amounts,
EPS/shares, comparative columns, repeated statements, and sign/format handling;
controlled hidden-only and source-hash mismatch cases. Check canonical-line and
source-anchor stability, Decimal preservation, post-Findings ordering, and absence
of new XBRL/provenance fields in discovery and verification requests. Update affected
Facts/Source inspection explanations in the same implementation task.

## T63 — Show fact source lines in evaluation results

**Status:** DONE. Implementation and automated gates passed; the user confirmed the UI review on 2026-10-14. Detailed observations were not supplied. **Dependency:** T62. See [PROGRESS.md](PROGRESS.md).

**Goal:** from an evaluation card, the user can inspect both the finding's cited
line and the independent fact's verified source line(s) to understand a mismatch.

**Implement:**

1. Extend the backend evaluation-card projection with persisted fact-source
   locations. Load by linked fact IDs, including facts outside the current storage
   page; bound previews and provide access to all saved locations.
2. In each comparator's provenance details show canonical line number/range,
   visible row quote, relevant year/unit/scale context, and an **Open fact source**
   link using the existing sanitized-source route. Clearly distinguish fact
   locations from finding citations and SEC statement/presentation row numbers.
3. Show each applicable statement occurrence, mapping status/method, and diagnostics.
   A missing-finding evaluation must still expose the independent fact's source.
   Ambiguous/unavailable/hidden-only cases show their reason and available SEC
   report link; comparisons without a fact do not invent a fact-source panel.
4. Add the same persisted locations to the selected Facts stage and its relevant
   station inspectors. Label historical runs without saved mappings as unavailable;
   do not recompute provenance or fetch SEC data during rendering. Update the Facts
   and Evaluate explanations and durable design brief to describe the implemented
   provenance flow without implying a new input to discovery or verification.

**Acceptance:** the user can follow an evaluation fact to its exact visible filing
line in one action when verified, compare it with the finding citation, and understand
why a source link is absent otherwise. SEC presentation row and canonical line remain
explicitly separate. Comparison states and provider verdicts are unchanged.

**Checks:** route/integration gates for exact match, mismatch, missing finding,
multiple locations, unavailable historical provenance, and cross-page linked facts;
bounded payloads, source links, and no I/O/provider calls while rendering. Manual
review on the existing UI at wide and phone widths, keyboard, no JS, and 200% zoom.

## T64 — Verify fact source debugging on real filings

**Status:** DONE. **Dependency:** T63. Two-company saved-real-data automated acceptance passed; the user confirmed cell, year and scale visibility on 2026-10-14. No itemized visual observations were supplied. See [PROGRESS.md](PROGRESS.md) for evidence and the caption-preview limitation.

**Goal:** prove that evaluation source links identify the facts users need to debug,
not merely matching numbers somewhere in a filing.

**Acceptance pass:** use saved real SEC filings/datasets for at least two companies
with different statement layouts. Cover annual net income, diluted EPS, and diluted
shares; scaled amounts, repeated concepts, comparative years, an evaluation mismatch,
and a missing finding. Verify every shown fact location against its concept,
period/entity context, visible cell, and scale. Include an unavailable or ambiguous
mapping and confirm the UI explains it. A rendered report link alone does not close
the canonical-line acceptance requirement.

**Checks and handoff:** run focused provenance/UI gates and the shared storage/
orchestration checks required by TASKS.md. Record actual fixture URLs/hashes,
mapping coverage and unresolved cases, commands/results, live SEC status when
configured, and manual UI observations in PROGRESS.md. Do not claim live validation
from saved-data tests. Close only after exact line links and all unavailable states
are verified; document remaining limitations without silently guessing locations.
