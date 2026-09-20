"""Persistent workflow contracts; caches identify their actual producing artifacts."""
from typing import Literal

from pydantic import AwareDatetime, Field

from profitlab.contracts.base import Contract, RunManifest, StableID


class StageState(Contract):
    name: str
    status: Literal['pending', 'running', 'completed', 'failed', 'interrupted'] = 'pending'
    input_hash: str | None = None
    output_hash: str | None = None
    output_ids: list[StableID] = Field(default_factory=list)
    source_run_id: StableID | None = None
    error: str | None = None
    elapsed_seconds: float = 0


class PipelineState(Contract):
    run: RunManifest
    stages: list[StageState]
    started_at: AwareDatetime | None = None
    elapsed_seconds: float = 0
    error: str | None = None
