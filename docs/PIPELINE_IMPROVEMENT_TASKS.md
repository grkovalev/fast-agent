# Pipeline explanation follow-up tasks

Created 2026-10-01 from [PIPELINE_IMPLEMENTATION_REVIEW.md](PIPELINE_IMPLEMENTATION_REVIEW.md).
T48–T59 are **DONE**; T60 is **IN_PROGRESS**, pending manual visual and comprehension review. This document creates implementation work; no task below
was implemented as part of the review.

These tasks continue after T47. Use [TASKS.md](TASKS.md)'s execution policy, preserve
unrelated changes, and implement one bounded task per session. The explicit
dependencies below identify handoff requirements. Other agents can pick up these
tasks later; this report does not launch implementation agents.

## Shared constraints

- Read [PIPELINE_PAGE_DESIGN.md](PIPELINE_PAGE_DESIGN.md) before UI edits. T48 aligns
  that brief with the requested direction; later tasks follow the amended brief.
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
- Record results and limitations in PROGRESS.md. A task with outstanding required
  visual verification must say so rather than claim fully verified completion.

## Task index

| ID | Priority | Result | Depends on |
| --- | --- | --- | --- |
| T48 | P1 | Design brief permits distinct semantic stage compositions | Review |
| T49 | P1 | Accurate live state and honest accounting availability | T48 |
| T50 | P1 | Inspectors reuse runtime object contracts | T48 |
| T51 | P1 | Provider inspection uses actual request builders | T50 |
| T52 | P1 | Shared inspector and interaction primitives, stable initial render | T50, T51 |
| T53 | P1 | Spacious page hierarchy and truthful data/gate connections | T48, T49, T52 |
| T54 | P2 | Source document-to-lines composition | T53 |
| T55 | P1 | Outline loop and final partition accurately distinguished | T53 |
| T56 | P2 | Sections/Evidence visually separate scoring and retention | T53 |
| T57 | P2 | Chunks explains core ownership and overlap spatially | T53 |
| T58 | P1 | Findings shows validation, repair, typing, and sealing | T53 |
| T59 | P1 | Facts/Evaluate shows independent data and conditional verification | T53 |
| T60 | P1 | Contract propagation and end-to-end explanation acceptance | T54–T59 |

## T48 — Align the durable product brief

**Result:** agents have one coherent explanation-page specification.

**Scope:** `docs/PIPELINE_PAGE_DESIGN.md`, `docs/UI_PIPELINE_REORGANIZATION_PLAN.md`,
and task cross-references. Documentation only.

**Work:** distinguish shared visual tokens, navigation, accounting, and inspector
behavior from stage-specific geometry. Replace equal-card-size/composition rules
with semantic compositions from the review. Reconcile the Outline loop requirement
with actual per-window continuation and post-loop partitioning. Preserve Facts below
Evaluate, the upward data input, and the separate post-Findings scheduling gate.
State which older layout rules are superseded and retain their historical context.

**Acceptance:** one explicit brief covers all eight stage compositions, desktop and
mobile intent, essential no-interaction content, model ownership, and replay exclusions.
It does not require changing backend behavior. Follow-up tasks no longer conflict
with “same anatomy” or fixed desktop card-size requirements.

**Handoff:** identify the amended rules and the next task. No screenshots or application
tests are required for this documentation-only task.

## T49 — Repair live progress and accounting truthfulness

**Result:** status, current stage, accounting, and elapsed time tell the same story.

**Scope:** `web/static/v2-progress.js`, stage-root template markup, relevant styling,
`web/app.py`'s state/view data, and bounded repository summaries if needed.

**Work:** attach stage identity to a stable container that owns its header and footer.
Unify server-rendered and updated status semantics. Update both overall counters,
current stage, run status, active treatment, and accessible state. Refresh persisted
stage accounting on completion without resetting inspector selection. Represent
pending/unavailable/partial accounting separately from a measured zero. Label current
configuration where historical request/configuration evidence is unavailable.
Close SSE and stop timers, delayed work, and fallback polling on terminal state;
handle disconnects and resume through the existing navigation/lifecycle. Preserve
backend timing semantics rather than treating wall time as authoritative active time.

**Acceptance:** a running-to-completed transition updates all displayed state without
reload; the timer finds expanded cards; a terminal disconnect cannot restart polling;
unknown work has no invented percentage; failed/partial/cancelled/interrupted states
remain honest after refresh; zero-output completed stages differ from queued ones.

**Checks:** focused state/render integration and non-browser JS state/timer checks
covering the identified defects. Manual: open an existing run at
`/v2/runs/<run_id>/pipeline`, inspect progress and accounting, disconnect/reconnect,
and compare with a refresh. Use controlled isolated fixtures if the needed state is
not available; state that visual verification remains pending on the live UI.

## T50 — Make contract inspection derive from runtime models

**Result:** changes to displayed backend contracts propagate without frontend field lists.

**Scope:** V2 contracts, stage services' `inspection_view` methods, narrow route context
assembly, and a small shared inspection envelope/serializer.

**Work:** inventory input, proposal, persisted-output, and diagnostic types for each
stage. Reuse `CanonicalDocument`/`CanonicalLine`/`CanonicalDocumentRef`, `SourceRange`,
`OutlineProposal`, `OutlineContinuation`, `OutlineSection`, `JevVisibleContext`,
`TextChunk`, `ScoredItem`, `Finding`, `StructuredFact`, and `FactComparison` directly.
For untyped runtime boundaries such as the Evidence descriptor and Findings proposal,
introduce a contract used by the actual builder/parser as well as inspection. Preserve
existing coercion/rejection behavior or explicitly surface incompatibilities for a
separate decision. Do not create a parallel `UiFinding` or `UiTextChunk`.

Define a minimal envelope for identity, schema/instance kind, input/output references,
provenance, availability, and optional request/policy sections. Separate schemas from
validated illustrative instances. Keep precise JSON serialization and nested models.
Use bounded explicit public projections where needed. Remove handwritten contract
field lists and misleading generated/exact-source labels. Load only the artifacts
needed for the requested page; avoid expanding all source payloads for an overview.

**Acceptance:** all displayed domain contracts have a traceable runtime owner; the
complete `TextChunk` contract includes neighbor links; proposal and persisted finding
shapes stay distinct; optional field/enum/constraint changes appear in generic contract
inspection through backend schema output. Missing values, Decimal strings, nested
ranges, and representative examples retain their meaning. No provider I/O is required
to render inspection, and no arbitrary settings/secrets are serialized.

**Checks:** schema/serialization parity, representative-instance validation, targeted
runtime compatibility tests, and one rendered integration path demonstrating backend
schema propagation. Verify public-field/redaction bounds. Run broader backend checks
if shared parser or storage behavior is touched, per existing task policy.

**Handoff:** list each contract owner, any necessary public projection, and which
business changes still need editorial work. Do not promise fully automatic layouts.

## T51 — Reuse real prompt and request builders

**Result:** a provider inspector explains the actual configured instruction and object.

**Scope:** Outline, Sections, Evidence, Findings extraction/repair/classification,
Evaluation request builders and their inspection adapters. Use existing provider types.

**Work:** expose safe request construction without network calls. Build illustrative
requests through the same functions as runtime requests, with typed synthetic values
or clearly labeled placeholders. Include Outline system/user instructions and response;
Sections/Evidence target questions; Findings initial and repair prompts plus type
classification; Evaluate's exact scale question, rule, and bounded eligibility. Keep
configured model/prompt version distinct from actual recorded model/version. Show
effective settings and local selection policy separately from model decisions.

**Acceptance:** editing a shared prompt/question changes the inspector without a JS
or template edit. Shape examples are valid instances, not JSON schemas masquerading
as provider state. Deterministic Source/Chunks/Facts do not imply model calls.
Inspection has no side effects, exposes no credentials, and does not claim a template
was the exact request sent in an old run without supporting persisted evidence.

**Checks:** request-builder/inspector parity with safe representative inputs, bounded
repair/classification/verification branches, and existing provider contract gates.
Manual: select each provider station and compare the instruction and output contract
against its shared builder output; confirm long values wrap inside the inspector.

## T52 — Share rendering and interaction without imposing one diagram

**Result:** every stage uses consistent inspection and accessible selection, while its
layout remains free to express its own logic.

**Scope:** `v2_workspace.html`, stage scripts, `pipeline-map.css`, reusable Jinja
partials/macros and a small shared browser controller as needed.

**Work:** extract the stage header/accounting frame, schema/instance renderer, inspector,
and selection/highlight/motion behavior. Render initial and selected inspector content
from the same backend envelope. Use local stable stage/station identifiers and scoped
controls; expose selected state accessibly. Replace JSON fallbacks and handwritten
payload strings with explicit unavailable states. Remove JS-driven rewriting of
essential Outline content after load. Keep wrapped text readable and code blocks
full-width with bounded scrolling. Remove proved-dead map branches and superseded
styles while preserving selected-stage pages.

**Acceptance:** new backend fields render in generic details without controller edits;
initial content remains useful with JS disabled; choosing a station takes one action;
keyboard, pointer, and touch activate equivalent inspections; selection does not erase
the diagram; reduced motion disables flow animation. No controller duplicates policy
thresholds, question counts, source examples, or domain field lists.

**Checks:** focused rendering/interaction checks using the current lightweight stack.
Manual: select first/last/provider stations, traverse with keyboard, disable JS, enable
reduced motion, and inspect long nested payloads. Verify no duplicate IDs or inaccessible
controls in the emitted markup. Do not replace string assertions with a new browser
automation dependency.

## T53 — Establish page hierarchy and semantic connections

**Result:** readers can locate the whole flow quickly and use wide space to understand it.

**Scope:** overview route composition, template/partials, styles, and connection metadata.

**Work:** introduce a compact always-visible route locator and stage-specific open
explanation regions. Use wide space for inputs/outcomes rather than a permanent empty
inspector reservation; preserve readable inspector placement where appropriate.
Define common visual styles for source artifacts, operations, decision gates, and
persisted outputs. Show data-flow edges separately from scheduling gates. Keep Facts
below Evaluate with an upward data input; make its filing-identity source and Findings
completion gate explicit. Preserve the existing selected-stage URLs.

**Acceptance:** the page shows eight recognizable stages and only one Findings/Facts
comparison merge; no arrow implies Facts fed discovery or began concurrently. Layout
does not require equal card sizes, collapsed essential content, pan/zoom, or a legend
to identify the main route. On mobile, reading order and connector meaning survive
without reducing essential text to fit a desktop SVG.

**Checks:** route/navigation and semantic relationship checks. Manual: compare wide
desktop, approximately 768px and 390px widths, 200% zoom, long labels, and no interaction.
Record whether the reader can identify what moves forward and where Facts enters.

## T54 — Source: show the document becoming addressable source

**Result:** a document-to-lines composition explains source preservation at a glance.

**Scope:** Source partial/styles and its existing inspection adapter. Depends on T53.

**Work:** replace repeated process rectangles with an acquisition document, visible-text
conversion, and numbered-line/source-reference artifact. Use real backend model names
in inspection and clear source links when data exists. Keep illustrative lines labeled.

**Acceptance:** users can see that retained visible lines, not live HTML or hidden XBRL
metadata, feed downstream work. Source hash, document identity, and line anchors remain
inspectable. Pending acquisition does not look like an empty completed document.

**Checks:** existing Source content/provenance gate, shared renderer checks; manual
desktop/mobile and exact-source navigation. No SEC requests are needed for UI fixtures.

## T55 — Outline: show window iteration and final reconciliation

**Result:** the diagram matches `OutlineService.build` and explains overlapping windows.

**Scope:** Outline partial, responsive inline SVG, inspection content, focused gates.

**Work:** draw overlapping windows against a canonical source strip; distinguish model
proposal, exact validation, accepted continuation, and final whole-document partition.
Keep an unambiguous next-window return and a separate finalization exit. Show warned
unlabeled coverage honestly. Derive bounds, overlap, continuation limits, proposal and
section shapes from backend owners. Preserve direct selection of the LLM request.

**Acceptance:** no final persisted partition is implied inside each window iteration;
generated topics cannot be mistaken for source text; proposal ends and final section
boundaries are distinguishable. All essential text and the complete return path fit
the mobile layout. No JS literal `841–1740`, `overlap: 60`, or fake proposal schema
remains as a competing contract.

**Checks:** Outline service and inspection tests with multiple windows and missing
boundaries; rendered contract/edge checks. Manual: wide/mobile loop, long prompt,
keyboard selection, no-JS route, and reduced-motion behavior.

## T56 — Sections and Evidence: show scoring, policy, and distinct outcomes

**Result:** related retrieval stages share a vocabulary while clearly operating at
different granularity.

**Scope:** Sections/Evidence partials, styles, inspection configuration, focused tests.

**Work:** Sections uses descriptor stacks and a score-to-policy gate. Evidence uses
chunk/target tiles and a bounded retained set that exposes coverage/diversity/budget
constraints. Each has separate selected, uncertain, and skipped destinations. Use
shared components for score vectors and outcomes, but arrange them for each purpose.
Show generated heading context separately from exact visible titles.

**Acceptance:** only selected items have a downstream continuation edge. Uncertain
items are inspectable candidates, not silently promoted inputs. Provider scores are
never called financial correctness probabilities. Actual thresholds, targets, bounds,
and policy explanations come from backend owners. Example scores are labeled.

**Checks:** existing scoring/policy tests and contract-rendering checks for all outcomes.
Manual: compare the two stages side by side in understanding, inspect their actual
question sets, and check responsive grouping and bounded payload display.

## T57 — Chunks: show core coverage and repeated context

**Result:** source-range geometry explains chunking more clearly than process boxes.

**Scope:** Chunks partial/styles and model-derived inspection. Depends on T53.

**Work:** show a selected section as a line-addressed band, partition it into adjacent
core ranges, and attach preceding-context bands with distinct texture/labels. Expose
neighbor links and request-size estimates through the actual `TextChunk` representation.
Use a bounded illustration instead of rendering every chunk in a large run.

**Acceptance:** overlap visually belongs to context and cannot be mistaken for new core
coverage. Atomic source boundaries and deterministic/no-model behavior are explicit.
Actual counts come from persisted artifacts; illustrative range geometry is labeled.

**Checks:** chunking and range invariants, model-render integration. Manual: desktop
and mobile core/context interpretation, long ranges, empty/failed stage, source links.

## T58 — Findings: show validation, bounded repair, and publication

**Result:** readers can follow a proposal into validated, sealed findings or rejection.

**Scope:** Findings partial/styles, inspection content, focused service/UI checks.

**Work:** show evidence versus navigation inputs, request assembly and budget fallback,
proposal validation, one bounded repair branch, rejection diagnostics, deduplication,
type classification/cache reuse, and publication. Distinguish extraction and type
classification model roles. Explain unresolved metadata using the real `Finding` model.
Confirm the repair candidate replacement semantics in current code; do not draw an
accepted-plus-repaired merge that the implementation does not perform.

**Acceptance:** every publication path passes citation/amount validation, only core
lines can supply citations, and Facts is absent from model input. One bounded repair
is visibly conditional. Deduplication precedes classification as implemented. Unresolved
types/periods/units remain visible, and sealed output does not imply every proposal succeeded.

**Checks:** existing finding validation/repair/classification checks and illustrative
request parity. Manual: initial diagram, repair branch, both provider inspectors,
published-object inspection, narrow layout, and keyboard reading order.

## T59 — Facts and Evaluate: show the gate, independent data, and optional verification

**Result:** independent acquisition and the comparison boundary are visually unmistakable.

**Scope:** Facts/Evaluate partials/styles, their inspection adapters, relevant tests.

**Work:** Facts shows its completion gate, filing identity, SEC dataset, configured
concept mapping, normalized fact rows, and alternatives/provenance. Evaluate pairs
two distinct inputs in a comparison layout, records deterministic outcomes, and sends
only eligible bounded mismatches through the optional scale/unit request. Include a
direct bypass to recorded outcomes. Preserve the downward Findings and upward Facts
data connections from T53. Show actual backend comparison states via `FactComparison`.

**Acceptance:** Findings completion is a control gate, not a stream of values used to
manufacture facts. Only Evaluate consumes both datasets for comparison. Exact results
and ineligible/unpaired outcomes do not visually require a model call; zero configured
verification pairs is represented correctly. Outcomes never imply discovery repair.
Actual request question/rule and exact Decimal values remain inspectable.

**Checks:** Facts ordering/normalization and deterministic/conditional evaluation tests,
including verification disabled and no eligible pairs. Manual: understand both input
origins without opening inspectors, follow conditional/bypass paths, inspect provenance,
and verify narrow-screen direction and comparison readability.

## T60 — Verify the page's semantic and contract promises

**Result:** one documented acceptance pass covers the assembled page and backend coupling.

**Scope:** relevant existing task gates, focused contract/JS checks, manual checklist,
and PROGRESS.md. Depends on all stage composition tasks.

**Work:** consolidate obsolete CSS/source-string assertions into meaningful route,
contract, and behavior checks. Verify safe backend field/constraint propagation,
shared prompt/question propagation, serialized Decimal/range preservation, and initial
render versus updates. Validate the route's actual branches/gates against service code.
Check that overview rendering loads bounded content and does not call providers. Record
any measured performance comparison; do not claim a speedup from code inspection alone.

**Acceptance:** all eight stages are usable without interaction; inspection is consistent;
running and terminal state agree after refresh; pending, zero, incomplete, example,
current configuration, and persisted data are distinguishable. No frontend contract
field copies or misleading provider paths remain. No replay behavior or storage was added.

**Checks:** focused backend/UI suites plus shared-change checks required by TASKS.md;
`git diff --check`; manual wide/mobile/zoom, keyboard, no JS, reduced motion, long
payloads, and available run states. Ask a reviewer to identify: what each stage accepts
and produces, what gets rejected, what repeats, and where independent facts first meet
findings. Record unresolved visual or comprehension issues as remaining work.

**Handoff:** list passed checks, actual visual observations, any outstanding verification,
and links to the finished overview and stage routes. Replay requirements remain open.
