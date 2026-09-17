import typer
import uvicorn
from rich.console import Console

from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.web.app import create_app

app = typer.Typer(no_args_is_help=True, help="ProfitLab: inspectable earnings growth research.")
console = Console()


@app.command()
def serve():
    """Start the local inspection interface."""
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


@app.command()
def doctor():
    """Check local configuration presence; no network or live probes."""
    for name, ready in Settings().readiness().items():
        console.print(f"{name}: {'ready' if ready else 'not configured (optional for demo)'}")
    console.print("Configuration presence only; live integrations are not implemented yet.")


@app.command()
def demo(
    through: str = typer.Option("T01", help="Latest implemented task: T01."),
    run_id: str = typer.Option(..., help="Unique run ID; existing runs are preserved."),
):
    """Create an offline, synthetic setup run."""
    settings = Settings()
    try:
        run = DemoService(settings.data_dir).create(run_id, through)
    except ValueError as error:
        console.print(f"Error: {error}", markup=False)
        raise typer.Exit(2) from None
    console.print(f"Synthetic demo · Run ID: {run.run_id}", markup=False)
    console.print(f"http://{settings.host}:{settings.port}/runs/{run.run_id}", markup=False)
