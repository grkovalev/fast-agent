"""Supported commands for the fresh V2 workspace."""
import typer
import uvicorn

from profitlab.settings import Settings
from profitlab.web.app import create_app

app = typer.Typer(no_args_is_help=True, help='ProfitLab: source-guided filing research.')
v3_app = typer.Typer(no_args_is_help=True, help='Isolated V3 source-grounded graph experiment.')
app.add_typer(v3_app, name='v3')


@app.callback()
def root():
    """ProfitLab commands."""


@app.command()
def serve():
    """Start the local V2 research workspace."""
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


@v3_app.command('answer')
def v3_answer(ticker: str, question: str):
    """Answer a question from the latest live 10-K with cited graph paths."""
    import asyncio
    import json

    from profitlab.v3.service import V3GraphService

    result = asyncio.run(V3GraphService(Settings()).answer_live(ticker, question))
    typer.echo(json.dumps(result.model_dump(mode='json'), indent=2))
