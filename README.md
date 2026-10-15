# ProfitLab

ProfitLab is a local, inspectable SEC earnings-research workspace. Its only supported
workflow is the fresh eight-stage V2 pipeline: visible source, outline, section score,
chunk, chunk score, quote-backed findings, structured facts, and independent evaluation.
Previous run data and the historical flat pipeline are unsupported.

V2 storage is fresh-only. If `data/v2/` already contains data created by an earlier
ProfitLab build, the application refuses to open it and leaves it unchanged. To discard
that unsupported local data and start again, stop ProfitLab and run:

```sh
rm -rf data/v2
```

If `PROFITLAB_DATA_DIR` is set, replace `data` with that directory. There is no
migration, export, compatibility, or recovery path for prior V2 databases.

Requires Python 3.12 and uv.

```sh
uv sync --locked
uv run profitlab serve
```

Open http://127.0.0.1:8000/. Enter a ticker and configure `SEC_USER_AGENT` with a real
contact email before creating a SEC filing run. Outline/findings and Jev scoring also require `LLM_API_KEY` and
`TYPESAFE_API_KEY`; no provider call is made until a run is created.

Open **Pipeline → Findings** to inspect every published quote and jump to its canonical
visible source line. Open **Evaluate** to compare that discovery output with Company
Facts loaded only after findings are sealed. Provider diagnostics remain on each stage's
**Inspect sanitized provider trace** page.

Discovery runs from **Source → Outline → Sections → Chunks → Evidence → Findings**.
Source saves numbered visible filing lines; Outline adds source-ranged navigation
topics. Sections ranks those descriptors with Jev, Chunks divides selected sections
into bounded core ranges with separate overlap context, and Evidence ranks and
retains a bounded set of chunks for Findings.

There are **three numeric finding types and five retrieval targets**:

- **Annual profit/net income or loss:** the annual shareholder earnings amount
  helps describe the company’s earnings level (annual profit type).
- **Diluted EPS:** annual diluted earnings per share gives the earnings amount per
  common share (diluted EPS type).
- **Annual diluted weighted-average shares:** the EPS denominator context helps
  interpret per-share earnings, not year-end shares outstanding (diluted shares type).
- **Earnings-change explanations:** help locate context for why earnings changed;
  no dedicated published output type.
- **Restatement/comparability passages:** help locate context for whether periods
  can be compared; no dedicated published output type.

Retrieval relevance is a search signal, not financial correctness or published
evidence. Findings validates exact source quotes and amounts before publication,
JEV assigns source lines to fixed concepts, attaches bounded context and ranks bundles.
Only selected eligible bundles reach LLM conversion; there is no later type classifier.
The pipeline extracts reported values; it does not compute EPS from profit and shares.

**What Findings delivers:** a list of reported numbers sought for the filing’s
current fiscal year. Each finding includes an amount, exact filing quote,
source-line link, fixed concept, and selected bundle/context provenance. Period, unit, attribution,
and limitations accompany it when supported; unclear fields remain unresolved.
Illustrative finding: **Diluted EPS · 2025 · $6.20**, backed by a quoted filing row
and source link (an example, not saved run data). Three types does not mean exactly
three findings: several numbers, missing concepts, unresolved metadata, or an empty result
are possible. Earnings-change and comparability passages provide context without
separate narrative findings. Source validation does not establish financial
correctness; independent comparison comes later in Evaluate.

Findings exposes seven stations: Candidates → Assign lines → Attach context →
Rank/select → Convert → Validate → Seal. Saved phase pages include losing bundles,
context roles, eligibility/omission reasons, request checkpoints and source links.
Validation binds the displayed Decimal/sign/span to selected evidence; metadata
references establish provenance rather than financial interpretation. Accepted
findings survive one bounded repair. Facts starts only after an atomic completed
or partial seal; failure/cancellation cannot publish a subset. Phase accounting
separates JEV assignment/context/rank and LLM conversion/repair, accumulates paid
work across resumed attempts, and records cache reuse separately. Phase steps
show the current attempt. Version cohorts include the complete Findings policy. JEV defaults to pinned
`jev-1.13.0`; Findings requires a verified pinned model (`jev-1.13.0` or
`jev-1.14.0`), so an explicit `jev-latest` override fails before dispatch.
Local V2 storage is fresh-only schema 76; older databases require a scoped reset.

Run checks with:

```sh
uv run pytest
uv run ruff check .
```

See [PROGRESS.md](docs/PROGRESS.md) for current status,
[PIPELINE_PAGE_DESIGN.md](docs/PIPELINE_PAGE_DESIGN.md) for the UI brief,
[PIPELINE_IMPROVEMENT_TASKS.md](docs/PIPELINE_IMPROVEMENT_TASKS.md) for the UI task
register, and [TASKS.md](docs/TASKS.md) for implementation history and task policy.
