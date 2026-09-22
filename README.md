# ProfitLab

ProfitLab is a local, inspectable SEC earnings-research workspace. Its only supported
workflow is the fresh eight-stage V2 pipeline: visible source, outline, section score,
chunk, chunk score, quote-backed findings, structured facts, and independent evaluation.
Previous run data and the historical flat pipeline are unsupported.

Requires Python 3.12 and uv.

```sh
uv sync --locked
uv run profitlab serve
```

Open http://127.0.0.1:8000/. For a no-network inspection run, enter `DEMO`, select
**Offline fixture**, and choose **Create fresh V2 run**. For a live SEC filing, select
**Live SEC filing**, enter a ticker, and configure `SEC_USER_AGENT` with a real contact
email. Live outline/findings and Jev scoring also require `LLM_API_KEY` and
`TYPESAFE_API_KEY`; no provider call is made until a live run is created.

Open **Pipeline → Findings** to inspect every published quote and jump to its canonical
visible source line. Open **Evaluate** to compare that discovery output with Company
Facts loaded only after findings are sealed. Provider diagnostics remain on each stage's
**Inspect sanitized provider trace** page.

Run checks with:

```sh
uv run pytest
uv run ruff check .
```

See [PROGRESS.md](docs/PROGRESS.md), [TASKS.md](docs/TASKS.md), and the
[V2 implementation specification](docs/V2_IMPLEMENTATION_PLAN.md). The next task is
T26: benchmark Jev retrieval against simple baselines.
