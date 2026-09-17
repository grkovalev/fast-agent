# Verified dependency versions

Resolved with uv 0.8.13 on 2026-09-17. Python 3.12.11.

Python is restricted to 3.12; `uv.lock` pins the complete dependency graph.
Pydantic AI uses the slim distribution with its OpenAI extra; provider integration verified locally in T07; live Jev and live LLM compatibility probes passed.

| Direct dependency / build tool | Version |
| --- | --- |
| fastapi | 0.141.1 |
| uvicorn | 0.53.0 |
| jinja2 | 3.1.6 |
| pydantic | 2.13.5 |
| pydantic-settings | 2.15.0 |
| pydantic-ai-slim | 2.44.0 |
| httpx | 0.28.1 |
| lxml | 6.1.3 |
| typer | 0.27.2 |
| rich | 15.0.0 |
| pytest | 9.1.1 |
| pytest-asyncio | 1.4.0 |
| ruff | 0.16.8 |

Build backend: hatchling, isolated build requirement; not installed in the runtime environment.

T07 inspected installed Pydantic AI 2.44.0 factory, Agent.iter, native message
serialization, FunctionModel, usage and tool APIs. OpenAI SDK 3.14.1 is provided
by the existing OpenAI extra; its AsyncOpenAI client is explicitly configured with
max_retries=0. Dependencies and uv.lock unchanged.
