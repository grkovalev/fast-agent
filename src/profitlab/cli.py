"""Supported commands for the fresh V2 workspace."""
import typer
import uvicorn

from profitlab.settings import Settings
from profitlab.web.app import create_app

app = typer.Typer(no_args_is_help=True, help='ProfitLab: source-guided filing research.')


@app.callback()
def root():
    """ProfitLab commands."""


@app.command()
def serve():
    """Start the local V2 research workspace."""
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
