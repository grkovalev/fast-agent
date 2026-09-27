"""Immutable, generic contracts for the V3 evidence graph."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from profitlab.v2.contracts import CanonicalDocumentRef, SourceRange

Relation = Literal['supports', 'qualifies', 'contradicts', 'same_claim', 'narrows', 'related_to']
Status = Literal['accepted', 'uncertain', 'rejected']


class V3Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[3] = 3


class EvidenceNode(V3Contract):
    node_id: str = Field(pattern=r'^node-[a-f0-9]{16}$')
    document_id: str
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    label: str = Field(min_length=1, max_length=500)
    evidence_ranges: list[SourceRange] = Field(min_length=1)
    status: Status
    model: str
    prompt_version: str
    uncertainty: str | None = Field(default=None, max_length=2000)


class EvidenceEdge(V3Contract):
    edge_id: str = Field(pattern=r'^edge-[a-f0-9]{16}$')
    document_id: str
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    from_node_id: str
    to_node_id: str
    relation: Relation
    evidence_ranges: list[SourceRange] = Field(min_length=1)
    status: Status
    model: str
    prompt_version: str
    uncertainty: str | None = Field(default=None, max_length=2000)


class ExplorationAction(V3Contract):
    action_id: str = Field(pattern=r'^action-[a-f0-9]{16}$')
    experiment_id: str
    sequence: int = Field(ge=1)
    window: SourceRange
    reason: str = Field(min_length=1, max_length=1000)
    parent_path: list[str] = Field(default_factory=list)
    status: Literal['completed', 'partial', 'budget_exhausted', 'cached']
    request_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    response_status: str
    elapsed_seconds: float = Field(ge=0)
    created_at: datetime


class GraphPath(V3Contract):
    path_id: str = Field(pattern=r'^path-[a-f0-9]{16}$')
    document_id: str
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    node_ids: list[str] = Field(min_length=1)
    edge_ids: list[str] = Field(default_factory=list)
    source_ranges: list[SourceRange] = Field(min_length=1)


class AnswerCandidate(V3Contract):
    answer_id: str = Field(pattern=r'^answer-[a-f0-9]{16}$')
    experiment_id: str
    answer: str = Field(min_length=1, max_length=10000)
    limitation: str | None = Field(default=None, max_length=2000)
    path_ids: list[str] = Field(min_length=1)
    source_ranges: list[SourceRange] = Field(min_length=1)
    status: Literal['accepted', 'limited', 'rejected']
    model: str
    prompt_version: str


class ExperimentManifest(V3Contract):
    experiment_id: str = Field(pattern=r'^v3-[a-f0-9]{16}$')
    question: str = Field(min_length=1, max_length=4000)
    document: CanonicalDocumentRef
    ticker: str
    filing: dict[str, str]
    application_revision: str
    model: str
    prompt_version: str
    budgets: dict[str, int | float]
    non_leak_inventory: tuple[str, ...]
    created_at: datetime
    finished_at: datetime | None = None
    frontier_state: Literal['active', 'exhausted', 'answered', 'budget_exhausted'] = 'active'


class GraphAnswer(V3Contract):
    manifest: ExperimentManifest
    answer: AnswerCandidate
    paths: list[GraphPath]
    cited_text: dict[str, str]

    @model_validator(mode='after')
    def citations_have_paths(self):
        if not set(self.answer.path_ids) <= {path.path_id for path in self.paths}:
            raise ValueError('Answer cites a missing graph path')
        return self
