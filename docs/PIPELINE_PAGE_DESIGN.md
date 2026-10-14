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
| Facts | Findings-complete gate plus filing identity → independent Company Facts → configured concept mapping and value checkpoint → bounded SEC presentation enrichment and retained-HTML source verification → normalized fact rows with separate provenance diagnostics. | Company Facts supplies comparator values; optional presentation provenance cannot change them or block evaluation. |
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

Each Findings station opens its saved result for the current run above the
contract explanation. Record the assembled request, initial and replacement
proposals, initial and final validation diagnostics with deduplicated candidates,
classified findings, and sealed output as each step finishes. A request with no
fitting evidence records skipped extraction, validation, and classification plus
an empty sealed output. Keep these results separate from illustrative requests
and current configuration. Older runs may expose their saved request and final
findings; label missing intermediate results explicitly instead of reconstructing
them. Preview at most 20 entries per list with bounded text and total payload size,
and link to saved diagnostics or the paginated published findings. The selected
Findings stage also exposes the five results as expandable sections.
Extraction request core evidence uses a CSV string with `line_number,text`
columns per retained chunk; CSV quoting preserves the visible text exactly.
Context and classifier input keep their separate structures. Request budgeting
measures the serialized CSV payload; evidence-character accounting still counts
the visible text rather than CSV headers or quoting.

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

## Keeping the explanation in sync

When pipeline logic changes, review the initial page and the affected selected-stage
inspector against the actual service and orchestration paths. Check the stage's
inputs and outputs, operation order, loops, conditional branches, rejection and
fallback paths, selection rules and budgets, scheduling gates versus data movement,
and persisted state/accounting. Also check whether prompts, effective settings,
contracts, examples, source/provenance links, and comparison outcomes remain accurate.
Update visible explanatory copy and geometry when behavior changes; schema and
request-builder propagation alone cannot explain a new branch or changed policy.

Keep the explanation anchored to runtime contracts and request builders. Label
illustrative examples, current configuration, and historical run data distinctly.
For a logic change that needs no UI edit, record the reason in the task handoff so
the review is explicit. Run focused checks for affected routes and contracts and
inspect the changed composition at wide and narrow widths when UI markup changes.

For Outline specifically, the Window inspector shows prior continuation and
effective window/overlap behavior; Propose shows the shared system instruction,
safe user prompt, and returned proposal contract; Validate shows exact source-match
checks and rejection diagnostics; Reconcile shows accepted/rejected proposals,
overlap ownership, continuation, and the distinct final partition. Selecting
Propose opens its provider request directly. Apply the same builder ownership to
Sections, Evidence, Findings, and Evaluate. Deterministic Source, Chunks, and Facts
must not imply provider calls.

## Fact presentation provenance and verified source inspection

T61 retains SEC statement provenance separately from Company Facts comparator
values. The Facts composition adds an Enrich station after normalization, which
checkpoints Company Facts values before enrichment. Enrichment retrieves the
submission-quarter financial statement archive selected by filing date, streams
bounded SUB/NUM/PRE projections, and checks report filenames against the filing
SEC directory index. The Store station represents the completed independent
comparator input and its separate saved inspection diagnostics. All enrichment
starts after Findings seals; Evaluate continues even when enrichment is unavailable.

The Enrich inspector shows current limits and saved status counts separately.
The selected Facts page shows matched, ambiguous, missing, or retrieval-failed
provenance for each fact, up to 20 presentation locations, archive URL/hash/retrieval
time, and validated SEC report links. A separate saved-details page exposes the
bounded retained projection and numeric records without SEC or provider I/O.
Historical facts with no saved provenance remain explicitly unavailable.

PRE.line is presentation row order, never a canonical filing line. The [SEC field definitions](https://www.sec.gov/files/financial-statement-data-sets.pdf)
specify rounded NUM period dates and durations. Join accession, namespace/tag,
taxonomy version, annual period bucket, literal unit, exact Decimal, and supplied
entity/dimensional context. Company Facts omits taxonomy year: multiple matching
standard versions stay ambiguous. Do not infer unit conversion (for example NUM
USD versus Company Facts USD/shares). PRE does not associate each report row with
a specific numeric cell/context; retain all matching concept presentations as
supporting provenance, not verified visible fact occurrences.

T62 adds a separate `FactSourceMapping` keyed by stable fact ID after presentation
enrichment. It reads retained original HTML without another SEC request, checks
Inline XBRL concept namespace, consolidated dimensionless entity, exact start/end
period, literal unit, and exact transformed Decimal. The bounded dot/comma-decimal
and zero transforms record format namespace, sign, scale, display text, and value.
Unsupported transformations or numeric continuation attributes remain unresolved.

Before sanitization the mapper retains surviving line/cell node identity; the shared
canonicalizer then regenerates the complete canonical document and sanitized HTML.
Both must equal the retained artifacts byte/text-for-text, including the raw source
hash. It verifies the visible numeric cell against its canonical quote and records
a `SourceRange`, line anchor, raw occurrence path, sanitized cell path, and nearby
visible period/scale rows. Hidden exact occurrences never receive visible links.
All verified repeated occurrences remain separate. Missing PRE does not prevent an
Inline match; PRE references remain supporting concept presentations rather than
numeric-cell coordinates.

Limits are 50 MB retained HTML, 100,000 scanned Inline numeric occurrences, 1,000
locations per fact, and 4 MB for the run projection. A limit or source disagreement
produces diagnostics rather than a claimed partial index. Status is verified,
ambiguous, hidden-only, or unavailable. The Facts Enrich/Store explanations now
include this second inspection step. Selected Facts rows show saved mapping status
and occurrence count; a separate saved-mapping page shows 20 locations per page,
quotes, exact source links, transformation details and visible header context.
Historical runs without saved mappings remain unavailable. Rendering never rebuilds
an index or retrieves SEC data.

T63 exposes these saved mappings on evaluation cards, loaded by linked fact IDs
independently of the current Facts storage page. Each verified comparator has a direct
**Open fact source** action to its first sanitized filing occurrence. The expanded
provenance shows up to three occurrences with canonical line/range, visible row quote,
numeric cell, exact period/unit, sign/scale, transformed Decimal, and nearby visible
header context. Quotes/cells are bounded to 1,200 characters, header previews to six
400-character rows, and diagnostics to five 500-character entries; shortened previews
are labeled and link to the paginated full saved mapping. Missing-finding cards still
expose the independent fact's sources; cards without a fact have no fact-source panel.

The selected Facts page keeps the numeric table compact and places the same provenance
in full-width fact sections below it, reached by each row's inspection link. Facts
Enrich/Store and Evaluate Record inspectors link to these saved results without loading
occurrence lists onto the overview. Separate statement details show up to 20 SEC
presentations and validated report links. Presentation rows remain explicitly distinct
from canonical lines. Ambiguous, hidden-only, unavailable, and unsaved historical
mappings show reasons and available statement links without invented visible anchors.
[T64](PIPELINE_IMPROVEMENT_TASKS.md) owns two-company real-filing acceptance. The
user confirmed T63 UI review on 2026-10-14; T61–T62 manual visual review remains
pending.

Presentation enrichment and exact-source mapping run after Findings is sealed and serve inspection only.
Company Facts remains the independent comparator-value source; source-location
metadata must not change discovery inputs, fact selection, comparison outcomes,
or scale/unit verification requests. Page rendering reads saved provenance and
does not fetch or infer a historical mapping.

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
composition introduced in T48–T60. Preserve their useful shared colors, stage navigation,
status/accessibility behavior, selected-stage routes, and the Facts-below-Evaluate
spatial contract. The [review](PIPELINE_IMPLEMENTATION_REVIEW.md) explains the
observed gaps; the [UI task register](PIPELINE_IMPROVEMENT_TASKS.md) records T60's
closure and user-confirmed verification, while
[completed scopes](PIPELINE_UI_COMPLETED_TASKS.md) retain history.
