# V3 G6 post-seal comparison cohort

Use `uv run profitlab v3 score cohort.json` only after every compared run is
sealed. The JSON is stored exclusively in V3’s experiment database and is never
sent to a provider. `required_ranges` are reviewer-entered, post-seal coverage
references—not graph targets or prompt material.

The cohort must use `rubric_version` `g6-post-seal-v1`, set `held_out` to `true`,
and contain all three frozen methods for each case: `graph`, `v2_packet`, and
`bounded_window`. Each case attaches to an existing V3 experiment only to reuse its
immutable canonical source for exact range validation. The V2 packet artifact is a
frozen export of an already-finished V2 run; the scorer never opens V2 storage.

```json
{
  "schema_version": 3,
  "cohort_id": "cohort-0123456789abcdef",
  "rubric_version": "g6-post-seal-v1",
  "configuration_id": "frozen-graph-v4-window-v1",
  "held_out": true,
  "created_at": "2026-09-27T12:00:00Z",
  "cases": [{
    "schema_version": 3,
    "case_id": "case-01",
    "experiment_id": "v3-0123456789abcdef",
    "question": "The exact sealed experiment question",
    "required_ranges": [{
      "schema_version": 2,
      "document_id": "v3-document-example",
      "source_hash": "<64 lowercase hex characters>",
      "start_line": 42,
      "end_line": 42,
      "start_character": null,
      "end_character": null
    }],
    "artifacts": [{
      "schema_version": 3,
      "artifact_id": "graph-sealed-result",
      "method": "graph",
      "source_ranges": ["<SourceRange object>"],
      "citation_ranges": ["<SourceRange object>"],
      "graph_path_ids": ["path-0123456789abcdef"],
      "answer_support": "supported",
      "ambiguity_handling": "handled",
      "provider_calls": 2,
      "provider_input_tokens": 100,
      "provider_output_tokens": 20,
      "latency_seconds": 1.2,
      "notes": "Optional reviewer note"
    }]
  }]
}
```

For `v2_packet` and `bounded_window`, `graph_path_ids` must be empty. The scorer
checks source identity and range bounds for every method; graph citation ranges also
must be contained by their selected persisted graph paths. It reports source coverage,
citation and path fidelity, reviewer support/ambiguity classifications, provider
calls/tokens, and latency. Open `/v3/comparisons/<cohort-id>` after scoring to inspect
the result. Do not alter prompts, relation vocabulary, graph budgets, or the model
while collecting one cohort.
