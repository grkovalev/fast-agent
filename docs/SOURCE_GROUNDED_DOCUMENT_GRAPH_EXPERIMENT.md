# Source-grounded document graph experiment

**Branch:** `source-grounded-document-graph`  
**Status:** planned; no graph-construction code has been introduced.  
**Decision boundary:** this is a separate experiment, not a replacement for the
active V2 retrieval pipeline.

## Approved direction — model-built semantic evidence graph

This section supersedes the earlier deterministic, layout-oriented construction
route below. Preserve that route as design history only; do not implement its
numeric scanner, table/header rules, anchor heuristics, or document-type-specific
scope rules.

The experiment is a **question-conditioned, model-built semantic evidence graph**.
The only deterministic responsibilities are source identity, request/call budgets,
exact source-span validation, persistence, and graph traversal mechanics. They may
not decide what a table, header, value, scale, claim, or answer is.

The graph is not a knowledge base and a model edge is never truth. Every graph node
and edge must cite one or more exact canonical `SourceRange`s and retain the model,
prompt/configuration version, request, response, status, and uncertainty that
produced it. A generated label is navigational metadata only. An answer can use it
only when the answer fields independently trace to exact visible source spans.

```text
question + immutable canonical source
  -> bounded model exploration actions
  -> source-cited semantic nodes / relationships / uncertainties
  -> bounded graph traversal and targeted expansion
  -> graph-grounded answer with exact source path
```

The generic initial relation vocabulary must stay deliberately small:
`supports`, `qualifies`, `contradicts`, `same_claim`, `narrows`, and `related_to`.
It must not encode financial metrics, tables, rows, cells, headings, units, periods,
or any other document type. Models may propose any of these relationships but must
state exact evidence spans; the application does not infer them from HTML layout.

## Handoff evidence and non-negotiable boundaries

New sessions must read [PROGRESS.md](PROGRESS.md) before implementing a graph task.
The preceding V2 cohort established the following, which motivates this branch but
does not provide graph input or gold labels:

- 15 real reports under `v2-5d00a512aa114aaa` completed all stages. T41 sent 525
  packet cores (345 target-shaped and 180 reserve) with no request-size exclusions.
- 37 first-pass quote-valid findings survived; 31 malformed citation proposals were
  rejected (30 amount/quote disagreements and one non-core citation); three repair
  findings survived. This shows exact source validation is essential but does not
  identify every upstream loss point.
- Current evaluation is not a graph oracle: it conflates some consolidated and
  common-shareholder income targets, has incomplete Company-Facts coverage for some
  reports, and cannot trace a missed fact to a visible source candidate or packet.
- Source-context diagnostics consumed 555 Jev calls in that cohort while not changing
  current retention or Findings inputs. Do not reproduce that unmeasured diagnostic
  pattern in this experiment.

The graph experiment must use a fresh isolated repository under
`data/evidence-graph-experiment/`; it must not migrate, mutate, or become a
prerequisite for the V2 pipeline. Company Facts, reviewed expectations, published
Findings, comparisons, rubrics, and evaluation output remain strictly post-seal and
must never be included in graph-construction or answer-generation provider requests.

## Branch task sequence

Each task is one bounded implementation session. Do not begin a later task until its
acceptance and a recorded inspection are complete. All live work uses a new explicit
application/experiment revision; local contracts never substitute for live evidence.

### G0 — Frozen experiment harness and evidence handoff

Create an experiment-local package, repository namespace, configuration identity,
and CLI/web entry point that accepts a canonical document plus a question. Record an
immutable manifest with source hash, branch commit, model/prompt versions, budgets,
timings, and an `experiment_id`. Add a checked-in reviewed **post-run** fixture format
for graph-path inspection, but do not make it provider input.

**Acceptance:** a saved canonical document can initialize an empty graph experiment;
no V2 row is altered; a manifest and explicit non-leak inventory are inspectable.

### G1 — Source-cited graph contracts and repository

Implement only generic nodes (`EvidenceNode`, `EvidenceEdge`, `ExplorationAction`,
`GraphPath`) and exact source-span provenance. Nodes/edges must be source-hash-bound,
versioned, status-bearing (`accepted`, `uncertain`, `rejected`), and immutable after
persistence. Reject a node/edge whose evidence span does not round-trip exactly from
the canonical document. Do not add layout, value, metric, or document-type contracts.

**Acceptance:** a fixture can persist accepted, uncertain, and rejected model-shaped
nodes/edges; every returned path resolves to exact canonical text; invalid or
cross-document provenance is refused.

### G2 — Bounded model exploration action

For a question and a bounded numbered source window, ask the configured model to
propose generic evidence nodes and relation edges relevant to answering the question.
Every proposal must cite supplied spans and use the small relation vocabulary. The
application validates references mechanically, stores rejected proposals without
their generated answer text being treated as source, and never uses document-type
heuristics to propose candidates. Cache by question fingerprint, source-window hash,
model, prompt, and configuration.

**Acceptance:** a real saved filing and controlled fixture show source-cited accepted
and rejected graph proposals; payload guards prove that facts, findings, evaluation,
and XBRL material cannot enter requests; one malformed response produces explicit
partial/audit state rather than fabricated graph content.

### G3 — Dynamic graph exploration planner

Build a bounded planner that begins with generic source windows, follows only
accepted/uncertain graph relationships, and asks the model for a limited number of
next exploration windows when evidence is insufficient. It must record why each
window was explored, the parent node/edge path, call/token/time budgets, and explicit
frontier exhaustion. It may not use a deterministic table/heading/row policy or a
top-N financial-target gate.

**Acceptance:** the explorer renders a reproducible frontier/path trace, cannot
revisit an equivalent window indefinitely, respects every budget, and makes no claim
when the graph lacks sufficient cited support.

### G4 — Graph explorer UI and inspection workflow

Add an experiment-only workspace: start from a question, source line, node, edge, or
answer candidate; expand one provenance path at a time; open every cited canonical
line; distinguish model inference from immutable source; and show rejected/uncertain
edges without promoting them. Provide request, timing, cache, and budget inspection.

**Acceptance:** a reviewer can answer “why was this line explored?”, “what source
supports this relationship?”, and “where did exploration stop?” without reading raw
database rows or provider payloads.

### G5 — Graph-grounded answer candidate and exact validation

Ask the model to synthesize an answer only from a bounded selected graph subgraph.
The response must attach each material field and claim to cited source spans and graph
paths. Reuse exact quote/Decimal validation where applicable, but do not assume a
financial-value schema; unsupported fields remain unresolved. Persist answer
candidates separately from V2 Findings.

**Acceptance:** invalid citations/paths cannot publish; a valid answer renders its
full source path; an uncertain or conflicting graph returns an explicitly limited
answer rather than a forced conclusion.

### G6 — Generic source-grounded evaluation

The first post-seal step is not a method comparison. Define one generic, versioned
evaluation protocol for a development cohort of distinct filings: the question family,
model, prompt, relation vocabulary, traversal budgets, and stopping rules are fixed
before that cohort runs. Each run receives only its canonical SEC source and question.
SEC ground truth is attached only after the run for scoring; it is never graph input,
provider input, or a source of per-filing retrieval rules.

Measure required-ground-truth coverage, exact citation validity, answer support and
limitation behavior, explored ranges, continuation reasons, terminal frontier state,
provider calls/tokens, and latency. The explorer and persisted action trace are the
diagnostic surface when a run misses required evidence. Diagnose source coverage,
path construction, answer synthesis, and budget exhaustion separately; do not add
financial, table, heading, layout, ticker, or accession-specific behavior.

**Development rule:** a change must state a generic, source-agnostic hypothesis and
be evaluated on a fresh development slice. Do not select a configuration from a
sealed diagnostic or the future held-out cohort.

### G6a — Insufficiency-directed graph continuation

Each bounded exploration response must declare typed `answerability` as either
`sufficient` or `insufficient`. This remains a model-supplied graph decision: the
application may validate and persist it, but must not infer it from headings, tables,
rows, values, page positions, or document type. Only a `sufficient` frontier may
enter answer synthesis. An `insufficient` frontier must provide at least one valid,
unvisited, bounded continuation window linked to accepted or uncertain evidence from
that action; otherwise the explorer persists a `partial` terminal frontier and makes
no answer call. Range validation, source/action/wall-time budgets, and normalized
interval no-revisit remain application-owned.

### G6b — Trajectory and ground-truth coverage cohort

Run the fixed generic protocol on several new development filings that exclude all
prior diagnostics and future held-out cases. Review ground truth only after every
run has completed. Report the cohort-level coverage, citation, support/limitation,
cost, and latency measures together with per-run trajectory inspection. A failure is
an investigation target, not permission to tune toward that filing; any resulting
generic change requires a new development slice.

**Current status (2026-09-27):** active. The existing FGN result is sealed
diagnostic-only and excluded from configuration selection. The isolated scorer and
explorer remain available for post-run inspection, but no frozen V2-packet or
bounded-window artifact is required for G6b.

**Operational-workflow plan:** the next bounded G6b work is the V3-only campaign,
terminal review, and development-scorecard sequence in
[V3_G6B_WORKSPACE_AND_SCORECARD_PLAN.md](V3_G6B_WORKSPACE_AND_SCORECARD_PLAN.md).
It retains V2's inspectable run/scorecard experience while preserving V3's fixed
configuration and post-seal review boundaries; it does not begin G6c.

### G6c — Controlled held-out three-method comparison

Only after G6b selects one configuration, freeze it and compare graph, a frozen V2
packet result, and a frozen bounded-window baseline on a separately held-out cohort.
The comparison rubric scores source coverage, path fidelity, answer support,
ambiguity handling, provider calls/tokens, and latency. Its records attach after
graph construction and are never model or provider inputs. Do not tune graph prompts,
relation vocabulary, budgets, or model from that cohort.

**Promotion gate:** promote no graph behavior into V2 unless this held-out evidence
shows an inspectable source-path benefit at an acceptable cost without reducing exact
citation validity. Otherwise keep the graph as an experiment/explorer and record the
negative result.

The isolated scorer and explorer view are available; its future frozen-cohort format
is documented in [V3_G6_RUBRIC_COHORT.md](V3_G6_RUBRIC_COHORT.md).

## Superseded exploratory draft (preserved for context; do not implement)

## Objective

Test whether bounded Jev decisions can turn reusable, document-local context into
source-grounded graph relationships that improve quantitative-value lookup.

The system's primary truth remains the immutable canonical visible document. A
model decision is always an inspectable inference, never a replacement for source
text. A returned value must be able to reach every interpreted field through
`SourceLine` or `SourceSpan` provenance.

The first measurable milestone is deliberately narrow:

```text
L120  Amounts in millions of U.S. dollars
...
L145  Revenue 728

ValueSpan("728", L145) --IN_SCOPE--> ContextScope --SOURCE--> L120
```

The resolved view must report `728 @ L145`, `millions @ L120`, and `USD @ L120`,
including the graph path and the decision metadata that created it.

## Existing seams to reuse

| Need | Existing implementation | Experiment decision |
| --- | --- | --- |
| Ordered immutable source | `v2.canonical.CanonicalDocument` / `CanonicalLine` | Reuse directly; do not add a second HTML parser. |
| Exact line/range validation | `SourceRange` and `CanonicalDocument.slice()` | Reuse for all source references. |
| Source identity | document ID, raw-source hash, canonical line number | Derive graph IDs from these immutable coordinates. |
| Bounded Jev binary decisions | `providers.jev` (`JevRequest`, `NoulQuestion`, traced client) | Reuse for anchor and boundary decisions. Extend only when a later measured variant needs Choice. |
| Provider tracing/caching pattern | section/chunk scoring services and SQLite repository | Record every request/response and decision in experiment-owned storage. |
| Evaluation shape | `v2.benchmark` and reviewed source ranges | Add a graph-specific reviewed gold fixture; never provide it to Jev. |

`CanonicalLine` is already source-grounded: it has contiguous line number, exact
normalized visible text, element type, DOM reference, and HTML anchor. The existing
`SourceRange` already permits a single-line character interval. A graph span should
therefore reference a `SourceRange`, not copy or normalize source text.

The active V2 SQLite database intentionally rejects schema migration. The experiment
must use a fresh, isolated SQLite namespace/repository (for example
`data/evidence-graph-experiment/`), or a disposable in-memory repository for fixture
tests. It must not alter `V2Repository` or make graph output a prerequisite for
`outline`, `chunk_score`, or `findings`.

## Minimal model

### Immutable provenance layer

```text
SourceLine
  id: line-{source_hash_prefix}-{line_number}
  document_id, source_hash, line_number
  text, element_type, html_anchor, dom_reference

SourceSpan
  id: span-{source_hash_prefix}-{line}-{start}-{end}
  source_range: SourceRange  # exactly one line for the first experiment
  exact_text: derived and checked with CanonicalDocument.slice()
  kind: value | label | header | context_text
```

The line ID is stable for a particular immutable canonical source. It must not be
based on text alone: repeated text may occur on multiple lines. A span constructor
must reject offsets whose slice does not exactly equal `exact_text`. Normalized amounts
may be computed in a query view, but are not persisted as replacement source values.

### Inference layer

```text
ContextKind = SCALE_CONTEXT | CURRENCY_CONTEXT
ContextAnchor
  anchor_id, source_line_id, kinds, status, decision metadata

ContextScope
  scope_id, anchor_id, kind
  start_line, end_line                 # inclusive source coordinates
  status: accepted | uncertain | rejected
  probability, decision metadata

GraphDecision
  decision_id, kind, input fingerprint, prompt version, model/version
  probability, status, evidence_ranges, request JSON, response JSON, timing
```

An anchor may create one scope for `SCALE_CONTEXT` and another for
`CURRENCY_CONTEXT`, even when both are supported by the same source line. A scope is
an inference. Its anchor line and evidence ranges are immutable provenance.

Structural graph traversal is implicit and range-indexed for the first version:

```text
SourceLine --NEXT/PREVIOUS--> SourceLine
SourceSpan --ON_LINE-------> SourceLine
SourceLine --IN_SCOPE------> ContextScope  (resolved by interval lookup)
ContextScope --SOURCE------> SourceLine
```

Do not materialize `anchor -> every covered line` edges. Index accepted scopes by
`(document_id, source_hash, kind, start_line, end_line)` and resolve coverage at query
time. A diagnostic or query may lazily emit a derived path, marked `materialized=false`.

## Interfaces and invariants

Implement an experiment-local interface, not a graph-database abstraction:

```python
class EvidenceGraph:
    def lines(self) -> Iterable[SourceLine]: ...
    def add_span(self, span: SourceSpan) -> None: ...
    def add_anchor(self, anchor: ContextAnchor) -> None: ...
    def add_scope(self, scope: ContextScope) -> None: ...
    def scopes_covering(self, line_id: str, kind: ContextKind) -> list[ContextScope]: ...
    def resolve_value(self, value_span_id: str) -> GroundedValueView: ...
```

`GroundedValueView` is computed, not stored as a claim node. Initially it contains the
value source and zero or more scale/currency fields, each with source span/line, scope,
and decision ID. It must expose ambiguity when two accepted scopes conflict and must
not silently select one.

Required invariants:

1. Every node and graph view belongs to one `(document_id, source_hash)`.
2. A semantic field has a source span/line and a path to it; generated labels cannot
   satisfy provenance.
3. A scope has `start_line <= end_line`, begins after (or at, if explicitly allowed)
   its anchor, and stays within the canonical document.
4. Accepted, uncertain, and rejected decisions remain distinct. A rejected decision is
   retained for replay/audit but is not used for resolution.
5. All Jev state is an allowlisted bounded source window plus structural metadata;
   gold data, Company Facts, prior final claims, and XBRL data are excluded.
6. Replaying a decision with the same source fingerprint, prompt version, model, and
   configuration may use a cached result; changing any of those cannot silently reuse it.

## Construction variants and common output

All variants write the same `EvidenceGraph` contracts and use the same resolver.

| Variant | Candidate anchors | Verification/scope construction |
| --- | --- | --- |
| Baseline | none | overlapping chunks only; no graph output beyond source spans |
| A | Jev scans overlapping 50--100-line windows | Jev bounded anchor and scope decisions |
| B | fast LLM proposes anchors | Jev independently verifies anchors/scopes |
| C | existing layout/extraction heuristics propose anchors and values | Jev verifies/links candidates |

Do not make any variant a recall gate for V2 findings. This is especially important in
light of T39: its early adaptive Jev eligibility gate reduced retained source before
extraction. The graph experiment first measures context edges on known value spans;
only a successful, separate result may justify an optional retrieval integration.

## Implementation sequence

### E0 — reproducible experiment harness

Create `profitlab/evidence_graph/` with its own contracts, repository, and service
entry point. Accept a `CanonicalDocument` and an explicit experiment configuration;
do not fetch SEC content or depend on a V2 run lifecycle. Add a small command/test
helper that loads the existing synthetic `chunk-context.html` fixture through
`canonicalize_html`.

Persist an experiment manifest: source hash, code/configuration identity, prompt
versions, model identity, timestamps, and a wall-clock/monotonic timing summary.

### E1 — immutable graph and value spans

Map every canonical line to `SourceLine`; provide deterministic span IDs and exact
offset validation. Implement an initial deterministic numerical-candidate scanner
(integers, decimals, commas, signs, parentheses) solely to create candidate
`ValueSpan`s. It may over-generate; it must never manufacture a value not present in
the source span. Expose `value spans on line` and `source line for span` queries.

Tests: same-line `728` and `639` produce distinct spans; repeated text has distinct
line IDs; invalid offsets/source hashes fail; all returned text round-trips exactly.

### E2 — scale/currency anchor discovery (Variant A)

Window the document by configurable line count and overlap. For each candidate line,
ask independent Jev Noul questions:

- Does this line explicitly establish a reusable scale for following values?
- Does this line explicitly establish a reusable currency for following values?

The request state contains numbered exact visible lines, line element types, window
coordinates, and the candidate line ID. It does not ask Jev to extract `USD` or
`millions`; those remain interpreted from the supporting source span later. Batch many
questions in one request while staying below a configured character/question budget.
Store raw response and policy thresholds separately. Ambiguous anchors are persisted
as `uncertain`, not discarded or upgraded.

### E3 — scope discovery

For each accepted/uncertain anchor, form local candidate boundaries from structural
signals: next heading/caption, next likely table header, document end, and a bounded
set of progressively farther probe lines. Start with binary Noul checks such as
`Does L120 still provide scale context for L144?` and perform monotonic/binary boundary
refinement only when probe results support it.

Record the entire evidence window for each probe. Do not assume applicability is
monotonic across a new table or section: a structural boundary ends a candidate scope,
and contradictory/low-confidence probes produce an uncertain scope rather than a
wide accepted one. Implement an alternative bounded boundary-selection strategy behind
the same `ScopeDiscoverer` interface only after the binary baseline has measurements.

### E4 — graph resolver and inspectable output

Resolve each value by interval lookup of accepted scopes. A context parser may derive
display values (`millions`, `USD`) only from the anchor's exact text and must return
`unresolved` for unsupported wording. Return both the derived display value and the
original anchor span. Competing accepted scopes return every candidate plus a conflict
state; Jev arbitration is permitted only as a separately logged decision.

Write JSON artifacts containing source IDs, spans, scopes, decision IDs, graph path,
and the computed view. This satisfies the first milestone without generated prose.

### E5 — controlled variants and evaluation

Add the LLM-proposal and existing-heuristic proposal adapters without changing graph
contracts. Build a reviewed fixture with source-line/span annotations for values,
scale/currency anchor lines, and expected scope extent. Use SEC-derived documents only
as evaluation data; no SEC-specific parser or structure belongs in construction.

Measure each variant against the baseline and record p50/p95 across documents:

| Measure | Definition |
| --- | --- |
| Value recall | Relevant reviewed value spans are discoverable. |
| Context-edge recall/precision | Expected applicable source-context paths found / emitted. |
| Field and provenance accuracy | Derived field and its exact supporting source are correct. |
| Build/query latency | Source-to-graph and query-to-grounded-view durations. |
| Jev calls and decisions/document | Operational complexity, including batched questions. |
| Uncertain/conflicting edge rate | Work requiring review or a later decision. |
| Graph size | lines, spans, anchors, scopes, and lazy/materialized paths per input line. |

Every benchmark artifact includes raw Jev requests/responses, decision timings, source
hash, and configuration. Report failures by layer: span detection, anchor decision,
scope inference, resolution, or source-context interpretation.

### E6 — only after E5 succeeds

Add `DATE_CONTEXT`, then `SECTION_CONTEXT`, then table-header/row-label relationships.
Only after measured source-context precision/recall and latency show value may an
optional graph-assisted query navigator be tested. It should retrieve candidate spans,
expand source-backed neighborhoods, and invoke Jev only for ambiguous routing; it must
not replace graph traversal with a wide document reread.

## Storage layout

The fresh repository should contain normalized rows equivalent to:

```text
experiments              immutable source/configuration/timing manifest
source_lines             document coordinate and copied canonical metadata
source_spans             single-line range and exact text fingerprint
context_anchors          one row per kind/candidate decision
context_scopes           inclusive interval, source anchor, status/confidence
graph_decisions          request/response hashes, raw compressed payloads, timing
decision_evidence_ranges decision-to-source-range join
value_spans              candidate span references (or source_spans with kind=value)
```

Indexes: source line coordinate; span line coordinate; scopes by document/kind/start/end;
and decision input fingerprint. Full source text remains canonical-source data; the
repository must store enough verified metadata to inspect it, but must not offer a
mutable alternate source of truth.

## Promotion and stop criteria

This experiment is promising only when it demonstrates all of the following on a
reviewed held-out set:

1. every returned interpreted field has exact source provenance;
2. a reusable context anchor/scope is established once and resolves many values;
3. graph build plus repeated graph-assisted resolution is measurably preferable to
   repeatedly reconstructing the same context from raw windows.

No public Jev provider latency figure is an experiment target. Report measured
end-to-end p50/p95 under the actual concurrency/configuration instead. Stop or revise
before integration if scope precision is poor, uncertainty is high, or the graph simply
duplicates context reconstruction without reuse.

## Explicit non-goals

No Neo4j, graph database abstraction, embeddings, general ontology, cross-document
entity resolution, general named-entity extraction, permanent claim nodes, or GraphRAG
agent is in scope. No structured SEC/XBRL data may enter extraction or Jev decisions.
