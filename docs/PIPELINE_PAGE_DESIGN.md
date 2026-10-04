# Pipeline page design brief

## Intent and scope

The pipeline page is an editorial, explorable explanation of how a report is
assembled. It should feel closer to a Seeing Theory explanation than a workflow
editor or application canvas. The initial render must show the route, what each
stage accepts and produces, and the important decisions and repetitions. Selection
adds inspection; it must not be required to understand the main flow.

The page explains the implemented pipeline. Preserve backend stage order, validation,
budgets, outputs, and the independent Facts/Evaluate boundary. Keep the existing
selected-stage URLs, exact-source links, and sanitized trace links. Do not add
recording, playback, migrations, a graph engine, a frontend framework, or provider
dependencies for this page. Replay requirements remain open.

## Shared visual and interaction language

- Use a compact, always-visible route locator with eight recognizable stages, then
  give each stage an open explanation region. The locator establishes position;
  it is not eight more full-size stage cards.
- Share muted blue/teal colors, typography, borders, status treatments, accessible
  selection, accounting, and inspector behavior. Use a small semantic vocabulary:
  source artifacts, operations, decision gates, candidate groups, and persisted
  outputs. Distinguish them with labels, geometry, and texture as well as color.
- Let each stage arrange those elements according to its actual transformation.
  Equal desktop card dimensions and identical internal anatomy are not required.
  Use wide space for inputs, outcomes, and relationships; do not reserve a permanent
  empty inspector column.
- Arrows show data movement and direction. Show scheduling and completion gates
  separately from data inputs. Label a relationship when its meaning would otherwise
  be ambiguous; avoid captions that merely repeat adjacent station titles.
- Avoid a canvas grid, pan/zoom, dragging, minimap, workflow editor, or decorative
  animation. A station may animate its active connector once on selection; respect
  reduced motion.
- Preserve persisted run accounting and state, including partial, failed, cancelled,
  and interrupted outcomes. Pending or unavailable accounting is not a measured
  zero. Label illustrative contracts and examples, current configuration, and
  persisted run data separately. Do not present current configuration as the
  historical request of an old run without evidence.

## The route and its eight compositions

The route runs Source → Outline → Sections → Chunks → Evidence → Findings, then
Facts, then Evaluate. Facts starts only after Findings is sealed. It fetches an
independent SEC dataset using filing identity; finding values do not create facts.
Evaluate alone consumes both findings and facts. Keep Facts physically below
Evaluate and draw its **data** input upward. Show the Findings-complete **scheduling**
gate to Facts separately; the Findings-to-Evaluate data input points downward.
Only Evaluate is a comparison merge. Screen position does not imply that Facts
runs concurrently with Findings.

| Stage | Open explanation composition | Essential meaning before interaction |
| --- | --- | --- |
| Source | Acquisition document → visible-text conversion → numbered canonical lines and retained source. | Downstream work uses addressable visible lines; hidden XBRL metadata is excluded. |
| Outline | Canonical source strip with overlapping windows; a per-window proposal, validation, and continuation loop; a distinct exit to final whole-document partition. | Generated topics are navigation metadata, not source text. A validated continuation is not yet a persisted section. |
| Sections | Visible outline-descriptor stack → provider score vectors → deterministic policy gate → selected, uncertain, and skipped groups. | Scores rank retrieval relevance; only selected sections continue. |
| Chunks | Selected section as a line-addressed band → adjacent core ranges with separate preceding-context bands and neighbor links. | Core ranges own source coverage; overlap repeats context without becoming new coverage. |
| Evidence | Chunk and target tiles → score vectors → bounded retained set, with separate uncertain and skipped groups. | Coverage, diversity, deduplication, and budgets govern what continues. |
| Findings | Evidence and navigation inputs → bounded request → proposal validation, conditional repair/rejection, deduplication, type classification, sealed output. | Every published citation and amount passes validation; uncertainty remains visible; extraction and classification are distinct model roles. |
| Facts | Findings-complete gate plus filing identity → independent SEC dataset → configured concept mapping → normalized fact rows and alternatives. | The gate controls timing; findings do not supply normalization values. |
| Evaluate | Findings and Facts enter a paired comparison → deterministic outcomes; eligible mismatches may visit optional bounded scale/unit verification before recording. | Exact and ineligible outcomes bypass the model; verification does not repair discovery. |

Keep the stage compositions faithful to runtime branches. For example, Outline
validates and carries accepted proposals between windows, then deduplicates and
partitions the entire document *after* the window loop. Its return arrow goes to
the next window; a separate finalization exit leads to persisted sections. Missing
boundaries may produce warned unlabeled coverage. Findings repair is conditional
and bounded, and its candidate replacement semantics must match the service.
Sections and Evidence selection must visibly distinguish selected, uncertain, and
skipped outcomes. Evaluate must show a direct bypass around optional verification.

## Station content and inspection

An explanation region should state representative **accepts**, **does**, and
**outputs** in plain language. Keep concrete transformations, important rejection
paths, and output identity visible without interaction. Use bounded illustrations
where complete run data would overwhelm the page, and label them as illustrations.
Do not show empty placeholder objects or zero counters for unavailable artifacts.

Selecting a station keeps its diagram in place and opens the corresponding inspector
in one action. On wide screens, place inspection material beside the relevant
composition when space allows; on narrow screens, stack it beneath. The inspector
shows the contracts, instructions, effective settings, provenance, source links,
and policy that matter at that station. It is not a second workflow interface.
Keep long text wrapped and structured payloads full width, with bounded vertical
scrolling. Do not squeeze JSON into a definition-list cell or narrow card.

The backend owns inspection content:

- Runtime domain classes own fields, types, constraints, and JSON serialization.
  Reuse actual classes such as `SourceRange`, `TextChunk`, `Finding`, and
  `FactComparison`; do not copy their fields into JavaScript or a UI-only model.
- Service request and policy builders own prompts, questions, effective settings,
  selection rules, and eligibility. Build safe illustrative requests through those
  same builders without provider I/O. Show the instruction, meaningful user input,
  and returned object, not transport details such as `json_object`.
- A small presentation envelope may identify a stage/station, schema or instance,
  input/output references, availability, provenance, and optional request/policy
  sections. Separate schema from a validated illustrative instance and from
  persisted run data. Generic rendering handles safe fields not emphasized in a
  stage composition.
- Expose only explicitly chosen public contracts or bounded projections. Do not
  serialize arbitrary settings, secrets, or unbounded source payloads. Contract
  changes can propagate through schemas and renderers, but changed business logic
  or a new branch still needs an editorial update.

For Outline specifically, the Window inspector shows prior continuation and
effective window/overlap behavior; Propose shows the shared system instruction,
safe user prompt, and returned proposal contract; Validate shows exact source-match
checks and rejection diagnostics; Reconcile shows accepted/rejected proposals,
overlap ownership, continuation, and the distinct final partition. Selecting
Propose opens its provider request directly. Apply the same builder ownership to
Sections, Evidence, Findings, and Evaluate. Deterministic Source, Chunks, and Facts
must not imply provider calls.

## Responsive and accessible reading

At wide widths, use the available width to make the source transformation, loop,
branch, range partition, and comparison legible. At approximately tablet and phone
widths, preserve the same meaningful order and connectors by reflowing compositions,
not by shrinking a desktop SVG until text is illegible. Outline keeps a responsive
inline-SVG loop with a complete visible return path and separate finalization exit.
Facts remains below Evaluate with an understandable upward data relationship.

Keep essential text in the document reading order. Station controls are keyboard
reachable, have useful accessible names and visible focus, and expose selected
state. Pointer, touch, and keyboard selection open the same inspection. Hover and
focus may highlight a station and its connectors, but primary content does not
depend on them. Connector and state contrast must remain sufficient, and flow
animation is disabled under `prefers-reduced-motion`. The page must still explain
the main route with JavaScript disabled and at 200% zoom.

## Relationship to earlier plans

This brief supersedes the equal-size desktop cards, same-card anatomy, permanently
adjacent inspector rail, and literal four-station `Window → Propose → Validate →
Reconcile → Window` interpretation in the earlier
[reorganization plan](UI_PIPELINE_REORGANIZATION_PLAN.md) and this brief's previous
version. Those rules document the T39–T47 implementation history, not the target
composition for T48–T60. Preserve their useful shared colors, stage navigation,
status/accessibility behavior, selected-stage routes, and the Facts-below-Evaluate
spatial contract. The [review](PIPELINE_IMPLEMENTATION_REVIEW.md) explains the
observed gaps; [follow-up tasks](PIPELINE_IMPROVEMENT_TASKS.md) bound implementation.
