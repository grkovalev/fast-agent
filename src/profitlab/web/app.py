from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.storage import Repository

WEB_DIR = Path(__file__).parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    service = DemoService(settings.data_dir)
    app = FastAPI(title="ProfitLab")
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
            context={'run_id': run_id, 'artifact_id': artifact_id, 'content': content},
        )

    return app
