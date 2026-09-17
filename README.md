# ProfitLab implementation handoff

This repository currently contains an implementation plan, not an implemented application.

ProfitLab will accept a stock ticker, retrieve SEC annual filings covering up to four fiscal years, use TypeSafe Jev to find relevant evidence, extract and reconcile earnings figures, and use a Pydantic AI agent to write a cited earnings-growth report. A local browser interface will expose the source evidence and the complete observable agent/tool trace.

## Read these files in order

1. [Progress and next-task prompt](docs/PROGRESS.md): the small file used to resume work.
2. [Implementation specification](docs/IMPLEMENTATION_PLAN.md): architecture, contracts, financial rules, evidence, and trace requirements.
3. [Numbered implementation tasks](docs/TASKS.md): sixteen bounded tasks, each with a runnable demo and acceptance checks.

To begin, give the coding agent this instruction:

> Read README.md, docs/PROGRESS.md, docs/IMPLEMENTATION_PLAN.md, and the next eligible task in docs/TASKS.md. Implement that task only. Run its checks and demonstrate it through the local interface. Update docs/PROGRESS.md with the actual results, the verification command and URL, and the next task. Do not mark unrun checks as passed. Follow the task handoff protocol in docs/TASKS.md.

For later turns, say:

> Do the next task in docs/PROGRESS.md.

The proposed commands below become available during implementation. They do not run yet:

```sh
uv sync --locked
uv run profitlab serve
uv run profitlab demo --through T01 --run-id demo-t01
```

The planned interface runs at `http://127.0.0.1:8000`. Demo mode is offline and visibly labeled. Live SEC, Jev, and language-model checks have separate status so a working fixture cannot be mistaken for a verified integration.
