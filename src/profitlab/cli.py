from typing import Annotated

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
def doctor(live: str | None = typer.Option(None, help='Explicit live probe: sec, jev or llm.')):
    """Check configuration or run an explicit, saved provider probe."""
    settings = Settings()
    if live is not None:
        if live in ('jev', 'llm'):
            from profitlab.providers.service import ProbeService

            run = ProbeService(settings).create(live)
            console.print(f'{live}: {run.status} · {run.limitation}', markup=False)
            console.print(f'http://{settings.host}:{settings.port}/runs/{run.run_id}/trace',
                          markup=False)
            if run.status == 'failed':
                raise typer.Exit(1)
            return
        if live != 'sec':
            console.print('Error: Supported live probes: sec, jev, llm.')
            raise typer.Exit(2)
        _discover(settings, 'AAPL', 1, 'live', None)
        return
    for name, ready in settings.readiness().items():
        console.print(f"{name}: {'ready' if ready else 'not configured (optional for demo)'}")
    console.print('Configuration presence only. Use doctor --live sec|jev|llm for an explicit probe.')


@app.command()
def demo(
    through: str = typer.Option("T10", help="Latest implemented task: T10."),
    run_id: str = typer.Option(..., help="Unique run ID; existing runs are preserved."),
    scenario: str = typer.Option("normal", help="normal, two-years, conflict, restatement or split-adjusted fixtures."),
):
    """Create an offline, synthetic setup run."""
    settings = Settings()
    try:
        run = DemoService(settings.data_dir).create(run_id, through, scenario)
    except ValueError as error:
        console.print(f"Error: {settings.redactor().text(str(error))}", markup=False)
        raise typer.Exit(2) from None
    console.print(f"Synthetic demo · Run ID: {run.run_id}", markup=False)
    console.print(f"http://{settings.host}:{settings.port}/runs/{run.run_id}", markup=False)


def _discover(settings, ticker, years, mode, run_id):
    from profitlab.sec.contracts import DiscoveryResult
    from profitlab.sec.service import DiscoveryService
    from profitlab.storage import Repository

    try:
        run = DiscoveryService(settings).create(ticker, years, mode, run_id)
    except ValueError as error:
        console.print(f'Error: {settings.redactor().text(str(error))}', markup=False)
        raise typer.Exit(2) from None
    result = DiscoveryResult.model_validate_json(Repository(settings.data_dir).read(
        run.run_id, 'discovery'))
    console.print(f'{run.ticker}: {result.outcome} · {result.message}', markup=False)
    if run.company:
        console.print(f'{run.company.name} · CIK {run.company.cik}', markup=False)
    for filing in result.filings:
        console.print(f'{filing.report_date} · {filing.form} · {filing.accession}', markup=False)
    console.print(f'http://{settings.host}:{settings.port}/runs/{run.run_id}', markup=False)
    console.print(f'http://{settings.host}:{settings.port}/runs/{run.run_id}/trace', markup=False)
    if result.outcome != 'found':
        raise typer.Exit(1)


@app.command()
def discover(
    ticker: str,
    years: int = typer.Option(4, min=1, max=4),
    mode: str = typer.Option('live', help='demo or live; live requires SEC contact.'),
    run_id: str | None = typer.Option(None, help='Optional unique run ID.'),
):
    """Resolve a ticker and save up to four annual periods; stop at discovery."""
    _discover(Settings(), ticker, years, mode, run_id)


@app.command()
def inspect(run_id: str):
    """Print the saved manifest and immutable artifact index without provider calls."""
    from profitlab.storage import Repository

    settings = Settings()
    try:
        run = DemoService(settings.data_dir).get(run_id)
        console.print(run.model_dump_json(indent=2), markup=False)
        for artifact in Repository(settings.data_dir).artifacts(run_id):
            console.print(f"{artifact['artifact_id']} · {artifact['media_type']} · "
                          f"sha256:{artifact['hash']}", markup=False)
    except (ValueError, FileNotFoundError) as error:
        console.print(f"Error: {settings.redactor().text(str(error))}", markup=False)
        raise typer.Exit(2) from None


@app.command()
def export(run_id: str, output: str = typer.Option(..., help="New trace export directory.")):
    """Export complete redacted trace and payloads; report bundles come in T16."""
    from pathlib import Path

    from profitlab.storage import Repository
    from profitlab.trace import TraceRecorder

    settings = Settings()
    try:
        TraceRecorder(Repository(settings.data_dir), run_id, settings.redactor()).export(Path(output))
    except (ValueError, OSError) as error:
        console.print(f"Error: {settings.redactor().text(str(error))}", markup=False)
        raise typer.Exit(2) from None
    console.print(f"Redacted trace exported to {output}", markup=False)


@app.command()
def stage(run_id: str, stage: str, filing_id: str | None = typer.Option(None),
          chunk_id: Annotated[list[str] | None, typer.Option(help='Select saved screening/extraction chunks; repeatable.')] = None,
          max_chunks: int | None = typer.Option(None, min=1, help='Bound screening/extraction to a subset; result is partial.'),
          company_facts_file: str | None = typer.Option(None, help='Optional saved SEC Company Facts JSON cross-check for extraction.')):
    """Download, parse, chunk, screen, extract or reconcile saved discovered filings; optionally select one filing."""
    from profitlab.documents.service import SourceService

    settings = Settings()
    try:
        if stage == 'reconcile':
            from profitlab.analysis.reconciliation import ReconciliationService

            if filing_id or chunk_id or max_chunks or company_facts_file:
                raise ValueError('Reconcile uses the latest full extraction snapshot; subset controls apply to extraction.')
            result = ReconciliationService(settings).progress(run_id)
            console.print(result.limitation)
        elif stage == 'extract':
            import json
            from pathlib import Path

            from profitlab.providers.extraction import ExtractionService

            facts = json.loads(Path(company_facts_file).read_text()) if company_facts_file else None
            result = ExtractionService(settings).progress(run_id, filing_id, max_chunks, chunk_id, facts)
            console.print(result.limitation)
        elif stage == 'screen':
            from profitlab.providers.screening import ScreeningService

            result = ScreeningService(settings).progress(run_id, filing_id, max_chunks, chunk_id)
            if result.status == 'partial':
                console.print(result.limitation)
        elif stage == 'chunk':
            from profitlab.documents.chunk_service import ChunkService

            ChunkService(settings).progress(run_id, filing_id)
        else:
            SourceService(settings).progress(run_id, stage, filing_id)
    except (ValueError, FileNotFoundError) as error:
        console.print(f"Error: {settings.redactor().text(str(error))}", markup=False)
        raise typer.Exit(2) from None
    page = 'candidates' if stage in ('extract', 'reconcile') else 'chunks' if stage in ('chunk', 'screen') else 'sources'
    console.print(f"{stage} complete · http://{settings.host}:{settings.port}/runs/{run_id}/{page}")
