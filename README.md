# ProfitLab

Local, inspectable earnings growth research. Company earnings per share; stock-price returns are not included.

T07 is implemented: separate Jev and OpenAI-compatible adapters with inspectable compatibility probes, table-aware chunks and a filterable chunk inspector, SEC discovery and filing downloads, a sanitized anchored source viewer with table highlighting, persistent service tracing, immutable storage, and synthetic fixtures. Financial processing starts in later tasks.

Requires Python 3.12 and uv. From the repository root:

```sh
uv sync --locked
uv run profitlab doctor
uv run profitlab demo --through T07 --run-id demo-t07
uv run profitlab serve
```

Open http://127.0.0.1:8000/runs/demo-t07/trace. Expand the **fake-jev** request and **Fixture agent history** to inspect the read-only tool call and validated marker. The run also retains discovery, sources and chunks. Home accepts ticker discovery in demo or live mode. Use a fresh run ID each time; existing runs cannot be overwritten. Runtime summaries are stored under `data/runs/`.

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

Continue with [PROGRESS.md](docs/PROGRESS.md), [TASKS.md](docs/TASKS.md), and the [implementation specification](docs/IMPLEMENTATION_PLAN.md). The next task is T08: Jev relevance screening and coverage recovery. Discovered filing coverage is separate from extracted financial coverage; financial stages remain unavailable. Earlier runs stay readable.

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
