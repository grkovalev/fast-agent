from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
        return templates.TemplateResponse(
            request=request, name="run.html", context={
                "run": run, "artifacts": Repository(settings.data_dir).artifacts(run_id),
            },
        )

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

    return app
