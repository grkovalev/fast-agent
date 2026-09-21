# ProfitLab

Local, inspectable earnings growth research. Company earnings per share; stock-price returns are not included.

T15 is implemented: the isolated V2 workspace now creates a canonical visible filing source with normalized line numbers and exact sanitized HTML anchors. The UI runs the implemented source stage directly; later stages remain visibly partial until implemented. Historical V1 runs remain separately readable.

Requires Python 3.12 and uv. From the repository root:

```sh
uv sync --locked
uv run profitlab serve
```

Open http://127.0.0.1:8000/. In **V2 workspace**, enter **DEMO**, select **Offline fixture**, and click **Create fresh V2 run**. The source stage runs immediately; open its canonical document to inspect numbered visible lines and exact HTML anchors. For a real filing, select **Live SEC filing** and enter a ticker after configuring `SEC_USER_AGENT`. Runtime summaries are stored locally.

The interface binds to `127.0.0.1:8000` by default. Demo and UI need no credentials or network after installation. Optionally copy `.env.example` to `.env`; configuration checks report presence only and do not probe external services. Never commit credentials.

The default model configuration is OpenAI API (`https://api.openai.com/v1`) with
`gpt-5.6-luna`, selected for low cost. Set `LLM_API_KEY` in your local `.env`
to your OpenAI API key. `LLM_BASE_URL` and `LLM_MODEL` remain configurable;
remove old blank assignments or use the values in `.env.example`. Configuration alone does not make paid requests. Only explicit live commands contact providers.
See [official model capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

```sh
uv run profitlab --help
uv run profitlab inspect demo-t02
uv run profitlab demo --through T02 --scenario two-years --run-id two-years-t02
uv run pytest
uv run ruff check .
```

Continue with [PROGRESS.md](docs/PROGRESS.md), [TASKS.md](docs/TASKS.md), and the [V2 implementation specification](docs/V2_IMPLEMENTATION_PLAN.md). The next task is T16: build the source-validated filing outline. Earlier V1 runs stay readable in their separate namespace.

```sh
uv run profitlab demo --through T04 --scenario two-years --run-id two-years-t04
uv run profitlab discover DEMO --years 4 --mode demo
uv run profitlab discover AAPL --years 4 --mode live
uv run profitlab doctor --live sec
```

Live discovery requires `SEC_USER_AGENT` with a real contact email. Tickers are trimmed,
uppercased, and class dots become hyphens (`brk.b` → `BRK-B`); no fuzzy matching.
Outcomes distinguish missing/ambiguous ticker, unsupported annual reports, and
service failure. Originals are selected by distinct report dates; 10-K/A metadata
is associated with its original and quarterly reports are excluded. Synthetic
documents have badges instead of invented SEC links. Two-year demos show partial
filing coverage without claiming four years.

All live attempts share a local process/thread rate limiter (default two requests
per second). Validated JSON cache entries include retrieval time and content hashes;
ticker entries expire after 24 hours and submissions after one hour. Timeouts,
retry count, response bytes and historical-file traversal are bounded. `Retry-After`
is respected; excessive waits fail visibly instead of bypassing SEC blocks.
The implementation follows the [SEC access policy](https://www.sec.gov/about/developer-resources)
and [submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

Open http://127.0.0.1:8000/runs/demo-t03/trace. Expand the failed fixture request
and read its complete redacted arguments/error, then follow the same call ID to
attempt 2. Full payload links also open standalone JSON or escaped viewers.
Filters include stage, actor, kind, provider, tool, errors, and payload/ID search.
These are scripted pipeline outcomes, with no invented model conversation.
Refresh preserves history. Server startup marks open spans interrupted; it does
not retry remote calls. Run only one local server, as required by this version.

```sh
uv run profitlab export demo-t03 --output ./exports/demo-t03
```

Use a new output directory. The trace-only export contains `trace.json`,
`events.jsonl`, and complete content-addressed `payloads/*.json`; portable reports
arrive in T16. TraceRecorder redacts before writing, including configured secret
values passed through `Settings.redactor()`, sensitive headers and URL credentials.
Service integrations must use this shared policy and avoid printing raw failures.

Saved source inspection (T05):

```sh
uv run profitlab demo --through T05 --run-id demo-t05
uv run profitlab stage <discovered-run-id> download
uv run profitlab stage <discovered-run-id> parse
```

Open `/runs/demo-t05/sources`, choose a table block, then click a value to
highlight that exact cell or **Row + column** to inspect its labels. Raw HTML is
saved unchanged; the viewer renders escaped source text and reconstructed tables.
Live progression accepts `--filing-id` to process one discovered filing. Existing
saved downloads and parsed artifacts are reused; failed operations remain in Trace.
Sources without an original anchor use a stable local source block, with no invented
page number. Synthetic sources have no SEC-original link.

Chunk inspection (T06):

```sh
uv run profitlab demo --through T06 --run-id demo-t06
uv run profitlab stage <parsed-run-id> chunk
```

Open `/runs/demo-t06/chunks`. Inspect **Prose overlap**, follow a primary block
link to its saved source, and use **Following chunk** to traverse table pieces.
The synthetic 2025 filing includes an intact table exceeding the target and a
large table split with repeated year/unit headers. Filter by filing, heading,
or estimated size. Earlier T06 runs have no screening decisions; T08 adds them below.

`CHUNK_TARGET_TOKENS=1500` and `CHUNK_OVERLAP_TOKENS=180` configure block-based
prose chunking. Tables can exceed the target. `CHUNK_REQUEST_BUDGET=24000`
includes `CHUNK_QUESTION_OVERHEAD=2000` reserved tokens and metadata, using a
conservative UTF-8 bytes/3 proxy; these are estimates, not measured Jev usage.
Oversized blocks or inseparable row groups fail explicitly without truncation.
Changed configurations save additional immutable chunk versions; earlier
versions remain inspectable. The safe budget is provisional until T07/T14.

Provider probes (T07):

```sh
uv run profitlab doctor --live jev
uv run profitlab doctor --live llm
uv run pytest tests/task_gates/test_t07.py
```

Each explicit live probe prints its saved trace URL, including on failure. Jev uses
`TYPESAFE_BASE_URL`, `TYPESAFE_MODEL`, and `TYPESAFE_API_KEY` independently of the
Chat Completions provider. `LLM_OUTPUT_MODE=tool` uses typed output tools;
`native` explicitly requests native JSON schema. Neither mode silently falls back.
For the default `gpt-5.6-luna` on the official OpenAI endpoint, the model factory
explicitly disables reasoning to permit Chat Completions function tools. Override
with `LLM_REASONING_EFFORT` when needed; other models/endpoints receive no automatic
reasoning override. The effective setting is visible in the trace. The live API
identified this restriction in a saved HTTP 400 response; the
[official model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
lists `none` among its supported reasoning efforts.
The LLM probe must call `read_probe` exactly once and return its marker as validated
output. No financial extraction or report writing is implemented by these probes.

`MAX_HTTP_ATTEMPTS=3` controls the single transport retry owner; SDK retries are
disabled. Jev 429/529 and transient server/transport errors use bounded exponential
backoff; authentication and request-validation failures stop immediately. Exhausted
LLM account quota stops immediately. `STRUCTURED_OUTPUT_REPAIRS=1` is a separate
validation budget. `PROVIDER_TIMEOUT=30`, `PROVIDER_TOTAL_TIMEOUT=120`, and
`PROVIDER_MAX_RESPONSE_BYTES=2000000` bound probes. Native message snapshots are
saved incrementally, including on interruption; filter Trace by `conversation` or
`structured_repair`. Fixture usage is labeled an estimate, never live consumption.
The implemented Jev contract currently supports the Noul primitive used by screening.

Live checks passed on 2026-09-17: Jev returned `jev-1.13.0`; LLM returned
`gpt-5.6-luna`, executed one read-only tool and produced the validated marker.
Inspect [the live LLM trace](http://127.0.0.1:8000/runs/probe-llm-516a2123c5de/trace).
Earlier quota/compatibility failures remain inspectable. Trace usage costs are
serialized as exact Decimal strings; framework cost estimates are distinct from
provider token usage.
See [PROGRESS.md](docs/PROGRESS.md) for exact run IDs and limits. The Jev contract
follows the [official API reference](https://docs.typesafe.ai/api); agent history
uses the [Pydantic AI message API](https://ai.pydantic.dev/message-history/).

Relevance screening (T08):

```sh
uv run profitlab demo --through T08 --run-id demo-t08
uv run profitlab stage <chunked-run-id> screen
uv run profitlab stage <chunked-run-id> screen --filing-id <filing-id> --max-chunks 5
uv run profitlab stage <chunked-run-id> screen --chunk-id <chunk-id> --chunk-id <another-id>
uv run pytest tests/task_gates/test_t08.py
```

Demo uses explicitly labeled fixture judgments; live runs use configured Jev.
The five questions are versioned in `src/profitlab/prompts/screen-v1.json`.
Experimental thresholds: `SCREEN_KEEP_THRESHOLD=0.65` and
`SCREEN_UNCERTAIN_THRESHOLD=0.20`. Uncertain and failed answers remain available;
financial statement/EPS tables have a visible structural safeguard. One label and
neighbor recovery pass retains up to `SCREEN_RECOVERY_MAX_CHUNKS=12` dropped chunks
without changing their reported scores. Coverage counts unique primary source IDs;
it indicates candidate labels per filing/report-end year, not validated facts.

`SCREEN_MAX_REQUESTS=2000` bounds evaluation calls; existing HTTP retry limits apply
within each call. `SCREEN_TOTAL_TIMEOUT=1800` gives full-filing screening a separate
deadline from the shorter provider conversation budget. These defaults cover the
observed 935-chunk four-filing MSFT workload with headroom; they remain configurable.
Subset selection, failed answers, missing label coverage or exhausted limits produce
a partial run. Unscreened chunks remain explicitly unknown. Cached results preserve
their returned model and historical usage; new-request usage is separate. Changing
source/chunk/prompt/model/endpoint/policy invalidates cached judgments. Alias model
reuse cannot prove that today's alias points to the same model. Prior immutable
artifacts remain inspectable; the chunk page shows the latest screening selection.

Candidate extraction (T09):

```sh
uv run profitlab demo --through T09 --run-id demo-t09-new
uv run profitlab stage <screened-run-id> extract
uv run profitlab stage <screened-run-id> extract --filing-id <filing-id> --chunk-id <chunk-id>
uv run profitlab stage <screened-run-id> extract --max-chunks 3
# Optional supplied SEC Company Facts JSON; never replaces a cited filing value:
uv run profitlab stage <screened-run-id> extract --company-facts-file companyfacts.json
uv run pytest tests/task_gates/test_t09.py
```

Open `/runs/<run-id>/candidates`. Click **View source** on a diluted-EPS
candidate to highlight its raw cell, row and year column. The drawer shows saved
source text; **Evidence and exact quote** includes the original URL and source hash.
Expand rejected fixture proposals to see fabricated IDs and rejection reasons.
Trace → stage=extract shows actual Pydantic AI structured-output conversations,
with the synthetic provider clearly labeled. Narrative passages are separate quotes.
Values use base units: `180` USD millions becomes Decimal `180000000`; EPS `2.00`
remains `2.00` USD/share. These are candidates, not reconciled selections.

Supported inline-XBRL concepts are explicitly mapped in
`documents/extraction.py`; only visible cell-anchored, non-dimensional annual
contexts with USD/share units and simple dot-decimal transforms are accepted.
Supported tables require metric rows, year columns, units and exact fiscal intervals
in saved text. Missing dates are flagged rather than inferred from a report-end year.
Quarterly, adjusted and segment presentations cannot enter accepted candidates.
Unresolved retained chunks use a bounded extraction agent (up to eight chunks,
three model requests each, configured stage timeout). Unverifiable proposals stay
ambiguous; malformed citations/value/year/scale mismatches are rejected. Partial
coverage and unsupported layouts remain visible. No gold answers enter extraction.
Company Facts cross-checks compare the same accession/concept/interval/unit and
label conflicts; they are another presentation of the same filing data.


Candidate reconciliation (T10):

```sh
uv run profitlab demo --through T10 --run-id demo-t10-new
uv run profitlab demo --through T10 --scenario conflict --run-id conflict-t10-new
uv run profitlab demo --through T10 --scenario restatement --run-id restatement-t10
uv run profitlab demo --through T10 --scenario split-adjusted --run-id split-t10
uv run profitlab stage <extracted-run-id> reconcile
uv run pytest tests/task_gates/test_t10.py
```

The candidates page shows a coverage matrix, group comparisons and complementary
source passages. Comparable groups use the exact fiscal interval, metric,
annuality, unit/currency, scope, attribution, accounting basis and share class.
Required source validations precede selection. Complete statements/EPS notes take
precedence over isolated mentions; newest comparable presentations are used only
when values agree or a newer cited row/header/caption explicitly labels a
restatement, recast or split adjustment. An amendment alone is not such a label.
Unexplained differences remain unselected, with both values and sources visible.
Different reported precision explains differences only when the finer value rounds
to the coarser value; equally precise differing values conflict.

Repeated values retain every candidate/source reference without adding votes or
independent corroboration. Common-share earnings never use parent/consolidated
income as a substitute. Ambiguous periods, currencies or share classes produce
explicit missing/conflicting coverage. Fiscal transition periods and mixed original
and adjusted per-share bases have comparability flags for subsequent calculations.
Passages are grouped by filing report-end year and topic; identical normalized text
is shown once per year/topic with all its evidence references. This is deterministic
evidence selection, not a generated narrative. Selection trace events expose the
complete rule results. Reconciliation snapshots are immutable; rerunning selection
preserves earlier artifacts and the latest index is used by the UI.

Deterministic calculations (T11):

```sh
uv run profitlab demo --through T11 --run-id demo-t11
uv run profitlab demo --through T11 --scenario losses --run-id losses-t11
uv run profitlab stage <reconciled-run-id> calculate
uv run pytest tests/task_gates/test_t11.py
```

Open `/runs/demo-t11/report` for the preliminary annual metrics table labeled
**Data table; narrative not generated.** Click the 2025 EPS percentage to inspect
1.60 and 2.00 USD/share, the exact formula and unrounded 25% result. Input links
open selected candidates; **View source** highlights the exact cell, row and year.
`/runs/losses-t11/calculations` shows absolute changes and loss/zero-base labels
with conventional growth percentages suppressed. Four annual observations produce
three annual comparisons and a three-interval CAGR per metric when eligible.
Missing or conflicting inputs, gaps, fiscal transitions, changed fiscal lengths,
currencies/classes or unresolved per-share bases suppress comparisons. CAGR also
requires every annual value to be positive. Ordinary leap-year and 52/53-week
variation is allowed. Calculations use Decimal precision 60; two-decimal half-up
rounding applies only to display. Re-extraction or reconciliation hides stale
calculations until those stages are rerun. No financial model calls are used.


Report writing (T12):

```sh
uv run profitlab demo --through T12 --run-id demo-t12
uv run profitlab stage <run-id> write
uv run profitlab stage <run-id> validate
uv run profitlab verify <run-id>
```

Open the Report tab: annual figures come from selected fact artifacts and growth
values come from deterministic calculation artifacts. Click a figure, then View
source for its highlighted row/year. Click View calculation for a narrative
comparison. Expand a management sentence's Source drawer to inspect its exact
quote and saved/original source. Interpretations carry a separate attribution.
Trace with stage=write and kind=conversation shows native framework messages;
kind=structured_repair shows output feedback. Demo writers use an explicitly fake
provider, exercise a real read-only tool call and repair an intentionally invalid
quantitative assertion. Live writers use only the configured model.

`verify` currently checks report reference integrity, source quotes, coverage and
placeholder availability; broader end-to-end verification is T15. A failed writer
is a data-only partial report, not successful model narrative. Reports are hidden
when extraction, reconciliation or calculations change; previous immutable
artifacts remain inspectable. `writer_max_requests` (6) and
`writer_max_tool_calls` (8), provider timeout and configured structured-output
repairs bound writing. Tools return explicit missing results for unknown IDs and
never search another run. No tools execute code or fetch arbitrary URLs.


T13 adds the complete managed workflow. Start the updated interface with
`uv run profitlab serve`, open http://127.0.0.1:8000/, select **Synthetic demo**,
enter **DEMO** and click **Analyze ticker**. Progress updates every second; open
**Report** when finished. Choose **Slow (try cancellation)** to exercise Cancel
run, inspect Trace, then Resume run. Refresh preserves progress. A server restart
marks abandoned workers interrupted and offers resume.

```sh
uv run profitlab demo --through T13 --run-id demo-t13-new
uv run profitlab analyze DEMO --years 4 --mode demo
uv run profitlab analyze AAPL --years 4 --mode live
uv run profitlab resume <run-id>
uv run profitlab cancel <run-id>
uv run pytest tests/task_gates/test_t13.py
```

Live requires `SEC_USER_AGENT`, `TYPESAFE_API_KEY` and `LLM_API_KEY`; missing keys
stop before paid screening. Failed live calls never switch to synthetic providers.
Only one live workflow runs at a time; provider requests run sequentially.
`STAGE_TIMEOUT` defaults to 600 seconds and `RUN_TOTAL_TIMEOUT` to 1800 seconds.
Source/network/request budgets from earlier stages still apply. Cancellation
interrupts async provider work; synchronous downloads finish their bounded writes
before releasing the run. Remote completion and billing may remain unknown.
The CLI cancel command signals an active CLI worker as well as the web worker.
Completed stages are reused only when settings, code/prompt hashes and artifact
hashes match. Changed chunk settings invalidate screening onward; writer settings
or wording invalidate writing onward. Previous immutable artifacts remain readable.
A failed ticker-discovery response is retained; start a fresh run to retry that
lookup. Earlier stage-only runs continue to use the `stage` command.
