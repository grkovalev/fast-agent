"""T01 setup service; full versioned persistence is introduced in T02."""
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class RunSummary(BaseModel):
    run_id: str
    ticker: str = "DEMO"
    mode: str = "demo"
    stage: str = "setup"
    status: str = "completed"
    created_at: datetime
    limitation: str = "Setup only. Financial processing is not implemented yet."


def validate_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Run ID must be 1–80 letters, digits, underscores or hyphens.")
    return run_id


class DemoService:
    def __init__(self, data_dir: Path):
        self.runs_dir = data_dir / "runs"

    def create(self, run_id: str, through: str) -> RunSummary:
        validate_run_id(run_id)
        if through != "T01":
            raise ValueError("Only --through T01 is implemented.")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = self.runs_dir / run_id
        try:
            run_dir.mkdir()
        except FileExistsError:
            raise ValueError(f"Run {run_id} already exists; choose a fresh run ID.") from None
        summary = RunSummary(run_id=run_id, created_at=datetime.now(UTC))
        (run_dir / "summary.json").write_text(summary.model_dump_json(indent=2))
        return summary

    def get(self, run_id: str) -> RunSummary:
        validate_run_id(run_id)
        return RunSummary.model_validate_json(
            (self.runs_dir / run_id / "summary.json").read_text()
        )

    def recent(self) -> list[RunSummary]:
        if not self.runs_dir.exists():
            return []
        runs = [self.get(path.parent.name) for path in self.runs_dir.glob("*/summary.json")]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)
