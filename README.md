# ProfitLab

Local, inspectable earnings growth research. Company earnings per share; stock-price returns are not included.

T01 is implemented: CLI, local interface, configuration checks, and an offline synthetic setup demo. SEC retrieval and financial processing are not implemented yet.

Requires Python 3.12 and uv. From the repository root:

```sh
uv sync --locked
uv run profitlab doctor
uv run profitlab demo --through T01 --run-id demo-t01
uv run profitlab serve
```

Open http://127.0.0.1:8000/runs/demo-t01. You should see DEMO, a **Synthetic demo** badge, setup completion, and unavailable financial stages. Home lists saved runs. Use a fresh run ID each time; existing runs cannot be overwritten. Runtime summaries are stored under `data/runs/`.

The interface binds to `127.0.0.1:8000` by default. Demo and UI need no credentials or network after installation. Optionally copy `.env.example` to `.env`; configuration checks report presence only and do not probe external services. Never commit credentials.

The default model configuration is OpenAI API (`https://api.openai.com/v1`) with
`gpt-5.6-luna`, selected for low cost. Set `LLM_API_KEY` in your local `.env`
to your OpenAI API key. `LLM_BASE_URL` and `LLM_MODEL` remain configurable;
remove old blank assignments or use the values in `.env.example`. Model calls
will be implemented in T07; configuration alone does not make paid requests.
See [official model capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

```sh
uv run profitlab --help
uv run pytest tests/task_gates/test_t01.py
uv run ruff check .
```

Continue with [PROGRESS.md](docs/PROGRESS.md), [TASKS.md](docs/TASKS.md), and the [implementation specification](docs/IMPLEMENTATION_PLAN.md). The next task is T02: validated contracts, fixtures, and persistent artifact storage.
