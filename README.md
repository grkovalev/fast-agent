# ProfitLab

Local, inspectable earnings growth research. Company earnings per share; stock-price returns are not included.

T03 is implemented: persistent service tracing, a filtered timeline with full redacted payloads, trace export, validated contracts, immutable storage, and synthetic fixtures. SEC retrieval and financial processing are not implemented yet.

Requires Python 3.12 and uv. From the repository root:

```sh
uv sync --locked
uv run profitlab doctor
uv run profitlab demo --through T03 --run-id demo-t03
uv run profitlab serve
```

Open http://127.0.0.1:8000/runs/demo-t03. You should see DEMO, a **Synthetic demo** badge, setup completion, and unavailable financial stages. Click Saved artifacts → manifest or fixture-metadata to inspect JSON; annual reports show escaped raw HTML. Home lists saved runs. Use a fresh run ID each time; existing runs cannot be overwritten. Runtime summaries are stored under `data/runs/`.

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

Continue with [PROGRESS.md](docs/PROGRESS.md), [TASKS.md](docs/TASKS.md), and the [implementation specification](docs/IMPLEMENTATION_PLAN.md). The next task is T04: SEC ticker lookup and filing discovery. Fixture availability is separate from extracted coverage; financial stages remain unavailable. Existing T01 runs stay readable.

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
