# Pipeline UI work

T48–T59 are DONE; their implementation scopes are archived in
[PIPELINE_UI_COMPLETED_TASKS.md](PIPELINE_UI_COMPLETED_TASKS.md). The active
[design brief](PIPELINE_PAGE_DESIGN.md) owns durable UI decisions, and
[PROGRESS.md](PROGRESS.md) records implementation evidence.

**T60 — DONE.** Automated gates passed, and the user confirmed the remaining UI
verification on 2026-10-13. Detailed visual observations were not supplied.

**T61–T63 — DONE; T64 — TODO.** The user requested fact source lines in evaluation results
for debugging. These tasks include backend provenance acquisition and mapping;
statement row numbers alone do not satisfy the requested canonical-line links.
T61–T63 implementation and automated gates are complete. The user confirmed the T63 UI review on 2026-10-14; detailed observations were not supplied. T61–T62 manual visual reviews remain pending.

| Task | Result | Depends on | Status |
| --- | --- | --- | --- |
| T61 | SEC statement/report/row provenance for selected facts | Existing Facts stage | DONE |
| T62 | Verified mapping from fact occurrences to canonical filing lines | T61 | DONE |
| T63 | Fact source lines, quotes, and links in evaluation cards and Facts inspection | T62 | DONE |
| T64 | Real-filing acceptance of fact source debugging | T63 | TODO |

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

**Status:** TODO. **Dependency:** T63.

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
