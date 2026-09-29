# T35 evaluation decision: exact match is a narrow audit, not the discovery score

Decision date: 2026-09-24.  This review uses persisted live V2 runs only.  It
does not replay a provider request, alter a finding, or treat a Company Facts
record as input to discovery.

## Reviewed sample and provenance

| Run | Ticker | SEC accession | Filing | Reviewed output |
| --- | --- | --- | --- | --- |
| `v2-b95f2d36e162` | DV | `0001104659-26-020499` | 2025 10-K | 3 facts, 3 findings, 2 scale-aware pairs, 1 duplicate-oracle result |
| `v2-833668489686` | NOEM | `0001213900-26-027784` | 2025 10-K | 1 fact, 6 findings, 1 exact pair, 2 additional values, 3 unsupported findings |
| `v2-36c40a279e2b` | TRC | `0001628280-26-019685` | 2025 10-K | 4 raw facts / 3 configured slots, 3 findings, 1 exact pair, 1 miss, 1 duplicate-oracle result |

The accession, source hash, canonical lines, finding quotation, Company Facts
payload hash, and comparison card remain in each local run.  The source sample
therefore spans three issuers and three accessions, as required; it is not a
population estimate.

## What the raw comparison actually measured

The old evaluator's comparator was **SEC Company Facts, annual (`fp=FY`), same
10-K accession and report end, exact Decimal, and literal unit string**.  Its
reported expected-fact count deduplicated only `(metric, period_end)`, while
the matching loop could still encounter two concepts assigned to that metric.
It did not establish that a visible finding had the same attribution or that a
visible scale had been normalized.

Across the sample there were seven configured metric/period slots (DV 3, NOEM
1, TRC 3), nine raw Company Facts rows, two deterministic exact results, two
Jev scale-aware results, two `ambiguous_duplicate` results, one
`structured_fact_missed`, two additional visible values, and three unsupported
findings.  These overlap as cards rather than as a single confusion matrix, so
they are diagnostic counts, not precision or recall.

| Reviewed class | Count | Representative evidence | Interpretation |
| --- | ---: | --- | --- |
| Exact Decimal / compatible unit and period | 2 | NOEM line 854: `$1,652,360`; TRC line 705: `26,949,278` | Valid narrow exact audit. |
| Visible scale or lexical unit difference | 2 | DV lines 1043/1046: `$0.30`, `166,683`, with thousands-scale context | The values were independently confirmed scale-aware, but are not deterministic exact values. |
| Duplicate or conflicting Company Facts concepts | 2 | DV reports `NetIncomeLoss` and `ProfitLoss` as $50.650m; TRC lines 595/597 distinguish $71k net income and $75k attributable to common stockholders | Not a discovery failure.  The former is a duplicate oracle; the latter exposes attribution ambiguity. |
| Source-selection / extraction miss | 1 | TRC has a zero diluted-EPS Company Facts record and no quote-backed diluted-EPS finding | A candidate retrieval/extraction gap, pending direct filing review; count it only when the oracle is eligible. |
| Oracle unavailable for visible metric | 2 | NOEM lines 856/858 give $0.17 per share for two share classes, but no matching diluted-EPS Company Facts row was normalized | A false positive if accepted as configured diluted-EPS evidence; otherwise preserve it as an unscored diagnostic. |
| Unsupported / non-target visible values | 3 | NOEM lines 757, 855, 857 | Evidence is preserved, but an accepted claim that assumes such a value covers a configured target is a false positive. |

Every non-exact reviewed record has one of the classes above.  In particular,
the two duplicate-oracle cards and NOEM's unavailable EPS comparator must not
be converted into discovery misses.

## Oracle audit

Company Facts is suitable as an independent **filing-scoped annual numeric
oracle** only after all of the following are true:

1. the fact is from the selected accession, form `10-K`, fiscal period `FY`,
   report-end date, and an approximately annual duration;
2. exactly one preferred concept is selected for the configured metric (a
   fallback concept is used only when the preferred concept has no eligible
   row);
3. the finding identifies the same metric, fiscal year, attribution, and a
   normalized unit/scale; and
4. the visible quote establishes the selected amount, rather than merely a
   number in a multi-year or multi-attribution row.

Company Facts is not an appropriate exact oracle for share-class-specific EPS,
facts absent from the selected accession, unknown attribution, or values whose
visible scale has not been mechanically normalized.  A matching decimal alone
is insufficient in those cases.

## Alternatives considered

**A. Improve discovery and metadata, retaining the old score.**  Improve
selection/extraction for source misses, require table-header and attribution
capture, and normalize visible unit/scale.  This reduces false negatives but
would still call incomparable facts misses and would hide an invalid
denominator.

**B. Replace exact match with a tolerance or semantic-review score.**  A
tolerance could absorb rounding and scale, and a reviewer could judge the
source range.  Used alone, this risks turning a different share class,
attribution, or metric into a match; it is unsuitable as the primary automated
discovery score.

**Chosen: both, with separate measures.**  Keep strict exact matching only for
eligible, normalized audit units.  Add a reviewed semantic/source-range
outcome for otherwise comparable evidence, but do not merge it into strict
exact results.  Mark absent, duplicate, conflicting, or attribution-unknown
oracle pairs as *incomparable*, excluded from the discovery denominator.
Scale-aware Jev remains a separately labelled post-seal aid, never a rewrite of
the finding or Company Facts value.

## Approved metric contract

The next scorecard must state this contract on every result:

| Field | Definition |
| --- | --- |
| Oracle | SEC Company Facts JSON, selected filing accession / annual period, with one ordered preferred concept per metric |
| Scope | Quote-backed finding from the selected primary 10-K visible HTML; one configured metric, fiscal year, and attribution |
| Normalization | Decimal only after explicit visible unit/scale normalization; no float tolerance or inferred conversion |
| Strict-exact denominator | Eligible expected audit units: unique `(metric, fiscal year, attribution)` facts with a single selected oracle and a finding whose period/unit/scale/attribution are resolved |
| Semantic-review denominator | Reviewed eligible non-exact source/fact pairs, reported separately from strict exact |
| Exclusions | Duplicate/conflicting concepts, unknown attribution, unresolved period/unit/scale, and invalid quote. An accepted unsupported/missing target mapping is a false positive, not an exclusion. |

Strict-exact false positives include an accepted value whose assumed configured
tag/concept mapping is absent or wrong; the absence is not an oracle ambiguity.
Different concepts, share classes, or annual columns must not be silently
conflated into a match. Strict-exact false negatives would penalize a correctly
quoted value reported in thousands or under a lexical unit alias.  The separate
semantic outcome makes both risks visible instead of optimizing either score.

## T36 clarification (2026-09-24)

The scorecard contract now counts an accepted `unsupported` finding as a false
positive alongside `additional_visible_value`. “Incomparable” is reserved for a
case where the selected oracle cannot decide the claim fairly (for example a
duplicate/conflicting fact, unresolved period/unit/scale, or attribution that is
not established). It must not hide a finding accepted on the incorrect assumption
that it was covered by the configured Company Facts tags.

## Implementation plan and regression boundary

This task changes the Company Facts normalizer now: concept entries for a
metric are ordered fallbacks, so `NetIncomeLoss` prevents a same-period
`ProfitLoss` row from creating a second expected fact.  `tests/task_gates/test_t35.py`
uses the reviewed TRC accession values to lock that rule and locks the DV
thousands-of-shares case as non-exact until explicit normalization exists.

T36 will introduce the persisted, versioned eligible/incomparable review unit
and a scorecard that excludes ineligible values from its denominator. The current
UI's historical cards remain diagnostic records; they are not retrospectively
relabelled or aggregated under this new contract.
