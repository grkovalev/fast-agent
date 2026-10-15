# JEV-led Findings implementation plan

Status: T69–T73 DONE; T74–T77 PLANNED, 2026-10-15. Scoped V2 data reset completed in T71.
This replaces the Findings internals in the existing eight-stage pipeline. Keep
the `v2` package, repository, database filename and URLs; do not create a v3,
migration, compatibility mode or permanent old/new execution switch.

## Agreed outcome

For each numeric finding concept, reuse ranked chunk candidates, let JEV assign
source lines to one or several concepts, attach additional context through JEV
yes/no questions, then rank the assembled evidence bundles. Only selected bundles
reach the LLM, which converts their source lines into structured findings. The
LLM does not discover lines, assemble context, rank evidence or assign types.

```text
concept -> candidate chunks -> line/concept assignments -> context links
        -> evidence bundles -> ranked/selected bundles -> LLM conversion
        -> deterministic validation -> sealed findings
```

The three concepts are annual shareholder profit/net income or loss, annual diluted
EPS, and annual diluted weighted-average shares. Earnings-change and comparability
remain retrieval/context targets, not new published finding types. A concept is a
type; a bundle is one source occurrence of evidence for that type. Multiple bundles
and multiple numeric findings per concept are allowed. Empty results are allowed.

The user authorizes discarding the current local database and run data during this
implementation on a separate branch. First retain a bounded baseline outside that
database. Reset only the resolved application V2 data namespace with the server
stopped; record the path and operation. Do not delete fixtures, other application
data, or unrelated worktree changes. Old database detection may reject unsupported
data with reset instructions; it must not auto-delete data on startup. No reset is
performed by this planning change.

## Execution contract for separate agents

Execute T69–T77 sequentially, each in a different fresh-context agent. Start agents
only when implementation is requested. Each reads `AGENTS.md`, `TASKS.md` execution
policy, `PIPELINE_PAGE_DESIGN.md`, this plan, its task, and recent `PROGRESS.md`.
Inspect actual code and worktree before implementing. Complete one task, record its
checks and handoff, and stop. Dependencies are completion gates, not suggestions.

T69–T75 build and test the replacement components without wiring a second live
pipeline. The current product route remains accurate until the atomic T76 switch.
Do not advertise unconnected components as active runtime stations. Schemas and
inspection builders for new components can be prepared/tested without exposing
them in the active route. If an earlier task changes any user-visible active
behavior, update its overview, selected-stage inspection and focused checks in that
same task. T76 activates runtime and its complete visual explanation together;
T77 verifies and fixes them together. No backend-first/UI-later release gap.

Preserve the repository's no-browser-automation policy. Use route/render tests and
give manual UI checks at wide/phone widths, keyboard, no JS and 200% zoom. Record
manual checks as pending until actually performed. Use isolated test databases;
paid provider calls never belong in default tests. Follow TASKS.md for lint, focused
tests, full-suite checks for shared storage/provider/orchestration, progress and
handoff requirements. Do not claim saved-response tests are live measurements.

## Runtime decisions

### Candidate ownership and inputs

- Derive a concept-to-chunk map from persisted selected `ScoredItem` records and
  their per-target scores; there is no extra chunk-scoring call. For each concept,
  admit selected chunks at or above the existing uncertain relevance threshold,
  order by that concept's score, then source order. This includes weaker concept
  evidence in chunks retained for another target. Record lower-score omissions;
  selected/uncertain/skipped chunk policy remains unchanged upstream.
- A source candidate must be a canonical line in a candidate chunk's core. A cheap
  recall-oriented numeric-span parser can exclude lines with no numeric content;
  do not require metric keywords or a currency symbol. Keep dates, zero, losses,
  and comparative columns available for JEV to interpret. Nonnumeric lines remain
  context candidates. Retain spans/offsets as data, not already selected amounts.
- Deduplicate repeated source occurrences by concept, document/hash and canonical
  line, retaining all eligible owning chunks. Choose the owning chunk by concept
  relevance, then source order/ID. Identical text at distinct lines stays distinct.
- Providers receive canonical visible text and minimal validated navigation only.
  Generated outline topics are hints, never evidence. No Company Facts, evaluation
  data, XBRL semantics or post-Findings provenance enters any new request.
- Do not change canonical numbering or import raw-HTML fact mapping into Findings.
  External visible captions absent from canonical lines remain a documented input
  limitation. Test this explicitly rather than silently inventing context.

### Assign source lines with Noul

Ask independently whether each numeric source line reports a value belonging to
each candidate concept. A row with profit and EPS may receive both assignments.
Do not replace this with mutually exclusive Choice classification. Instructions
name the concept and the exact referenced candidate in state; API question IDs
alone are not model instructions. Keep uncertain and rejected assignments with
raw probabilities and policy reasons. Default support threshold: 0.65; uncertain
band: 0.20–0.65. These are provisional Findings-owned settings, not reused chunk
thresholds that silently couple two policies.

### Attach bounded context with Noul

For each supported line/concept pair, ask whether a candidate line provides
additional context for that specific source line and concept. Persist a general
support answer plus atomic role answers for period/duration, unit/scale,
entity/attribution and qualification/comparability. Ask them together; no question
depends on another answer within that request. Shared context may support several
bundles and roles. Never treat the answers as independent evidence or multiply
their probabilities to manufacture a confidence value.

The allowed context pool is the union of concept-candidate chunk cores and their
existing preceding context ranges, plus retained earnings-change/comparability
chunks and their context. All ranges remain explicit canonical ranges. Within
this pool, enumerate local lines before/after the source and structural headings,
captions and table-header candidates in its owning section. Do not cross sections,
fetch more source, or change chunk coverage. Deduplicate overlaps. A following line
can be context if it is in this allowed pool; this does not alter Chunks' existing
preceding-overlap contract. Record the pool and all omissions so a bounded search
is never described as an exhaustive document scan.

Provisional defaults: 12 local lines each direction, at most 40 context candidates
per bundle, at most 12 selected context lines per bundle, support threshold 0.65.
Reserve candidate slots for structural context before filling with local lines;
keep selected lines in source order and record any context-cap loss. T73/T77 can
adjust defaults using recorded evidence; any adjustment changes policy/version
and its explanation together. A missing role remains explicitly unresolved and
reduces completeness; it does not fabricate a year, unit or attribution.

### Rank bundles, then select in code

JEV evaluates each assembled bundle, not an isolated line. Use a Score rubric:
0 unrelated/unsupported, 1 relevant but meaning largely unresolved, 2 direct
reported value with some context unresolved, 3 direct reported value with clear
period, unit and scope. Add separate Nouls for requested fiscal-year support,
annual duration, reported-versus-adjusted/forecast basis, and concept-specific
scope. A row containing current and comparative columns can be eligible; the
converter must later identify the current-year numeric span.

Known-negative required conditions make a bundle ineligible; uncertain conditions
retain an uncertain bundle. Supported candidates form the eligible group. The
application selects eligible bundles only; unresolved optional unit/scale metadata
can survive with limitations. Keep the eligible, uncertain, rejected and
budget-omitted groups separate. A high rank cannot overrule ineligibility. Threshold
boundary logic and concept-specific required conditions belong to one policy
builder shared by execution and inspection.

Sort eligible bundles within each concept by descending Score, then source-support
Noul, upstream concept score and source order/ID. Do not compare Choice probability
mass across separately packed batches. Default selection: at most three bundles
per concept, nine total; keep multiple source occurrences until conversion because
similar text can contain conflicting values. This is a configurable bounded
selection policy, not a promise of one answer per concept or complete coverage.
Do not add pairwise ranking calls or an LLM tie-breaker in this first implementation.

### Convert selected bundles only

The LLM receives bundle IDs, known concepts, exact source lines, chosen context
lines/roles, visible numeric spans and filing report date. It receives neither the
full outline nor unselected chunks. One normal request can convert all selected
bundles; deterministic packing may split it under a fixed budget. Each bundle can
yield zero, one or several proposals. A proposal identifies its bundle and the
numeric span; it cannot create a new source line or change the concept.

Validate proposals against the selected bundle, not all stored chunks: bundle
exists/is selected; its declared line is the source line; quote matches that line;
numeric span/offset and finite Decimal match visible text including sign; type is
the bundle's concept. Bind metadata claims to selected context/source references;
source-reference existence proves provenance, not financial interpretation. Unknown
metadata is null with limitations. Keep amount equal to the displayed number;
record any scale separately rather than silently applying it to the amount.

Deduplicate final findings by concept, exact source span and amount. Merge repeated
ownership of the same occurrence; preserve equal values at different occurrences,
different concepts and conflicting amounts. IDs include concept and source identity.
Persist bundle links and context references with findings so source/UI inspection
does not reconstruct selected context from the original full chunk.

One bounded repair can address invalid proposals using their existing selected
bundles only. Preserve initially accepted findings and merge validated repaired
proposals; retire the old whole-response replacement semantics. There is no
post-conversion JEV type classifier and no LLM discovery fallback.

### Batching, accounting and failure semantics

Use bounded shared-client JEV batches with existing transport/redaction/retry owner
and `v2_provider_concurrency`; each successful batch is checkpointed. Persist actual
models, raw answers, policy versions, full safe request identity, usage, timings,
cache hits, omitted counts and reasons. Enforce provider token limits in addition
to local serialized character limits. Instructions must reference state explicitly.

One named Findings policy owns settings for source/context/rank request bytes or
characters, token estimates/margin, question count, candidate counts, total provider
requests, elapsed deadline, context count, selected bundle count and LLM conversion
requests. Proposed starting bounds: 20,000 serialized characters and 64 questions
per JEV batch, 100 JEV requests/stage, 300-second total Findings deadline, 60,000
characters/conversion request, at most two initial conversion requests plus one
repair. Verify serialized instructions/criteria overhead, not state alone. Values
are tunable defaults, not measured optimums. Build no Cartesian product larger than
the admitted candidate budget. Record planned, dispatched, completed, cached,
failed and omitted work separately; cache hits are not live calls.

Empty input/no supported lines/no eligible bundles: complete with an explained empty
set and zero LLM calls. Deterministic count/size caps: persist omissions and mark
stage partial when coverage was actually cut. Provider failure/deadline exhaustion:
persist completed batches and failed step, fail/interruption as appropriate, and
do not seal an apparently complete subset. Resume reuses exact successful batches;
provider cancellation is not converted into an empty result. Rank-based intentional
selection is not itself a partial-stage condition. A terminal bounded conversion
rejection can seal accepted results with visible rejection diagnostics, matching
the existing publication contract. Facts may start only after a sealed completed
or partial Findings result; failed/interrupted work is not sealed. T76 must update
the existing Facts/provenance scheduling checks together for that explicit partial
case, without supplying finding values to the independent facts lane.

Cache keys include canonical source hash, exact candidate/context inputs, concept,
question/rubric version, model identity and every behavior-affecting policy value.
Exclude run-local IDs from reusable identity; remap occurrence IDs on reuse.
Pin/log the actual JEV model for measured comparisons. Add all new relevant values
to run version components/cohorts. Never reuse a checkpoint after changed inputs
or policy. Public JSON and accounting come from typed runtime results, not dicts
with undocumented competing field meanings.

## Contracts and persistence

Names below are the shared vocabulary; T69 finalizes exact field definitions in
Pydantic classes rather than allowing later agents to invent different shapes.

| Contract | Responsibility |
| --- | --- |
| `FindingConcept` / shared concept definitions | Stable three-concept identity and financial definition |
| `ConceptChunkCandidates` | Concept, eligible chunk references, per-target scores, inclusion/omission reasons |
| `FindingLineCandidate` | Exact canonical line/range, owner(s), visible numeric spans and concept association inputs |
| `ConceptLineAssignment` | Candidate/concept, Noul, decision, question/model/call provenance |
| `FindingContextLink` | Bundle/source candidate, context line/range, support/role answers and policy decisions |
| `FindingEvidenceBundle` | Concept, source candidate, selected context links and unresolved roles |
| `RankedFindingBundle` | Bundle, Score/distribution, eligibility Nouls, rank/decision/reason |
| `FindingConversionProposal` | Selected bundle ID, exact quote/span, amount, metadata and supporting references |
| `Finding` | Published source-validated value, fixed concept, selected bundle/context provenance |
| Typed step results and `FindingsRunSummary` | Availability/status, counts, limits, usage, calls and persisted outputs for each phase |

Reuse `SourceRange`, `TextChunk`, `ScoredItem` and canonical classes. Request state
and result models must be the models executed and persisted, with strict bounds
and enum constraints. Small dedicated modules under `v2` are preferred to growing
one service file into a generic framework. Separate request/policy builders from
I/O so safe examples can execute the real builders without credentials.

Store candidate maps, assignments, context links, bundles/ranks, conversion
diagnostics and checkpointed batch results in fresh schema tables with indexed
run/step/concept/occurrence access. Use typed JSON payloads where suitable; avoid
persisting many copies of source text in every link. A reader can fetch complete
saved detail with pagination without provider I/O. Keep sanitized transport traces
distinct from domain results. Remove obsolete extraction/type-cache tables and
legacy result reconstruction once T76 switches consumers. Schema validation must
reject the old database; no migration or historical UI fallback is needed.

## UI contract

Findings uses seven selectable stations in the existing editorial composition:
**Candidates -> Assign lines -> Attach context -> Rank/select -> Convert ->
Validate -> Seal.** Its always-visible illustration shows concept lanes, shared
source lines, one bundle's context attachments, selected/uncertain/rejected groups,
and only selected bundles crossing into the LLM operation. Show the bounded repair
return to Validate and accepted findings bypassing that repair. Empty/budget/error
branches and variable result cardinality are visible without selection. Do not
turn seven stations into seven full-size repeated cards.

Overview and selected Findings page expose the same saved phase results. Clicking
a station opens its saved result above runtime contracts, real request/questions,
effective policy, safe validated examples, provenance and source links. Generate
schema with `model_json_schema`, instances with `model_dump(mode='json')`, and
illustrative requests through runtime builders. Do not define UI-only copies of
source, context, ranking or proposal models or handcrafted example payloads that
bypass those classes. Label schema, illustration/current config and persisted run
data separately. Bounded previews link to complete paginated saved details.

Show selected and losing bundles, support probabilities, rank/eligibility reasons,
context roles and unresolved roles. Each source/context link uses the existing
canonical source route/anchor. Show source-validation guarantees separately from
JEV judgments and LLM metadata interpretation. Accounting separates JEV phases,
LLM conversion/repair, live/cache work, discarded/omitted candidates and stage state.
Update Findings output inspection and Evaluate's finding-evidence preview to use
the persisted selected bundle context; do not quietly re-expand it to full chunks.
Trace Evaluate's request construction separately: preserve independent comparator
values and existing optional scale-verification semantics; if its request uses
chunk context today, do not change that decision input merely for UI convenience.

Keep eight-stage routes, source/trace URLs, shared muted colors, semantic operation/
gate/group/output treatments, station selection, responsive reflow, reduced motion,
keyboard behavior, no-JS reading and Facts-below-Evaluate relationships. No frontend
framework, graph engine, playback or new pipeline version. Update the durable
design brief and README at activation, removing obsolete Findings explanations.

## Task register

| Task | Deliverable | Depends on | Status |
| --- | --- | --- | --- |
| T69 | Baseline evidence and shared replacement contracts/policy | Planning complete | DONE |
| T70 | Typed mixed Noul/Score adapter and bounded batch execution | T69 | DONE |
| T71 | Fresh storage/checkpoints and concept-to-chunk/line enumeration | T70 | DONE |
| T72 | JEV multi-concept source-line assignments | T71 | DONE |
| T73 | JEV context links and assembled evidence bundles | T72 | DONE |
| T74 | JEV bundle ranking and deterministic selection | T73 | PLANNED |
| T75 | Selected-bundle LLM conversion and strict validation | T74 | PLANNED |
| T76 | Atomic runtime/UI activation and obsolete flow removal | T75 | PLANNED |
| T77 | Real-data quality/latency acceptance and final closure | T76 | PLANNED |

### T69 — Baseline and replacement contracts

Read Findings, shared contracts/settings, canonicalization, scoring, inspection,
storage, orchestration and evaluation consumers. Before any reset, capture/export
bounded baseline findings, retained inputs, configuration/models, source hashes,
per-provider counts/usage and timings for representative saved runs where present.
Historical results are observational, not necessarily comparable timed baselines.
Keep a provenance manifest and immutable input artifacts in a dedicated benchmark
fixture directory, outside application data. Capture the old stage on those exact
retained inputs when configured; if unavailable, record the future measurement gap.
Do not add a permanent baseline execution mode to production.

Implement shared concepts, all contract skeletons with meaningful validated fields,
one Findings policy model/settings builder and safe example builders. Finalize
required eligibility conditions per concept, phase names, identity, status,
metadata-reference and budget semantics above in this document. Reuse existing
models; avoid importing a service into another service just for concept constants.
Keep active old contracts while their current consumers exist; delete them in T76.

Checks: contract serialization/constraints/source identity, actual safe examples,
numeric parser/sign expectations, policy boundaries and absence of forbidden input
fields. UI handoff: current pipeline unchanged; replacement schemas/builders are
prepared but not advertised as live behavior. Record baseline availability and
the exact next task. Gate file: `tests/task_gates/test_t69_findings_contracts.py`.

### T69 finalized contract decisions — 2026-10-14

- `finding_concepts.py` owns the stable three-value enum, definitions and scope.
  Earnings-change/comparability remain context retrieval targets. Existing active
  constants/consumers stay unchanged until T76; new services import this vocabulary.
- `findings_contracts.py` owns prepared artifacts and minimal request states;
  `findings_builders.py` and `findings_examples.py` own pure validated builders and
  explicitly illustrative instances. They are not registered in active inspection.
  Mixed Score transport/questions remain T70; `RankState` already binds the actual
  four-level rubric and required-condition definitions for that integration.
- Phase values are `candidates`, `assign_lines`, `attach_context`, `rank_select`,
  `convert`, `validate`, `seal`. Step status distinguishes pending/running,
  completed/partial, failed/cancelled/interrupted and skipped; availability is
  unavailable/checkpointed/final. Summary separates JEV assign/attach/rank from
  LLM conversion/repair, and live dispatched/completed/failed work from cache hits
  and omissions. Unknown native usage is null, never a fabricated zero.
- Stable line occurrence IDs hash concept, raw canonical source hash and line
  number, excluding run-local document/chunk IDs. Document/hash must still match
  in every range/owner/context relationship. Bundles identify that same occurrence.
  Reusable batch identities also require exact remapped input hash, phase, concept,
  model identity, question version and the complete effective policy hash.
  T71 owns occurrence remapping/storage; T75 owns final span/amount finding IDs.
- Every concept requires separate requested-year, annual-duration, reported-basis
  and concept-scope judgments. Profit requires consolidated shareholder income/loss;
  EPS requires diluted common-share earnings; shares requires diluted weighted-average
  common shares. Basic, period-end, segment and adjusted substitutes fail the
  corresponding scope/basis condition. Any probability below .20 is rejected;
  [.20, .65) is uncertain; .65 and above is supported. Rejection dominates
  uncertainty, and only all-supported required conditions are eligible. High Score
  never overrules this gate. Threshold decisions remain application policy.
- Optional unit/scale/entity/qualification context roles remain explicitly unresolved
  if selected role support is missing. This differs from the required scope/basis
  gate: missing optional qualification alone need not veto an eligible bundle.
  General context support and the four role answers remain independent, never
  multiplied. Selected context belongs to the same canonical source/owning section;
  builders require an explicit allowed pool and preserve whole lines/source order.
- Numeric spans use half-open canonical-line character offsets, raw displayed text
  and finite Decimal. Commas are removed for amount, parentheses denote loss
  (including a redundant inner minus), minus and Unicode minus preserve sign.
  Years/percentages/zero/repeated amounts remain candidates, not semantic assignments.
  Amount stays equal to the displayed number; scale is separate cited metadata.
  T71 further hardens enumeration/parser edge cases; T75 checks exact quote/span and
  metadata against supplied selected-bundle references and fixes concept at publication.
- `FindingsPolicy` is configurable through `FINDINGS_POLICY` JSON in Settings; one
  builder validates it and excludes secrets. Independent assign/attach/rank budgets
  include whole serialized request and instruction/criteria overhead, question cap,
  estimated token cap/margin (defaults 8,000/512, conservative 3 chars/token).
  These are application estimates, not provider-limit guarantees; T70 verifies the
  live model limits. Additional defaults are 1,000 candidate lines, eight structural
  candidate reservations within the 40-line context cap and 48,000 selected text
  characters. Other agreed defaults above remain unchanged. Every policy field
  participates in identity. Oversized atomic inputs are omitted/error, never truncated.
- Count/size omissions cut coverage and require partial results; relevance/ranking
  selection is intentional exclusion. Empty successful results may seal with zero
  conversion calls. Seal requires all seven successful terminal phases and only
  completed/partial status; failed/interrupted/cancelled subsets cannot publish.
  Terminal conversion rejections can retain accepted findings with diagnostics;
  repair preserves accepted results and uses a separate one-request cap.
- Baseline provenance/results are in [the retained manifest](../tests/fixtures/benchmarks/t69/manifest.json)
  and [fixture README](../tests/fixtures/benchmarks/t69/README.md). Three saved runs
  plus one isolated live AZZ replay are retained. No database reset was performed.
  Old LLM token usage remains unavailable; no quality/speed acceptance is claimed.

### T70 — Mixed typed JEV evaluation and batching

Extend the current HTTP adapter with discriminated Noul/Score question and answer
unions, structured instructions where used, distribution/legend constraints and
request-to-response type/ID/rubric validation. Add Choice only if an actual consumer
requires it; line membership must remain independent Nouls. Preserve existing
Noul-only scoring/evaluation consumers and response checking.

Build bounded shared-client batch execution using current tracing/transport retry
ownership, request-size/token estimates, concurrency and cancellation. Add hooks
for successful batch checkpoints and typed phase accounting; persistence arrives
in T71. Keep instructions' explicit state references and question overhead in
packing. A single oversized atomic item receives a documented omission/error;
never truncate evidence text to make it fit.

Checks: one mixed response with provenance, wrong answer type/IDs/levels, bounded
packing, concurrency/deadline/cancellation and existing provider consumers. Use
recorded real responses if available; synthetic responses only for controlled
malformations. Full suite required for this shared-provider change. UI: expose
adapter schemas through existing inspection only where already used; no future
phase advertised. Gate: `test_t70_jev_batching.py`.

### T70 finalized adapter/batching decisions — 2026-10-14

- Shared JEV questions/answers are discriminated Noul/Score unions; no Choice
  consumer was introduced. Existing Noul request serialization is unchanged.
  Score uses 2–10 criteria, consecutive zero-based legend/distribution levels,
  finite probabilities/confidence, sum/weighted-score checks and exact string
  rubric matching. Structured instructions/criteria serialize through validated
  JSON values; structured criteria have level-count validation because provider
  legend rendering is unspecified. Real responses round scores/probabilities
  independently to two decimals: validation permits their accumulated rounding
  envelope. A retained real 2.12 score corresponds to 2.13 from displayed weights.
- `findings_batching.py` packs atomic state/question groups whole, with explicit
  structured instruction scopes into `state.items.item_N`; IDs only route results.
  Packing includes full state/instruction/criteria/model serialization. Oversized
  items are omitted without truncation. Request-count omissions and atomic-size
  omissions retain item IDs/reasons. `PhaseAccounting` counts request groups,
  including one omitted group per oversized item; `omitted_items` separately
  counts atomic omissions, which may share one omitted packed request.
- Verified official API/model docs on 2026-10-14: 32 MiB body, 64k request and 32k
  question context for Jev 1.13/1.14 and current aliases, no long-context header.
  Packing enforces application character/question/token-estimate limits plus
  conservative UTF-8 byte estimates against both provider context limits; unknown
  model limits are rejected. Estimates are not native tokenizer measurements.
- One shared HTTP client uses current TracedTransport retry/tracing/redaction and
  `v2_provider_concurrency`; executor adds no retries. Successful batches invoke
  an awaited checkpoint hook, including validated cache hits. Failures/deadlines
  and cancellation retain typed partial results and drain cancelled workers;
  they never become successful empty work. Stable plan indices preserve result
  order even for identical packed requests. Native live usage excludes cache hits.
- Wire hashes identify exact reusable requests; callers must additionally verify
  the T69 full source/policy/question/model identity before supplying cached data.
  Current routes remap item IDs on reuse. Persistence, stage integration, global
  phase/deadline budgets and sealing remain T71–T76; this executor remains unwired.
- Gate/full-suite/live evidence and pending manual checks are in PROGRESS.md and
  `tests/fixtures/benchmarks/t70/README.md`. No reset or UI/runtime activation.

### T71 — Fresh persistence and candidate enumeration

Implement fresh tables and typed repository access for new artifacts/checkpoints,
indexed paginated reads, atomic step completion, and policy/input-sensitive caches.
Retain currently used old tables only until activation; do not write adapters or
migrations. Reject the prior schema. After T69 baseline capture, stop the server,
reset only the resolved V2 data namespace, then verify fresh initialization.
Record the actual operation and restart prerequisite; use isolated data in tests.

Build concept-to-chunk candidates from saved scores and deterministic numeric-line
enumeration with overlap/owner resolution and explicit omissions. Harden numeric
span handling for parentheses/minus signs, commas/decimals, zero, percentages,
year labels, repeated amounts and multiple numbers on a row. Parsing identifies
spans; it does not infer their metric or fiscal year.

Checks: fresh schema/rejection/typed round trips, checkpoints/pagination, concept
score inclusion boundaries, shared lines/multiple owners, numeric edge cases,
source isolation. Full suite required for shared storage. UI: prepared candidate
schema/request/result projections; active route unchanged. Gate:
`test_t71_findings_candidates.py`.

### T71 finalized persistence/enumeration decisions — 2026-10-15

- Fresh schema uses `PRAGMA user_version=71` with the existing application ID,
  package, database filename and routes. Old data is rejected with scoped reset
  instructions, without mutation. Current old runtime tables remain until T76.
- Five prepared tables retain typed phase artifacts, atomic final step results,
  successful batch checkpoints, exact reusable phase caches and run summaries.
  Artifact indexes cover run/phase/type/concept/occurrence; reads and checkpoint
  inspection are paginated. A phase's replacement artifacts and result commit
  together. Conversion diagnostics can retain several proposals per bundle;
  empty diagnostics have no inferred concept. Transport traces remain separate.
- Cache identity includes all T69 source/input/policy/concept/phase/question/model
  fields plus the exact serialized safe request (including instructions/rubrics).
  Only document/filing/chunk/section routing ID fields are removed from reusable
  request identity. Canonical hashes, text, offsets and occurrence IDs remain.
  Reuse returns the current request and routing map, validates answers and checks
  the saved actual model. Callers must supply the exact semantic input identity;
  a cache never substitutes for its phase/source/policy identity.
- Core-only numeric enumeration admits selected chunks at the upstream uncertain
  threshold for each concept, sorts by concept score/source/ID, retains eligible
  owners, and deduplicates concept/hash/line occurrences. Below-threshold and
  nonselected chunk omissions, nonnumeric context-only lines and global count
  omissions are explicit. Count cuts yield partial; relevance exclusions do not.
  Parser handles displayed sign/parentheses (including canonical whitespace),
  comma groups, decimals/fractional decimals, zero, percentages, years and repeats;
  it chooses no metric, period, unit or scale. Source isolation is enforced before
  enumeration. The existing Apple external-caption limitation remains unchanged.
- After verifying T69 compressed/uncompressed baseline hashes, stopped the local
  server (PID 64233), verified no port-8000 listener, and used `shutil.rmtree` only
  on resolved `/Users/grkovalev/repos/src/fast-agent/data/v2`. Fresh initialization
  recreated `profitlab-v2.sqlite3`, version 71, with zero runs. Fixtures and other
  data were untouched. Server remains stopped; `uv run profitlab serve` is the
  one-time restart prerequisite. No replacement runtime/UI activation occurred.
- Gate/full-suite evidence and pending manual verification are in PROGRESS.md.
  Next task is T72 in a different fresh-context agent, only when requested.

### T72 — Assign lines to concepts

Status: DONE, 2026-10-15. Prepared source assignment plans, exact requests,
persisted answers/decisions and restart-safe successful batch reuse are implemented;
no active pipeline switch.

Implement source-line Noul request builders and service using T70/T71 batching,
minimal exact state, supported/uncertain/rejected decisions, persisted raw answers
and successful-batch reuse. Test multi-concept membership explicitly. No LLM calls,
exclusive classification or premature amount/year selection.

Checks: saved real filing rows, one line supporting several concepts, basic versus
diluted values, annual/quarterly labels, source support thresholds, no supported
lines, omissions and restart reuse. Prepared Assign inspector uses exactly the
executed question/state/results classes. Gate: `test_t72_findings_lines.py`.

### T72 finalized source-assignment decisions — 2026-10-15

- `findings_lines.py` prepares deterministic line/concept plans and executes only
  Noul membership questions through T70 batching and T71 storage. Exact single-line
  canonical text, filing identity and candidate ownership are validated before
  planning. State is the actual `AssignmentState`; it contains filing metadata,
  fixed concept/definition and exact source range/text, with no full chunks,
  outline, chosen numeric spans, Facts or evaluation values.
- Independent supported/uncertain/rejected decisions retain raw Noul answers,
  reasons, current source references and model/question/request/batch provenance.
  Multiple concepts may be supported on one occurrence. Basic-only values are
  distinguished from diluted; explicit duration labels remain exact. No amount,
  span or fiscal-year choice and no LLM call occurs here. Requested-year and
  annual-duration eligibility remain later bundle judgments.
- Atomic size and packed request-count omissions are explicit partial coverage;
  nothing is truncated. Callers can supply a remaining request/deadline allowance,
  bounded by the policy; T76 owns the shared whole-stage budget across phases.
  Execution pins verified actual models to make checkpoint identity unambiguous.
  Cache identity covers exact safe input requests (including omitted inputs),
  source, questions, policy and model, excluding documented local routing IDs.
- Successful batches persist before further work on that worker; restart/cache
  reuse remaps current routes and records zero native usage for cache hits.
  Final assignments and step results replace atomically. Failed/interrupted/
  cancelled executions raise typed results and retain successful raw checkpoints;
  they never write a successful subset. The prepared plan/result projection holds
  the exact executed request/state/results for the future Assign inspector.
- Eight focused checks cover genuine recorded six-question AZZ requests/responses,
  real row 147 with controlled independent memberships, threshold boundaries,
  basic/diluted output, annual/quarterly label preservation, no supported/empty
  input, size/count omissions, source/policy isolation, deadline/cancellation/
  failure, restart reuse and current local-ID remapping. Synthetic judgments and
  label mutations are explicitly controlled invariants, not accuracy evidence.
- One real live JEV request on six saved AZZ line/concept pairs used actual
  `jev-1.13.0`, 3,395 input/124 output tokens and 0.4180s executor time. Basic EPS
  was rejected; diluted EPS/shares were supported. Both row-147 assignments stayed
  uncertain because its label includes adjusted calculation. No multi-concept
  accuracy or speed acceptance is claimed. Official API/model limits were rechecked
  before the probe; redacted evidence is retained under `benchmarks/t72`.
- Gates and full suite passed; see PROGRESS.md for durations and manual handoff.
  Active pipeline/UI/Facts/Evaluate paths remain unchanged; no reset or activation.
  Next task: T73, in a different fresh-context agent, only when requested.

### T73 — Attach context and assemble bundles

Implement allowed context-pool construction, bounded structural/local enumeration,
general/role Nouls and link selection. Persist source/context ranges, raw answers,
roles, unresolved roles and dropped candidate/selected context. Assemble typed
bundles without copying a full outline or full chunks into every provider state.
Keep context shared by reference and restore source order for conversion/inspection.

Checks: comparative-year headers, scale captions present in canonical lines,
entity labels, distant headers within the bounded allowed pool, shared context,
following context, overlapping chunks, absent roles, unavailable external captions,
cross-section rejection, question budgets and resume. Prepared Attach inspector
shows exact role questions and context ownership. Gate:
`test_t73_findings_context.py`.

T73 completed, 2026-10-15:

- Prepared `findings_context.py` builds shared canonical coverage from the union of
  concept-candidate chunks and selected earnings-change/comparability chunks whose
  respective target reaches the same recorded upstream uncertain threshold. Core
  and preceding-context ranges retain chunk/section ownership; no new source fetch,
  section crossing or chunk coverage change is allowed.
- Reserve structural candidates (headings/captions and table rows with no numbers
  or date/year-only numbers), then nearest local lines, then remaining structural
  lines, within the configured cap. Following lines are allowed only inside this
  pool. Overlap deduplicates by canonical occurrence, retaining every owner.
  Nonlocal/nonstructural exclusions are grouped by source range; other-section
  exclusions are explicit. Candidate/request/selected-context caps mark partial
  coverage, while bounded search scope remains an explicit limitation.
- Five independent Nouls per source/context pair persist general support and all
  four role answers. General support admits links; selected-line ties use supported
  role count, support, distance and source order. Selected context returns to source
  order. No probability multiplication, invented metadata or external-caption import.
  Typed pools, links and bundles persist atomically; raw successful batches checkpoint
  before further work, with exact-input/policy/model reuse and current local-ID remap.
- Prepared plan/result and actual request builders expose questions, ownership,
  omissions, unresolved roles and answers for the later Attach inspector. No active
  runtime/UI/Facts/Evaluate switch or database reset. Gates/provenance/manual handoff
  are recorded in PROGRESS.md. Next: T74, only when requested, in a fresh agent.

### T74 — Rank and select bundles

Implement the shared Score rubric, required-condition Nouls, eligibility decisions,
within-concept ordering, deterministic ties and per-concept/global/count/text
limits. Persist winners and all uncertain/ineligible/omitted/losing records with
reasons. Ensure conversions can fit whole selected bundles; record any preconversion
packing omissions, with no silent context stripping. Rank confidence is a signal,
not independent proof or a veto on equally good alternatives.

Checks: complete versus ambiguous bundles, wrong period/quarter/adjusted scope
despite high Score, current/comparative row, several competing values, exact ties,
no eligible result, low-context result, batch-order independence and budget cutoff.
Prepared Rank inspector uses real rubric/policy/results. Gate:
`test_t74_findings_ranking.py`.

### T75 — Convert and validate selected evidence

Implement strict selected-bundle conversion request/proposal models, prompt builder,
structured LLM output, response/model/usage recording and conversion batch cache.
Carry fixed concept and source/context references through publication. Validate
numeric span/sign and bundle ownership; restrict metadata provenance to supplied
lines and leave semantic uncertainty visible. Bind every output to a selected
bundle. Permit several relevant current-year values from a row when supported.

Repair only invalid selected-bundle proposals under the separate bounded repair
budget; preserve accepted results. Prevent repair from changing concept, selecting
another line or pulling unselected evidence. No post-LLM type call. Update `Finding`
and its existing consumers as needed to support provenance without pretending the
new flow is already active; old constructors can use sensible optional fields
until T76 removes unused transition-only defaults.

Checks: several numbers/years on one row, quotes/sign/Decimal/source offsets,
metadata references, unselected bundle rejection, no extra model work, accepted
results surviving repair, empty conversion, dedup identity and bounded failure.
Prepared Convert/Validate/Seal inspectors use real models/builders. Gate:
`test_t75_findings_conversion.py`.

### T76 — Activate the replacement with its UI

Wire the seven phases into `FindingsService.build` and pipeline scheduling, with
durable batch checkpoints, limits, failures/partial publication and summaries.
Update all relevant Facts/provenance seal checks for explicit completed/partial
publication. Update version cohorts, evaluation/benchmark/performance accounting:
count line/context/rank JEV and conversion/repair LLM separately, including real
usage/cache/timing. Do not leave metrics using old `calls` as if it means all calls.
Make seal/publication atomic and reuse only completed matching checkpoints.

Replace `_pipeline_findings.html`, Findings inspector/result projection, selected
stage content and connector selection hooks with the seven-station composition.
Add paginated saved candidate/bundle detail access using existing route patterns.
Provide all public schema/instances/request examples via actual classes/builders.
Show real intermediate results during execution, source/context links, losing
bundles, unavailable/pending results, actual policy/limits and precise accounting.
Update Evaluate's evidence preview with selected context without changing its
independent comparison inputs or optional verification policy inadvertently.

Delete old extraction assembly/classifier/cache settings/tables/helpers, whole-set
repair behavior, legacy result reconstruction and obsolete tests. Recreate local
V2 storage after schema cleanup within the already-authorized namespace. Update
README, durable design brief (replace obsolete Findings paragraphs), current task
register and progress; no dormant old/new modes survive.

Checks: end-to-end isolated storage/service/route paths; selected/uncertain/rejected,
empty/limited/partial/error/cancel/resume; Facts seal gate; source isolation; bounded
JSON generated from executed classes; matching overview/selected-stage branches;
source URLs; no read-time provider I/O; metric/version correctness. Full suite,
lint and diff checks required. Manual visual handoff includes all new stations,
source/context links, losing bundle reasons, wide/phone, keyboard, no JS, reduced
motion and 200% zoom. Gate: `test_t76_findings_pipeline_ui.py`.

### T77 — Real-data acceptance and final handoff

Use identical retained inputs from T69 to compare old recorded baseline and new
Findings, keeping upstream discovery out of this comparison. Include Microsoft
and Apple saved filings already in tests plus at least one loss/ambiguous/qualified
layout when available. Create human-checked source-line/context/span labels with
URLs, hashes and annotation provenance. Gold/Company Facts may be used after the
run for evaluation only, never in discovery requests. Split threshold tuning from
held-out acceptance; do not tune on the final acceptance examples.

Measure source assignment/context recall, selected-bundle target coverage, wrong
year/type/amount, metadata uncertainty, final finding quality, JEV phase calls/tokens,
LLM conversion/repair calls/input/output tokens, cold/cached Findings latency and
end-to-end latency separately. Distinguish candidate-enumeration loss, assignment
loss, context loss, selection loss and conversion rejection. Report actual sample
size; p95 requires enough comparable repeated observations, otherwise report
individual durations/median without population claims. Live measurements use
configured credentials and the pinned/logged provider model; response replay is
only deterministic correctness acceptance.

Acceptance: no LLM before selected-bundle conversion; no post-conversion type calls;
all published citations/amounts pass selected-bundle validation; three concept
coverage is no worse on the labeled acceptance inputs; no new incorrect year/type/
amount on that set; preserved empty/ambiguous outcomes; lower conversion input
volume and measured cold Findings latency improvement on comparable runs. Report
quality/latency failures honestly and adjust the relevant component/policy/UI as
one change. Do not mark the speed goal achieved from fewer tokens alone.

Finish focused/full checks, obsolete-code search, real saved UI-data render checks,
and documented manual review. If credentials or baseline measurements are absent,
record the exact remaining live-performance gap; implementation may be complete,
but performance acceptance remains open. Record fixture provenance, commands,
durations, manual status, residual canonical-caption limitations and final task
status. Gate: `test_t77_findings_acceptance.py`.

## Research references and implementation boundaries

- [Typed JEV API](https://docs.typesafe.ai/api): Noul/Score answers and criteria;
  Choice is available but not required for multi-label membership here.
- [Parallel questions](https://docs.typesafe.ai/introduction): independent questions
  share state; dependent questions require a later request or speculative questions
  whose relevance code resolves afterward.
- [Pre-parsed extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook):
  code owns numeric spans and normalization; JEV supplies semantic judgments.
- [Known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13): keep
  arithmetic in code, explicit state references and bounded relevant context.
- [Model context limits](https://docs.typesafe.ai/models): validate per-request
  and per-question limits against the pinned model; local character bounds are
  conservative application policy, not a claim of exact provider token counts.

The implementation must recheck the live API contract/model limits before a live
probe. This plan defines the product direction and bounded tasks; reported default
thresholds/caps are starting settings to validate, not established accuracy results.
