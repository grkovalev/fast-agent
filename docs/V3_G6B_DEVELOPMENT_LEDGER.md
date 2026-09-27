# V3 G6b development cohort ledger

G6b evaluates one fixed graph configuration on new development filings. It is not
the held-out G6c three-method comparison: its contract is
`g6b-development-v1`, requires `held_out: false`, and contains exactly one sealed
V3 graph run per case. Do not use FGN, CRVL, SPRO, WOR, or MSFT.

Attach SEC/reviewer `ground_truth_ranges` only after the graph run has finished.
The scorer checks that every range belongs to, and can be sliced from, the saved
canonical document. It reads the persisted graph action/path/answer audit to report
ground-truth coverage, exact answer citations, reviewer support and ambiguity,
trajectory, calls, token availability, and latency. It performs no provider calls
and has no graph-service call path.

The configuration object must exactly match every saved experiment's application
revision, model, prompt version, and budgets. This prevents a development ledger
from silently mixing configurations.

```json
{
  "schema_version": 3,
  "cohort_id": "development-cohort-0123456789abcdef",
  "ledger_version": "g6b-development-v1",
  "held_out": false,
  "configuration_id": "fixed-evidence-graph-v5",
  "configuration": {
    "schema_version": 3,
    "application_revision": "revision-fixed-before-cohort",
    "model": "configured-model",
    "prompt_version": "evidence-graph-v5",
    "budgets": {"max_actions": 12, "max_source_characters": 120000, "max_wall_seconds": 300}
  },
  "created_at": "2026-09-27T12:00:00Z",
  "cases": [{
    "schema_version": 3,
    "case_id": "development-01",
    "experiment_id": "v3-0123456789abcdef",
    "question": "The exact sealed experiment question",
    "ground_truth_ranges": ["<SourceRange object from this experiment's canonical document>"],
    "answer_support": "supported",
    "ambiguity_handling": "handled"
  }]
}
```

Run `uv run profitlab v3 score-development cohort.json`. The record is persisted
only in the V3 repository. Inspect it at
`/v3/development-ledgers/<cohort-id>`; the existing `/v3/comparisons/<cohort-id>`
remains G6c-only.
