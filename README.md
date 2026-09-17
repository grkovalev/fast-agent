# ProfitLab

Local, inspectable earnings growth research. Company earnings per share; stock-price returns are not included.

T06 is implemented: table-aware chunks and a filterable chunk inspector, SEC discovery and filing downloads, a sanitized anchored source viewer with table highlighting, persistent service tracing, immutable storage, and synthetic fixtures. Financial processing starts in later tasks.

Requires Python 3.12 and uv. From the repository root:

```sh
uv sync --locked
uv run profitlab doctor
uv run profitlab demo --through T04 --run-id demo-t04
uv run profitlab serve
```

Open http://127.0.0.1:8000/runs/demo-t04. You should see DEMO, a **Synthetic demo** badge, the matched company and four annual report periods plus an associated amendment. Click Saved artifacts → discovery for exact metadata, or Trace for requests and older-history traversal. Home accepts ticker discovery in demo or live mode. Use a fresh run ID each time; existing runs cannot be overwritten. Runtime summaries are stored under `data/runs/`.

The interface binds to `127.0.0.1:8000` by default. Demo and UI need no credentials or network after installation. Optionally copy `.env.example` to `.env`; configuration checks report presence only and do not probe external services. Never commit credentials.

The default model configuration is OpenAI API (`https://api.openai.com/v1`) with
`gpt-5.6-luna`, selected for low cost. Set `LLM_API_KEY` in your local `.env`
to your OpenAI API key. `LLM_BASE_URL` and `LLM_MODEL` remain configurable;
remove old blank assignments or use the values in `.env.example`. Model calls
will be implemented in T07; configuration alone does not make paid requests.
See [official model capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

```sh
uv run profitlab --help
uv run profitlab inspect demo-t02
uv run profitlab demo --through T02 --scenario two-years --run-id two-years-t02
uv run pytest
uv run ruff check .
```

Continue with [PROGRESS.md](docs/PROGRESS.md), [TASKS.md](docs/TASKS.md), and the [implementation specification](docs/IMPLEMENTATION_PLAN.md). The next task is T07: Jev and OpenAI-compatible provider adapters. Discovered filing coverage is separate from extracted financial coverage; financial stages remain unavailable. Earlier runs stay readable.

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
or estimated size. No screening decisions exist yet.

`CHUNK_TARGET_TOKENS=1500` and `CHUNK_OVERLAP_TOKENS=180` configure block-based
prose chunking. Tables can exceed the target. `CHUNK_REQUEST_BUDGET=24000`
includes `CHUNK_QUESTION_OVERHEAD=2000` reserved tokens and metadata, using a
conservative UTF-8 bytes/3 proxy; these are estimates, not measured Jev usage.
Oversized blocks or inseparable row groups fail explicitly without truncation.
Changed configurations save additional immutable chunk versions; earlier
versions remain inspectable. The safe budget is provisional until T07/T14.
