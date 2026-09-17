from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder

WEB_DIR = Path(__file__).parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    service = DemoService(settings.data_dir)
    @asynccontextmanager
    async def lifespan(app):
        # Single-process startup: no application workers exist yet (jobs arrive in T13).
        repo = Repository(settings.data_dir)
        for run in repo.recent():
            TraceRecorder(repo, run.run_id, settings.redactor()).recover_interrupted()
        yield

    app = FastAPI(title="ProfitLab", lifespan=lifespan)
    templates = Jinja2Templates(directory=WEB_DIR / "templates")
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def home(request: Request):
        return templates.TemplateResponse(
            request=request, name="home.html",
            context={"runs": service.recent(), "readiness": settings.readiness()},
        )

    @app.get("/runs/{run_id}")
    def overview(request: Request, run_id: str):
        try:
            run = service.get(run_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Run not found") from None
        from profitlab.sec.contracts import DiscoveryResult

        try:
            discovery = DiscoveryResult.model_validate_json(
                Repository(settings.data_dir).read(run_id, 'discovery'))
        except FileNotFoundError:
            discovery = None
        return templates.TemplateResponse(
            request=request, name="run.html", context={
                "run": run, "artifacts": Repository(settings.data_dir).artifacts(run_id),
                'discovery': discovery,
            },
        )

    @app.post('/discover')
    async def discover(request: Request):
        from urllib.parse import parse_qs

        from profitlab.sec.service import DiscoveryService

        fields = parse_qs((await request.body()).decode())
        try:
            run = await run_in_threadpool(DiscoveryService(settings).create,
                fields.get('ticker', [''])[0], int(fields.get('years', ['4'])[0]),
                fields.get('mode', ['demo'])[0])
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                context={'runs': service.recent(), 'readiness': settings.readiness(),
                         'error': settings.redactor().text(str(error))})
        return RedirectResponse(f'/runs/{run.run_id}', status_code=303)

    @app.get('/runs/{run_id}/artifacts/{artifact_id}')
    def artifact(request: Request, run_id: str, artifact_id: str):
        try:
            content = Repository(settings.data_dir).read(run_id, artifact_id).decode()
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Artifact not found or damaged') from None
        return templates.TemplateResponse(
            request=request, name='artifact.html',
            context={'run_id': run_id, 'artifact_id': artifact_id,
                     'content': settings.redactor().text(content)},
        )

    def trace_data(run_id, filters):
        try:
            run = service.get(run_id)
            recorder = TraceRecorder(Repository(settings.data_dir), run_id, settings.redactor())
            events, warnings = recorder.history()
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'Run not found') from None
        selected = []
        for event in events:
            data = settings.redactor()(event)
            if any(filters.get(key) and data.get(key) != filters[key]
                   for key in ('stage', 'actor', 'kind', 'provider', 'tool')):
                continue
            if filters.get('error_only') and event.status not in ('failed', 'interrupted'):
                continue
            if event.sequence <= int(filters.get('after_sequence', 0)):
                continue
            query = filters.get('q', '').lower()
            search = event.model_dump_json()
            if query:
                for identifier in (event.request_artifact_id, event.result_artifact_id):
                    if identifier:
                        search += recorder.repo.read(run_id, identifier).decode()
                if query not in search.lower():
                    continue
            selected.append(data)
        return run, selected, warnings

    @app.get('/runs/{run_id}/trace/events')
    def trace_events(request: Request, run_id: str, after_sequence: int = 0):
        filters = dict(request.query_params)
        filters['after_sequence'] = after_sequence
        _, events, warnings = trace_data(run_id, filters)
        return {'events': events, 'warnings': warnings}

    @app.get('/runs/{run_id}/trace')
    def trace_page(request: Request, run_id: str):
        filters = dict(request.query_params)
        # The incremental cursor belongs to the JSON endpoint only.
        filters.pop('after_sequence', None)
        run, events, warnings = trace_data(run_id, filters)
        return templates.TemplateResponse(request=request, name='trace.html', context={
            'run': run, 'events': events, 'warnings': warnings, 'filters': filters,
        })

    @app.get('/runs/{run_id}/trace/payloads/{artifact_id}')
    def trace_payload(run_id: str, artifact_id: str):
        try:
            recorder = TraceRecorder(Repository(settings.data_dir), run_id, settings.redactor())
            events, _ = recorder.history()
            allowed = {identifier for event in events for identifier in
                       (event.request_artifact_id, event.result_artifact_id) if identifier}
            if artifact_id not in allowed:
                raise ValueError('Unknown trace payload')
            import json

            return settings.redactor()(json.loads(recorder.repo.read(run_id, artifact_id)))
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'Trace payload not found or damaged') from None

    @app.get('/runs/{run_id}/sources')
    def sources(request: Request, run_id: str):
        from profitlab.documents.service import SourceService

        try:
            run, items = SourceService(settings).sources(run_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Sources not found or damaged') from None
        return templates.TemplateResponse(request=request, name='sources.html',
            context={'run': run, 'items': items})

    @app.get('/runs/{run_id}/sources/{filing_id}')
    def source(request: Request, run_id: str, filing_id: str,
               cell: str = '', row: str = '', column: str = ''):
        from profitlab.documents.service import SourceService

        try:
            run, item = SourceService(settings).document(run_id, filing_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Source not found or damaged') from None
        cells = item['cells']
        if (cell and cell not in cells or row and row not in {c.row_id for c in cells.values()}
                or column and column not in {c.column_id for c in cells.values()}):
            raise HTTPException(400, 'Unknown highlight coordinate')
        row_cells, column_cells = set(), set()
        for table_id, table in item['index']['tables'].items():
            for rendered_row in table['rows']:
                for coordinate in rendered_row:
                    c = cells[coordinate['cell_id']]
                    if row and row.startswith(table_id + '-r'):
                        target = int(row.rsplit('-r', 1)[1])
                        if coordinate['row'] <= target < coordinate['row'] + c.row_span:
                            row_cells.add(c.cell_id)
                    if column and column.startswith(table_id + '-c'):
                        target = int(column.rsplit('-c', 1)[1])
                        if coordinate['column'] <= target < coordinate['column'] + c.column_span:
                            column_cells.add(c.cell_id)
        return templates.TemplateResponse(request=request, name='source.html',
            context={'run': run, 'item': item, 'cell': cell,
                     'row_cells': row_cells, 'column_cells': column_cells})

    @app.get('/runs/{run_id}/chunks')
    def chunks(request: Request, run_id: str, filing: str = '', heading: str = '',
               min_tokens: int = 0, max_tokens: int | None = None):
        from profitlab.documents.chunk_service import ChunkService

        try:
            run, all_chunks = ChunkService(settings).list(run_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Chunks not found or damaged') from None
        from profitlab.providers.screening import ScreeningService

        screening, decisions = ScreeningService(settings).latest(run_id)
        items = []
        for i, chunk in enumerate(all_chunks):
            if (filing and chunk.filing_id != filing or
                    heading.lower() not in ' / '.join(chunk.heading_path).lower() or
                    chunk.token_estimate < min_tokens or
                    max_tokens is not None and chunk.token_estimate > max_tokens):
                continue
            previous = all_chunks[i-1] if i and all_chunks[i-1].filing_id == chunk.filing_id else None
            following = all_chunks[i+1] if i+1 < len(all_chunks) and all_chunks[i+1].filing_id == chunk.filing_id else None
            items.append({'chunk': chunk, 'previous': previous, 'following': following,
                          'screen': decisions.get(chunk.chunk_id)})
        return templates.TemplateResponse(request=request, name='chunks.html', context={
            'run': run, 'items': items, 'filings': sorted({c.filing_id for c in all_chunks}),
            'filing': filing, 'heading': heading, 'min_tokens': min_tokens,
            'max_tokens': max_tokens, 'screening': screening})

    @app.get('/runs/{run_id}/candidates')
    def candidates(request: Request, run_id: str):
        from profitlab.providers.extraction import ExtractionService

        try:
            run = service.get(run_id)
            index, attempts = ExtractionService(settings).latest(run_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Candidates not found or damaged') from None
        import json

        evidence = {a.evidence_id: json.loads(Repository(settings.data_dir).read(run_id, a.evidence_id))
                    for a in attempts if a.evidence_id}
        cells = {a.proposal['cell_id']: json.loads(Repository(settings.data_dir).read(run_id, a.proposal['cell_id']))
                 for a in attempts if a.candidate}
        return templates.TemplateResponse(request=request, name='candidates.html',
            context={'run': run, 'index': index, 'attempts': attempts, 'evidence': evidence, 'cells': cells})

    return app
