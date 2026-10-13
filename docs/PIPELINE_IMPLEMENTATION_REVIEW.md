# Pipeline implementation review

Reviewed 2026-10-01 at commit `399cc8d`. Scope: explanation of the backend flow,
visual composition, shared model ownership, and implementation follow-ups.
No application code was changed. Replay is outside this review's implementation scope.

The page has a useful inspection foundation, but its visual structure explains
stage names more effectively than it explains how data changes. The next iteration
should use a consistent visual vocabulary with different compositions for loops,
partitioning, selection, validation, and comparison. It should also finish the move
from hand-authored descriptions of contracts to representations of actual runtime
contracts.

The completed implementation scopes are archived in
[PIPELINE_UI_COMPLETED_TASKS.md](PIPELINE_UI_COMPLETED_TASKS.md); T60's closure and
verification record are in [PIPELINE_IMPROVEMENT_TASKS.md](PIPELINE_IMPROVEMENT_TASKS.md).

## Evidence and limits

Reviewed the design brief, reorganization plan, task gates, orchestration, all eight
stage services, shared contracts, repository access, route context, template, styles,
and stage interaction/live-progress scripts. References below are repository paths
and symbols at the reviewed commit.

`uv run pytest tests/task_gates/test_pipeline_ui_session1.py -q`: **6 passed in 1.44s**,
with one existing Starlette/AnyIO deprecation warning. These tests validate route
content and selected source strings; they do not execute browser interactions.
No provider calls or pipeline runs were started. The initial worktree was clean.
Browser inspection was unavailable. Layout and interaction findings below are based
on code; exact appearance, clipping, contrast, and usability need manual verification.

## What to preserve

- Clear separation between visible filing discovery and independent Company Facts.
  Facts requires completed Findings, and Evaluate is the comparison boundary.
- Real Pydantic domain contracts, including source identity, ranges, exact Decimal
  values, findings, and comparison states.
- Outline's shared prompt template and typed representative objects; Sections'
  `JevVisibleContext.model_json_schema()` and shared target questions.
- Persisted stage status, accounting, source links, detailed stage routes, and
  sanitized trace inspection.
- Keyboard-reachable stations, directional connectors, reduced-motion styles,
  and the editorial intent of an explanation that works without interaction.
- FastAPI/Jinja and small browser enhancements. This work does not require a new
  frontend framework, graph editor, or layout engine.

## Findings, in priority order

### R1 — Shared anatomy has become a repeated diagram, rather than a visual language

**High impact.** Source, Sections, Chunks, and Evidence use the same three vertically
stacked rectangles in a `720 × 660` SVG. Findings and Facts extend that pattern to
five and four rectangles. Evidence, Findings, Facts, and Evaluate reuse
`chunks-stage-explainer` and related classes. Changing labels and accents cannot
communicate the difference between selecting records, splitting ranges, validating
citations, and comparing two independent datasets.

The workspace already expands to 88rem. Each stage still reserves a diagram column
and an inspector column, while many station SVGs use only a central strip. This is
space allocated to containers rather than relationships. Outline additionally hides
its inspector on initialization, leaving its reserved column without initial content.

**Recommendation:** retain typography, spacing, status placement, inspector behavior,
and semantic styles; let each stage arrange objects around its actual operation.
Use width for parallel inputs, before/after objects, source-range bands, and separate
outcomes. Allow content-driven heights. Avoid eight new decorative themes.

Evidence: [workspace template](../src/profitlab/web/templates/v2_workspace.html),
[pipeline styles](../src/profitlab/web/static/pipeline-map.css),
[Outline script](../src/profitlab/web/static/outline-loop.js).

### R2 — Some diagrams contradict the backend's sequence and branching

**High impact.** An educational page must preserve distinctions that matter to
understanding the result:

| Area | What the implementation does | What the current presentation loses |
| --- | --- | --- |
| Outline | Validates each window, carries the last eight accepted proposals into the next request, then deduplicates and partitions the whole document after the window loop. | `Window → Propose → Validate → Reconcile → Window` implies final reconciliation and persisted sections are produced within each iteration. |
| Sections / Evidence | Records selected, uncertain, and skipped decisions. Only selected sections feed chunking; only selected chunks feed findings extraction. | A single outgoing arrow and “bounded uncertainty” copy can imply uncertain items also continue downstream. |
| Chunks | Partitions core coverage and separately attaches preceding context ranges. | Three process boxes do not show why overlapping context is not duplicate evidence. |
| Findings | Builds bounded context, may fall back, validates proposals, may make one repair request, deduplicates, classifies or reuses cached types, then persists. | Five unconditional boxes omit the repair branch and put deduplication conceptually at publication, after classification. |
| Facts | Uses filing identity to fetch SEC data after the findings completion gate. Finding values are not normalization inputs. | “How sealed discovery becomes an independent SEC comparison input” and “Accepts sealed findings” blur a scheduling gate with data transformation. |
| Evaluate | Saves deterministic results; only bounded eligible value/unit mismatches enter optional scale verification. Exact and other ineligible results bypass that request. | `Pair → Compare → Verify → Record` has no visible bypass and overstates the model's role. |

Outline also creates an unlabeled coverage range when a starting boundary is missing;
its inspector's “uncertain gaps ... instead of being silently assigned” needs to
explain this warned partitioning precisely. The generated `parent_topic_hint` is
used in Evidence's heading path alongside an exact source title, while its inspection
descriptor says “exact visible headings only.” Generated navigation and exact text
must remain distinguishable everywhere.

**Recommendation:** show the real branches, gates, and finalization boundaries. Do
not change pipeline behavior merely to make an existing diagram true. Findings'
repair branch currently replaces the candidate list; do not illustrate it as merging
repaired proposals into previously accepted findings without a separate backend decision.

Evidence: `OutlineService.build`, `SectionScoringService._policy`,
`V2PipelineService.run`, `SourceRangeChunker.build`, `ChunkScoringService._descriptor`
and `_policy`, `FindingsService.build`, `CompanyFactsService.load`, and
`EvaluationService.compare_with_scale_verdicts` in [v2](../src/profitlab/v2).

### R3 — Backend ownership is partial; a Python dictionary can still be a duplicate schema

**High impact.** Keeping inspector data on the server is necessary but insufficient.
Several inspector methods independently describe the objects that runtime code builds.

| Stage | Existing reuse | Remaining duplication or missing contract |
| --- | --- | --- |
| Source | Actual filing and canonical reference supply accounting. | Transformation narrative is in JavaScript; canonical object contracts are not exposed as such. |
| Outline | `OutlineProposal`, `OutlineContinuation`, `OutlineSection`, and `SourceRange` produce examples; prompt view shares the request template. | JS contains literal line bounds, overlap, response fallback, and abbreviated fake field names such as `title/start/end`. Window/diagnostic wrappers and prompt field lists remain handwritten. |
| Sections | Schema comes from the same `JevVisibleContext` used at runtime; questions use `TARGETS`. | Inspector request is assembled separately from `_request`; schema is placed where a sample instance would normally sit. JS fallbacks hardcode five questions and preview limits. |
| Chunks | Settings and real `TextChunk` instances supply bounds and counts. | Inspector lists five `TextChunk` fields by hand, omitting neighbor links and schema version. |
| Evidence | Settings and `TARGETS` are shared. | Inspection descriptor and `_descriptor` build separate dictionaries; no shared typed descriptor. |
| Findings | Uses current settings and persisted summary. | Proposal description is a handwritten dictionary separate from `_prompt` and `_validate`; published `Finding` is not the proposal shape. |
| Facts | Uses `FACT_TARGETS` and persisted accounting. | Output description does not derive from `StructuredFact`; policy narrative is manually maintained. |
| Evaluate | Uses settings and summary. | Output descriptions do not derive from `FactComparison`; request explanation is separate from `_request`. |

**Recommendation:** use existing runtime classes directly for schemas and serialized
instances. Where a meaningful runtime boundary only has a dictionary, introduce a
typed contract used by that runtime path and the inspector together. Avoid UI-only
lookalikes of `TextChunk`, `Finding`, or `StructuredFact`.

In this Python/Jinja application, “same class” means Python owns the class and sends
its schema/serialized instance to the browser. It does not require recreating the
class in JavaScript. A generic object renderer can reveal new safe fields without
a frontend schema edit; specialized visuals can continue to highlight stable concepts.

Evidence: the seven `inspection_view` methods; [contracts](../src/profitlab/v2/contracts.py);
[route context](../src/profitlab/web/app.py); stage scripts in [static](../src/profitlab/web/static).

### R4 — Several provider inspectors show summaries rather than the actual request

**High impact.** Outline exposes its real system instruction and safe prompt template.
Findings exposes request limits and a short source rule, but not the actual extraction
prompt, repair variant, or type-classification request. Evaluate shows a paraphrased
rule without the actual `NoulQuestion` instruction. Sections and Evidence share target
text but reconstruct a partial request description outside their request builders.

**Recommendation:** generate safe illustrative requests through the same pure builders
used for real calls. Show instruction text, bounded input structure, returned contract,
and deterministic selection separately. Do not include credentials or transport noise.
Distinguish current configured instructions from the instructions used by a historical
run; the route currently combines current `Settings` with persisted run artifacts.

Evidence: `OutlineService.prompt_view`, `SectionScoringService._request`,
`ChunkScoringService._request`, `FindingsService._prompt`, `_live`,
`_classification_request`, and `EvaluationService._request` versus their inspector methods.

### R5 — Live state updates no longer match the expanded-card DOM

**High impact for trust.** `v2-progress.js` updates individual statuses and the summary
count, but does not update `data-current-stage`, `data-map-run-status`, or the overview's
own completed count. Its timer calls `duration.closest('[data-stage-card]')`; expanded
cards put that attribute on a header link, while the duration is in a sibling footer.
Consequently the per-tick elapsed update cannot find its active card. The active CSS
treatment is also scoped to `.pipeline-card`, which expanded header links do not use.

Stage accounting and embedded inspection JSON come from the initial response and
are not refreshed by the state endpoint, which returns only run and stage snapshots.
A page opened before completion can show completed status alongside stale counters.
`stopLiveUpdates` does not close the EventSource; a terminal disconnect can start
fallback polling again. These are code-path findings, not browser reproductions.

**Recommendation:** establish one stage root and one state-application path for
server rendering and updates. Refresh bounded persisted accounting at stage completion;
do not reconstruct business policy in JS. Make terminal cleanup cover the connection,
timers, scheduled work, and fallback behavior. Keep this work separate from replay.

Evidence: [progress script](../src/profitlab/web/static/v2-progress.js), workspace
template, `V2Repository.state`, and `create_app.events`.

### R6 — Unknown values, examples, and actual run data need explicit identity

**Medium impact.** Several inspector methods replace absent summaries with `{}` and
render zero counts. Queued Facts can therefore display zero supported facts in the
same form as a completed run that found none. Examples and current configuration
appear next to persisted accounting without a consistent distinction. Outline's
browser example uses lines 841–1740 while its backend window example starts at 1.

**Recommendation:** represent availability explicitly: pending, available (including
zero), unavailable, or incomplete. Mark illustrative values as examples and account
for actual results only when persisted. Label current configuration when the original
run configuration is not available. Preserve Decimal strings, nulls, source IDs, and
source hashes when displaying real objects.

### R7 — Fixed SVG text and duplicated rendering create avoidable layout risk

**Medium impact.** Outline sets its mobile viewBox to x=180..540 while routing the return
curve through control points at x=666; that path exceeds the declared viewBox. SVG
overflow styles mean this is an overflow/clipping risk, not a confirmed screenshot
defect. Other stages retain a wide viewBox and small SVG text while imposing mobile
minimum heights, which does not itself prevent text from shrinking with width.

Outline substantially rewrites station size, coordinates, and text in JS after the
server render. Other stage controllers repeat near-identical selection, inspector,
and animation logic. Initial server-rendered inspector prose is separate from the
data used after a click. `card.hidden = true` further makes Outline initialization
inconsistent with other stages. Older map markup remains behind `{% if false %}`,
and styles retain successive layout generations.

**Recommendation:** render stable content initially, allow text to wrap, and use SVG
primarily for geometric relationships. Keep the Outline inline-SVG route, but give
it a deliberately designed readable mobile layout. Share interaction and inspection
primitives without forcing all stages into one layout. Remove verified dead branches
and obsolete styles as part of the relevant refactor.

### R8 — Current tests protect strings, not the main product promises

**Medium impact.** The six pipeline UI gates cover navigation, statuses, Source/Outline
content, and the presence of live-update code. Assertions requiring CSS strings such
as `.outline-architecture` can preserve obsolete implementation details. There is no
gate here proving a backend field addition reaches the inspector, a prompt change
reaches the displayed request, or a conditional path is accurately represented.

**Recommendation:** use focused backend contract/rendering tests and non-browser JS
behavior tests where practical. Follow the repository's task policy of manual UI
verification; record desktop/mobile, keyboard, reduced-motion, and running/terminal
observations. Do not report visual acceptance from source-string tests alone.

## Recommended composition for each stage

Use a compact, always-visible route at the top to orient the reader, then open,
stage-specific explanations below it. The route is a locator, not a second collection
of full-size cards. Keep essential transformations visible without expanding controls.
An inspector adds contracts, instructions, configuration, and provenance.

| Stage | Visual composition | Relationship that must be obvious |
| --- | --- | --- |
| Source | A filing document transforms into numbered canonical lines and a retained source artifact. Compact horizontal before/after on wide screens. | Visible text is preserved; hidden metadata is excluded; downstream stages use retained source. |
| Outline | A source strip shows overlapping windows; the request/validation loop carries accepted navigation forward. A distinct exit produces the finalized partition/outline. | Repeated windows and continuation are different from final reconciliation; generated topics are different from exact lines. |
| Sections | A small descriptor stack enters scoring, then a policy gate branches into selected, uncertain, and skipped groups. | Model scores measure retrieval relevance; deterministic policy decides what continues. |
| Chunks | A source-range ruler becomes adjacent core bands, with hatched preceding-context bands and neighbor links. | Every core range owns coverage; context may repeat without becoming a second owner. |
| Evidence | Chunk tiles with target-score vectors enter a visibly bounded retained set, with separate uncertain/skipped groups. | Coverage, section/year diversity, deduplication, and budget are local selection constraints. |
| Findings | Evidence and navigation enter an assembly area; proposals pass a citation gate. Show one bounded repair branch, deduplication, type classification, and a sealed output tray. | Only source-validated candidates can publish; metadata uncertainty survives; two model roles are distinct. |
| Facts | SEC dataset acquisition sits behind a completion gate, followed by a concept-to-metric mapping and provenance-bearing fact rows. | Findings completion unlocks acquisition, but finding values do not determine facts. |
| Evaluate | Findings and Facts visibly converge into a paired comparison table. A conditional side branch handles eligible scale/unit verification; other outcomes go directly to recording. | Exact comparison is the baseline; optional verification never rewrites either input. |

Keep Facts below Evaluate with an upward data connector under the existing spatial
contract. Distinguish the Findings-complete scheduling gate using a labeled/dashed
relationship or adjacent gate annotation. Supply filing identity to Facts explicitly;
do not draw a discovery-values data arrow into normalization. This is a data-flow
explanation, not a claim that stage execution is concurrent or follows screen order.

A small vocabulary is enough: source artifacts/line strips, processing regions,
decision gates, grouped outcomes, and sealed outputs. Use labels, geometry, and texture
as well as color. Share the muted blue/teal palette; vary geometry according to meaning.
Do not add a workflow canvas, pan/zoom, draggable nodes, or decorative animation.

## Contract ownership and the limit of automatic updates

Use four boundaries:

1. **Runtime contracts:** existing Pydantic classes and any newly typed runtime
   payloads own fields, types, constraints, and serialization.
2. **Request/policy builders:** service-owned functions own prompts, questions,
   effective settings, and eligibility rules. Inspection calls those builders with
   safe examples and no I/O.
3. **Inspection envelope:** a small shared UI envelope identifies the stage/station,
   input/output contract references, schema or instance, example/run provenance,
   availability, explanatory copy, and optional request/policy blocks. This is
   presentation metadata around domain objects, not a second domain schema.
4. **Renderers:** Jinja and a shared browser formatter render the supplied objects.
   Specialized stage compositions arrange stable semantic elements; a generic
   contract/details view handles fields they do not visually emphasize.

Schema and example must be separate. `model_json_schema()` communicates required
fields, optionality, constraints, nested models, and enums. `model_dump(mode='json')`
communicates an instance, preserving Decimal serialization. An example alone cannot
explain every allowed state, and a schema embedded in `state.sections` is not a valid
representative request. Examples must validate against the runtime class and be
clearly illustrative rather than claimed source records.

Automatic propagation should cover added safe fields, updated constraints/enums,
settings, and shared prompt text. New required fields may require updating backend
example factories. A new decision branch or changed business meaning still requires
an editorial/layout change. Do not promise that introspecting a class can infer the
right visual story, or that inspecting code can safely infer all control flow.

Display only explicitly chosen public contracts/projections. A generic renderer must
not automatically expose arbitrary settings or transport objects. If a projection
is necessary for boundedness or redaction, derive it from the actual model and name
the projection; do not silently present an incomplete field list as the full class.

The route currently loads chunks, scores, findings, and Company Facts data while
constructing context for every stage page. After ownership is clarified, load only
the needed page data and bounded summaries. This is a scalability concern inferred
from the reads, not a measured latency claim. Do not add an event-sourcing platform
or persistence migration to solve a presentation problem.

## Replay: preserve options without implementing it

Replay requirements are deliberately undecided. Do not add a playback UI, timeline,
event payload format, per-station recorder, persistence migration, or historical
execution simulator in these tasks.

Useful choices now are stable stage/station identifiers; separate illustrative and
persisted values; preserve existing artifact/source references; and keep rendering
independent of acquisition and mutable DOM state. These are useful to the current
page even if replay is never built.

`PipelineEvent` currently describes stage/run lifecycle changes, with sequence,
status, summary, and timestamp. It does not contain every station's input/output
or transformation. Existing SSE therefore is not a ready-made data replay log.
Existing artifact and version identifiers are useful context, not proof that an
old prompt, intermediate state, or complete execution history is reproducible.

Future decisions include whether replay means historical playback or re-execution,
which granularity matters, data retention/redaction, failed/cached/retried work,
schema evolution, and how missing historical payloads should appear. Leave these open.

## Brief alignment and implementation order

The current [design brief](PIPELINE_PAGE_DESIGN.md) asks expanded stages to reuse
Source/Outline composition and disallows a separate card anatomy. The
[reorganization plan](UI_PIPELINE_REORGANIZATION_PLAN.md) also preserves a shared
desktop card size, while the actual page has grown beyond those cards. The requested
direction needs an explicit documentation update before implementation so future
agents do not faithfully recreate the current limitation.

First align the brief (T48), fix existing state truthfulness (T49), and establish
contract/request ownership (T50–T51). Then share rendering/interaction primitives
(T52), establish the page composition (T53), and implement the stage visuals
(T54–T59). Finish with semantic and manual verification (T60). Detailed scope,
dependencies, and acceptance gates are in the follow-up task document.
