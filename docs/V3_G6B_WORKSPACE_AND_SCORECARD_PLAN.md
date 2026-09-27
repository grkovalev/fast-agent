# V3 workspace, evaluation, and scorecard plan

## Product-direction update — V2/V3 comparable research workspace

This section supersedes the campaign-operator presentation described below. The
immediate objective is to test the V3 source-grounded approach on **the same fixed
annual profit/net income, diluted EPS, and diluted weighted-average shares question
as V2**, not to expose arbitrary-question research controls. Arbitrary questions are
explicitly deferred until this comparison workflow is reliable and measured.

### Workspace shape

The application has two peer top-level tabs:

| Tab | Purpose | Storage and data boundary |
| --- | --- | --- |
| **V2** | Current production-style eight-stage earnings-research pipeline. | Existing V2 namespace and behavior. |
| **V3 experiment** | Same ticker/report question, evaluated as a source-grounded graph alternative. | `data/evidence-graph-experiment/` only; never reads or mutates V2 rows. |

The V3 landing page must mirror the useful V2 launch experience. It offers a manual
ticker, a random eligible report, and a bounded sequential batch of random eligible
reports. The only operator-selected input for a normal V3 report is its ticker (or
the batch count). The fixed question, model, prompts, graph configuration, and
version identity are server-owned and sealed. V3 random selection and batch records
must be V3-local; they may use live SEC discovery but must not query V2 run history or
reuse V2 batch rows.

### V3 report workspace

Each V3 report presents a compact, refresh-safe stage rail analogous to V2. These
are V3 stages, not renamed V2 stages:

1. **Source** — live SEC filing acquisition and immutable canonical visible source.
2. **Explore** — bounded source-window graph actions, continuations, budgets, and
   explicit partial/exhausted states.
3. **Evidence paths** — accepted, uncertain, and rejected nodes/edges with exact
   source ranges; generated labels remain visibly non-source metadata.
4. **Findings** — only source-cited graph answer claims projected into the three
   fixed metric slots. A value/period/unit/attribution that cannot be established
   from the cited graph path remains unresolved; no V2 finding is copied in.
5. **Ground truth** — independently retrieve and normalize V3-local SEC Company
   Facts only after graph exploration and findings are sealed.
6. **Evaluate** — compare V3 findings with V3-local ground truth and retain
   source/path links for every state.

The stage rail is a navigation and lifecycle surface, not a claim that graph evidence
is linear. A selected stage opens the existing bounded explorer/source view or its
corresponding findings, ground-truth, and evaluation detail. Running/failed/partial
states must be as explicit as in V2 and survive refresh/restart.

### Comparable evaluation and scorecard

V3 must calculate the same macro metrics and denominator accounting shown by V2 for
the fixed three-metric experiment: expected facts, exact matches, scale-aware
equivalents (clearly separated from exact), misses, additional visible values,
unsupported/unresolved output, value/period accuracy, source coverage, provider
calls/tokens, and latency. It may additionally report graph-specific diagnostics
(frontier state, action/continuation count, path coverage, citation validity), but
must not substitute them for the V2-comparable metrics.

Ground truth and evaluation are post-seal, V3-local records. They never enter a graph
exploration or answer request. The V3 scorecard groups only runs with the same sealed
V3 configuration/version, accounts for all selected/failed/partial runs, and links
each aggregate cell to its V3 report, exact visible source, graph path, and ground
truth record. It must not silently pool V2 and V3 or claim a population-accuracy
result from a development cohort.

### Delivery order

1. Add the V2/V3 tab shell and restore V3 manual, random, and sequential random-batch
   launch with V3-local persistence and one-at-a-time execution.
2. Convert the V3 report status/explorer into the six-stage V3 workspace, preserving
   existing graph provenance and explicit terminal states.
3. Add source-cited fixed-metric V3 findings, then post-seal V3-local Company Facts
   and the V2-compatible per-report evaluation contract.
4. Add the selected-configuration V3 scorecard with V2-comparable macro metrics and
   graph diagnostics. Only after a measured fixed-question cohort review may the team
   decide whether to add arbitrary questions.

## Purpose

Make the isolated V3 experiment usable as a development workflow: a reviewer can
start a graph run from the local UI, inspect its bounded trajectory while it is
running or after it seals, attach reviewed SEC evidence only after it seals, and
read a cohort scorecard with links back to every case.

This borrows the useful *experience* of V2's run workspace and evaluation
scorecard. It does **not** borrow V2's source, Findings, Company Facts,
comparisons, or evaluator inputs. V3 remains under
`data/evidence-graph-experiment/`; its source/graph/answer requests remain unable
to read post-seal review records.

## Why this is a new bounded workstream

The current V3 UI is an explorer only. It lists and opens persisted experiments,
but `profitlab v3 answer TICKER QUESTION` is the only run launcher. The existing
`g6b-development-v1` ledger is a correct post-run scorer and report, but it is
file-driven and case-oriented rather than a review workflow or cross-case
scorecard.

The word **accuracy** is deliberately not used as an automatic property of an
answer. For this generic, question-conditioned graph, a score exists only after an
independent reviewer attaches exact canonical SEC ranges and records answer support
and ambiguity handling. Before that, the UI may show provenance and status but must
say “not evaluated,” not imply correctness.

## Non-negotiable boundaries

- G6b is development-only. Every run uses a fresh development filing; FGN, CRVL,
  SPRO, WOR, and MSFT remain excluded. G6c is still deferred and remains a separate
  `held_out: true`, three-method comparison.
- A campaign's full configuration and question are sealed before its first run. The
  UI cannot change model, prompt, relation vocabulary, source-window size/overlap,
  action/source/wall-time budgets, continuation/stopping policy, or application
  revision per case.
- The application validates source identity, bounds, fixed configuration, terminal
  state, and exact ranges only. It must not infer facts from headings, tables,
  values, tickers, accessions, or document layout.
- Reviewer/SEC ranges, support labels, ambiguity labels, notes, scorecard values,
  and any G6c record must be absent from every V3 exploration and answer request.
  Attaching or rescoring must make no provider call.
- A run may fail or end `partial`, `exhausted`, or `budget_exhausted`. Those are
  first-class inspectable outcomes; the UI must not fabricate an answer or a score.
- Do not alter V2 pipeline semantics, tables, stored data, evaluation behavior, or
  scorecard denominators. Shared navigation may expose the V2 and V3 tabs, but every
  V3 run, batch, fact, finding, and evaluation record remains in V3 storage.

## V2 patterns to retain and adapt

| V2 experience | G6b adaptation |
| --- | --- |
| Explicit fresh-run form and durable workspace status | A V3-only campaign/run form, background task status, errors, refresh-safe terminal inspection, and direct explorer link. |
| Configuration cohort selector | A development campaign chosen explicitly; only one sealed full V3 configuration can populate its scorecard. No default that silently mixes configurations. |
| Included/excluded run ledger with reasons | Every campaign run appears as awaiting completion, awaiting review, included, or excluded with a precise reason. |
| Matrix/counts with visible denominators and clickable records | Coverage/support/limitation/citation/trajectory summaries with case links and stated denominators. No TP/FP/FN or precision/recall unless a later protocol introduces independently reviewed positive and negative denominators. |
| No raw provider payload as the review surface | Use canonical-line, graph-path, action/frontier, and reviewer-range links; preserve provider payload redaction. |

## G6b.1 — sealed campaign and V3 run workspace

**Goal:** create a V3-only, local UI workflow that can safely start and follow new
development graph runs without weakening fixed-configuration boundaries.

**Design:** add an isolated campaign contract/repository namespace. Before a run,
the operator creates one campaign containing its question and a complete immutable
configuration snapshot. The snapshot must cover every V3 request/traversal-affecting
input, including application revision, selected model, all prompt/request-schema
versions, relation vocabulary, source-window size and overlap, action/source/wall
budgets, and stopping/continuation policy version. Give the strengthened contract a
new version rather than relabeling a persisted `g6b-development-v1` record.

The V3 workspace may submit only ticker plus the selected campaign. It starts an
isolated `V3GraphService.answer_live` task, records a V3-only lifecycle audit, and
redirects to a status page. The server, not form fields, supplies the campaign
question and configuration. The launch must reject a non-ready SEC/provider setup,
duplicate active run for the campaign/ticker, excluded ticker, and any runtime
configuration mismatch before provider work begins. A completed run links into the
existing provenance explorer; a failed one exposes a redacted, actionable failure
without pretending it sealed.

**Acceptance:** one manually entered eligible development ticker can be launched
from `/v3/...`, remains visibly isolated from V2, progresses to a terminal state,
and opens its canonical source/action/path inspection. A user cannot vary a fixed
campaign setting or use an excluded ticker. Restart/reload preserves persisted
terminal state; active work is recovered or explicitly marked interrupted rather
than misrepresented as completed.

**Focused contracts:** V3-only repository writes; no V2 repository construction or
access; server-owned campaign configuration; rejection before any SEC/provider call;
one active campaign run; redacted failure persistence; terminal manifest/action
inspection; and every provider payload excludes campaign/review/evaluation data.

## G6b.2 — terminal-only review and ledger authoring

**Goal:** replace hand-authored cohort JSON with a reviewer workflow that creates
the existing deterministic G6b ledger input after, and only after, a run seals.

**Design:** from a sealed campaign case, a reviewer opens the immutable canonical
document and selects/enters exact `SourceRange`s, support, ambiguity handling, and
optional notes. The server round-trips each range against that experiment's document
and source hash. It neither edits graph/answer records nor sends these fields to the
graph service. A case is reviewable only once it has a terminal manifest snapshot;
failed/unsealed runs remain visibly in the campaign accounting but cannot receive
ground truth.

The workflow creates an immutable post-seal review record and then derives the
G6b ledger contract/report through the deterministic scorer. It must expose the
same result that the CLI produces for equivalent reviewed data. Existing
`g6b-development-v1` records remain readable; any new fuller campaign identity is
versioned and must not silently reinterpret old reports.

**Acceptance:** a reviewer can create one exact canonical range, see invalid,
cross-document, and non-terminal submissions rejected, submit a review, and inspect
the persisted ledger without a provider call. The experiment explorer remains
unchanged and no answer request contains the review data.

**Focused contracts:** terminal-only gate; exact range/source-hash validation;
immutable review persistence; no graph/answer mutation; no provider call;
equivalence with the deterministic scorer; and explicit separation from G6c tables,
routes, and `held_out: true` contracts.

## G6b.3 — development scorecard and diagnostic navigation

**Goal:** provide the cross-case evaluation experience requested without claiming a
held-out result or unsupported statistical accuracy.

**Design:** add a V3 development-scorecard page scoped to one selected sealed
campaign/configuration. It reports, with denominators:

- reviewed-ground-truth coverage (reviewed ranges covered / reviewed ranges);
- exact-citation-valid cases (valid / reviewed cases);
- support and ambiguity disposition counts (including forced and unresolved);
- terminal-frontier distribution and action/continuation counts;
- provider calls, available token accounting, and latency, with unavailable values
  shown as unavailable rather than zero; and
- case accounting: all campaign cases, each marked running, terminal-awaiting-review,
  included, or excluded with a reason.

Every aggregate cell links to the case's V3 explorer and its canonical reviewed
ranges. The page must label itself “G6b development evaluation,” state its question
and complete configuration identity, state that reviewer ranges were attached
post-seal, and warn that it is neither population accuracy nor the G6c comparison.
It must not merge campaigns, select a newest configuration by default, fabricate
precision/recall, or call providers on refresh.

**Acceptance:** a two-or-more-case fixture renders aggregate denominators, mixed
included/excluded states, unavailable telemetry, and links to each case. A reviewer
can navigate from a coverage/support/trajectory summary to an exact source and the
frontier responsible for it. G6c reports remain absent from this page.

**Focused contracts:** selected-campaign-only aggregation; full configuration
identity match; denominator and unavailable-telemetry correctness; all disposition
states; direct source/explorer links; no provider call on scorecard render or
rescore; and no G6b/G6c cross-read.

## Execution and evidence order

Implement and inspect one task at a time: G6b.1, then G6b.2, then G6b.3. Do not run
a development cohort until G6b.1 has frozen a campaign. After each run, attach
reviewed SEC evidence through G6b.2; only then use G6b.3 to inspect the cohort. A
configuration change requires a stated generic hypothesis, a new configuration
identity, and a fresh development slice. It never retroactively changes a campaign
or authorizes G6c.

For each task, run the focused V3 contracts, the full suite, Ruff, and `git diff
--check`; do not use browser automation. Manual verification is local only through
`uv run profitlab serve` and the V3 routes introduced by that task. Live SEC/provider
work requires configured credentials and must be recorded as development evidence,
not substituted by fixtures.
