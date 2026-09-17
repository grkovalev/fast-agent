from pydantic import AwareDatetime, Field

from .base import Contract, StableID


class TraceEvent(Contract):
    event_id: StableID
    sequence: int = Field(ge=1)
    run_id: StableID
    span_id: StableID
    parent_id: StableID | None = None
    kind: str
    actor: str
    stage: str
    provider: str | None = None
    tool: str | None = None
    call_id: StableID | None = None
    timestamp: AwareDatetime
    duration: float | None = Field(default=None, ge=0)
    attempt: int = Field(default=1, ge=1)
    status: str
    request_artifact_id: StableID | None = None
    result_artifact_id: StableID | None = None
    summary: str
    error: dict | None = None
