# T39 recall investigation — 2026-09-26

## Status

No T39 approach below is established as an improvement. This report records what was
actually run, what was observed, and which later code changes have **not** yet received
a fresh live run. Treat it as the starting point for the next agent; do not infer success
from local tests or from a design description.

The product goal remains narrow: discover quote-backed annual net income/profit/loss,
diluted EPS, and diluted weighted-average shares from a filing. The result must be a
source quote whose number mechanically matches the published Decimal. Context can
explain a table header, year, or scale, but cannot be the citation.

## Evidence and cohorts

The observations below come from `data/v2/profitlab-v2.sqlite3`, chiefly the live runs
created on 2026-09-24. Counts are small and are diagnostic, not a benchmark.

| Cohort | Runs examined | Active discovery design | Observed outcome |
| --- | ---: | --- | --- |
| `v2-756e7174db79ee8a` | 12 complete chunk-score runs | Adaptive Jev role, eligibility, and context-sufficiency gate after flat chunk scoring | Flat Jev selected 8.92 chunks/run; adaptive output retained 1.67. Findings averaged 1.0/run. Evaluation had 23 structured-fact misses, 8 scale-aware matches, and 0 exact matches. |
| `v2-9d8a954a0195dc26` | 5 terminal runs: HCXY, NBHC, ATLC, PGC, SKT | Deterministic packets followed by per-target packet routing and target-specific extraction | Flat Jev selected 10.4 chunks/run; packet routing retained 4.6. Findings averaged 2.2/run, with 6 rejected proposals/run; 13 misses, 2 scale-aware matches, and 0 exact matches. |
| `v2-063ad24354d04cbb` | CQP, VLOSU, RANI inspected in detail; database has more terminal runs | Flat Jev chunks, all-claim extraction once per chunk, then Jev type classification | This was not good enough: CQP published unrelated derivatives, VLOSU published 23 values from one statement, and RANI timed out in Findings. |

The current database summary for `v2-063ad24354d04cbb` is not a clean controlled
measurement: it contains 15 runs, 10 terminal runs, and code/server changes occurred
during development. Its populated finding summaries average 4.33 retained chunks, 4.33
extraction calls, and 14.67 rejected proposals. Do not use it to claim a trend.

### 4. Controlled IWAL source-row replay

On 2026-09-26, fresh run `v2-5e82c4ba9063` used application revision
`t39-iwal-audit-v1` (version `v2-3432655c44f7a869`) against the pinned IWAL filing
`0001498372-26-000002`, whose canonical hash matches the checked-in replay case.
The fresh run makes the structural proposal audit available; reviewed rows themselves
were still never provider inputs.

| Expected source row | Flat retained | Sent | Proposed / quote valid | Type / published | Independent outcome |
| --- | --- | --- | --- | --- | --- |
| 291, net loss | yes | yes | yes / yes | annual profit / yes | exact match |
| 292, basic and diluted EPS | yes | yes | yes / yes | diluted EPS / yes | additional visible value |
| 293, weighted-average shares | yes | yes | yes / yes | diluted shares / yes | additional visible value |

The last two rows have no available Company Facts target in this filing, so their
evaluation disposition is not a source, proposal, validation, classification, or
publication failure. This small case establishes that the revised request/audit path
can preserve and publish its three reviewed rows; it does not demonstrate broader
precision or recall.

The same run recorded 109 source-context decisions: 88 completed and 21 explicit
budget partials after 36 Jev calls. All final roles were `uncertain`. Since those
decisions remain diagnostics and flat chunk retention delivered all three rows, the
experiment establishes neither semantic value nor a context-driven retrieval effect.
The immediate next diagnostic was to inspect the persisted completed/partial response
shape and expansion histories, without changing a prompt, threshold, retention rule,
or Findings input first.

### 5. Score-shape diagnostic replay

On 2026-09-27, `v2-10d253c64e2b` replayed the same 107 flat-retained IWAL cores
under application revision `t39-score-shape-v1` / version `v2-a3c9381780e9992a`.
It persisted the complete finite Jev answer vector alongside every completed
source-context decision. The request, thresholds, rings, expansion policy, flat
retention, and Findings inputs were unchanged.

The replay made 36 Jev calls and persisted 109 decisions: 88 completed, 21 explicit
request-budget partials; 69 completed cores were uncertain with sufficient context,
18 were uncertain with insufficient context, and one was evidence with sufficient
context. The evidence-labelled core was line 290, a heading/context line eligible
only for earnings-change and comparability—not a target value. The reviewed loss row
291 had sufficient context but evidence 0.64, just below the 0.65 role threshold,
and annual-profit eligibility 0.47. Rows 292 and 293 had evidence 0.62 and
diluted-shares eligibility 0.87, but were still role-uncertain. The two eligible,
insufficient first-pass candidates entered pass 1 after the final first-pass call and
became budget partials.

This identifies a response-calibration shape (near-threshold generic evidence plus
separate direct-type scores) but does not establish a safe threshold change, a useful
eligibility rule, or retrieval improvement. A same-source diagnostic replay that
accidentally inherited application revision `0.1.0` is retained as
`v2-8c12a9fdc6eb` but explicitly excluded from controlled cohorts.

## What was tried

### 1. Adaptive source eligibility after flat chunk scoring

The first T39 design asked Jev to label canonical blocks as evidence, contextual, or
neither; estimate per-target eligibility; and request wider local context if necessary.
Only direct, context-sufficient evidence was allowed through to Findings. A fallback
restored the flat selection when adaptive output was empty.

Why it failed:

- It made an uncertain semantic judgement an early recall gate.
- In the 12-run sample it mostly produced `neither`, uncertain, or ineligible results.
- The active evidence set collapsed from about nine flat-selected chunks to fewer than
  two chunks per run. This explained the decline in findings before extraction began.

Lesson: source interpretation/eligibility cannot be a required precondition for
retrieval. Record it as diagnostics only if it is retained at all.

### 2. Target-ranked evidence packets

Packets were built deterministically around paragraph, list, and table-row cores, with
visible heading/caption/preamble/adjacent-row context. Jev then ranked packets for each
target and a bounded per-target reserve was sent to three target-specific extraction
requests.

Why it failed:

- The bounded ranking once again discarded useful chunk content before extraction.
- A target prompt incorrectly encouraged semantic relabelling. For example HCXY emitted
  basic EPS rows as annual profit candidates.
- ATLC and NBHC exposed a protocol issue: models sometimes returned numeric JSON amounts
  rather than Decimal strings, producing many avoidable validation failures.

Lesson: packets are useful as a source-layout view, but ranking packets is another
recall gate. Do not conflate a retrieval score with financial type eligibility.

### 3. Flat chunks plus one all-claim LLM extraction per selected chunk

The active replacement restored flat `chunk_score` selection and kept packets only as
deterministic citable cores with context. It made one concurrent LLM request per
selected chunk, asked for untyped numeric claims, mechanically grounded each amount to
the quote, then used Jev to assign a product type.

What worked:

- It restored the flat chunk boundary instead of the adaptive/packet-retention gate.
- VLOSU's statement of operations was present in the selected chunk: lines 1148–1154
  contain net income, weighted-average share rows, and per-share rows. The run did
  publish an exact annual-net-income match (`5,778,750`).
- Exact quote/amount validation continued to stop uncited prose.

What failed:

- The request still contained a large mixed table/chunk. VLOSU published 23 values,
  including general operating costs, trust-account interest, and IPO transaction costs.
  These were quote-valid but not product claims.
- CQP selected one chunk that included correct `Net income` and `Basic and diluted net
  income per common unit` rows, but the model chose derivative rows later in the same
  chunk. The failure was therefore not solely chunk retrieval.
- CQP rejected 23 proposals with `source line must be an integer core evidence line`.
  That live run parsed every JSON integer as `Decimal`, including `source_line`.
- RANI failed Findings with `Request timed out`; increasing simultaneous full-chunk LLM
  work is not a safe scaling strategy.

Lesson: an exact quote validator proves that a number appears in a line. It does not
prove the line is a desired financial metric. “All numeric claims” is too broad when
the artifact sent to the LLM is a wide financial-statement chunk.

## Changes currently in the working tree, not yet live-verified

These changes were made after the bad runs above. They passed local tests but have no
fresh run evidence and must not be described as fixes yet.

1. JSON parser correction: fractional amounts parse as `Decimal`, while structural
   integers such as `source_line` stay integers.
2. Per-packet context: a core now carries its own labelled context rather than every
   packet in a chunk sharing a mixed table context.
3. Product boundary after classification: a quote-valid candidate classified as
   `unresolved` remains in diagnostics and is not published into evaluation.
4. Deterministic target-shaped core routing: only cores with visible net-income/loss/
   profit, EPS, or weighted-average-share wording are placed in an extraction request.
   This is intended as layout/vocabulary reduction, not Jev scoring or financial
   eligibility. It may improve precision but creates a new recall risk for uncommon
   labels.

The last item is deliberately provisional. It narrows the LLM input but has not shown
that it retains all required variants across filings.

## Important provenance warning

`version_id` is based on configured version components and
`PROFITLAB_APPLICATION_REVISION`; it is not a hash of the working tree. Multiple code
edits can therefore share a version ID if the application revision is not changed, and
a running server can execute older imported code. This happened during T39 iteration.

Before every live comparison:

1. Set a new explicit `PROFITLAB_APPLICATION_REVISION` for the candidate change.
2. Restart the server/process.
3. Record the run IDs and exact revision in this document or a new experiment ledger.
4. Compare only runs from the same revision and fixture/filing set.

## Recommended next experiment

Do not make another broad prompt-only adjustment. First create a small fixed replay
set from the observed filings, at minimum:

- CQP: correct net-income and basic-and-diluted-EPS rows are in a large selected table
  together with cash-flow/debt/derivative rows.
- VLOSU: statement-of-operations rows 1148–1154 contain the desired net income, EPS,
  and share evidence beside generic operating/income rows.
- ATLC and NBHC: numeric JSON amount protocol cases.
- RANI: timeout/concurrency case.

For each filing, persist an expected *source-row set* before measuring final facts:
which selected chunks contain it, whether it reaches the extraction request, whether it
is proposed, quote-validates, classifies, publishes, and matches an independent fact.
This makes the first loss point observable. A metric count alone cannot distinguish a
retrieval miss, prompt miss, parser failure, type-classifier rejection, or evaluator
mismatch.

Only then choose between two explicitly measured designs:

1. **Target-shaped deterministic packet batches.** Build packets without semantic
   scoring; batch only the target-shaped cores and their local headers into one small
   LLM request per chunk. Measure lexical-variant recall before trusting it.
2. **Cheap Jev candidate routing.** If deterministic vocabulary recall is inadequate,
   use Jev to mark packet candidates but retain a wide, measured uncertainty reserve.
   It must not be a top-N per-target gate, and it must be evaluated against the fixed
   source-row set before being made active.

Do not reintroduce adaptive eligibility, top-N packet routing, or target-specific
extraction labels without an experiment showing that they improve source-row recall on
the replay set.

## Fixed multi-filing source-row replay set

The checked-in `t39-source-row-expectations-v2` set fixes the source identity before
any candidate design is measured.  It contains the controlled IWAL case plus exactly
the five filings named above: CQP, VLOSU (now SEC ticker VLOS), ATLC, NBHC, and RANI. Each case pins its
ticker, accession, raw-HTML SHA-256, and three reviewed current-year rows (annual
profit/loss, diluted EPS, and diluted shares).  The hashes were reconstructed from the
SEC primary HTML on 2026-09-27 using the production `visible-html-1` canonicalizer.

The rows are review-only, post-run diagnostics.  A changed/re-filed source does not
match the case, and the set is never supplied to source retrieval, Jev, the Findings
LLM, or evaluation.  CQP and VLOSU retain their mixed-table/noise failure modes; ATLC
and NBHC retain the decimal JSON protocol cases; RANI retains the Findings timeout
case.  A controlled replay must record the first loss point for every row before any
calibrated role, eligibility, routing, prompt, or retention change is considered.

### First fixed-set replay: CQP

On 2026-09-27, fresh run `v2-b77c75aa8adc` used application revision
`t39-fixed-replay-v1` (version `v2-5e400dda6f984ca5`) against pinned CQP accession
`0001383650-26-000005`; its canonical source hash matched the fixed set. All three
reviewed rows (292–294) were flat-retained, sent to Findings, proposed,
quote-validated, type-classified, and published. This proves no source-row loss for
the CQP mixed-table case on the current flat path.

The run published annual profit `2987`, diluted EPS `5.17`, and diluted shares `484.0`.
Its independent comparisons did not exact-match: the annual Company Facts value is
scale-incompatible with the visible statement value and the other two are additional
visible values under the current target contract. This is an evaluation/scale boundary,
not a source, proposal, quote, classification, or publication failure. The run made
36 source-context calls for 250 retained lines and recorded 254 decisions, including
174 explicit request-budget partials. It does not establish context usefulness or a
candidate strategy improvement.

## Local checks at the time of writing

The working tree passed `uv run pytest -q` with **25 passed** (one existing Starlette /
AnyIO deprecation warning), `uv run ruff check .`, and `git diff --check`. These are
contract checks only; they are not live quality evidence.
