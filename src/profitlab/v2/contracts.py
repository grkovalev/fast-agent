"""Small, shared contracts for the V2 source-ranged pipeline."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from profitlab.contracts.base import StableID

STAGE_NAMES = (
    'source', 'outline', 'section_score', 'chunk',
    'chunk_score', 'findings', 'facts', 'evaluate',
)
StageName = Literal[
    'source', 'outline', 'section_score', 'chunk',
    'chunk_score', 'findings', 'facts', 'evaluate',
]
StageStatus = Literal[
    'queued', 'running', 'completed', 'partial', 'failed', 'cancelled', 'interrupted',
]
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class V2Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    schema_version: Literal[2] = 2


class StageSnapshot(V2Contract):
    run_id: StableID
    stage: StageName
    position: int = Field(ge=1, le=8)
    status: StageStatus = 'queued'
    completed_work: int = Field(default=0, ge=0)
    total_work: int | None = Field(default=None, ge=0)
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    elapsed_seconds: float = Field(default=0, ge=0)
    summary: str = ''
    limitation: str | None = None
    error: str | None = None
    input_hash: Hash | None = None
    output_hash: Hash | None = None

    @model_validator(mode='after')
    def work_is_bounded(self):
        if self.total_work is not None and self.completed_work > self.total_work:
            raise ValueError('Completed work cannot exceed total work')
        return self


class V2Run(V2Contract):
    run_id: StableID
    ticker: str = Field(pattern=r'^[A-Z0-9][A-Z0-9.-]{0,19}$')
    mode: Literal['offline', 'live']
    status: StageStatus = 'queued'
    selected_stage: StageName = 'source'
    cancellation_requested: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    summary: str = ''


class CanonicalDocumentRef(V2Contract):
    document_id: StableID
    filing_id: StableID
    source_hash: Hash
    line_count: int = Field(ge=0)


class SourceRange(V2Contract):
    document_id: StableID
    source_hash: Hash
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_character: int | None = Field(default=None, ge=0)
    end_character: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def ordered(self):
        if self.end_line < self.start_line:
            raise ValueError('Source range ends before it starts')
        if ((self.start_character is None) != (self.end_character is None) or
                self.start_character is not None and self.end_character < self.start_character):
            raise ValueError('Character coordinates must be a complete ordered pair')
        return self


class OutlineSection(V2Contract):
    section_id: StableID
    generated_topic: str = Field(min_length=1)
    exact_source_title: str | None = None
    exact_representative_quote: str | None = None
    primary_range: SourceRange
    parent_topic_hint: str | None = None
    section_type: str | None = None
    boundary_warnings: list[str] = Field(default_factory=list)


class TextChunk(V2Contract):
    chunk_id: StableID
    section_id: StableID
    core_range: SourceRange
    context_ranges: list[SourceRange] = Field(default_factory=list)
    request_size_estimate: int = Field(ge=0)
    previous_chunk_id: StableID | None = None
    next_chunk_id: StableID | None = None


class ScoredItem(V2Contract):
    item_id: StableID
    target_scores: dict[str, Annotated[float, Field(ge=0, le=1)]]
    model: str
    call_id: str
    policy_decision: Literal['selected', 'uncertain', 'skipped']
    policy_reason: str


class Finding(V2Contract):
    finding_id: StableID
    narrative: str = Field(min_length=1)
    exact_quote: str = Field(min_length=1)
    source_range: SourceRange
    source_chunk_id: StableID | None = None
    target: str | None = None
    raw_number: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    period: str | None = None
    attribution: str | None = None
    limitations: list[str] = Field(default_factory=list)
    validation_state: Literal['validated', 'rejected', 'unresolved']
    model: str | None = None
    repair_attempted: bool = False


class StructuredFact(V2Contract):
    fact_id: StableID
    concept: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value: Decimal
    unit: str = Field(min_length=1)
    period_start: date | None = None
    period_end: date
    accession: str
    form: str
    filed_date: date


class FactComparison(V2Contract):
    comparison_id: StableID
    metric: str | None = None
    fact_id: StableID | None = None
    finding_ids: list[StableID] = Field(default_factory=list)
    state: Literal[
        'exact_match', 'value_match_period_unresolved', 'period_match_value_mismatch',
        'structured_fact_missed', 'additional_visible_value', 'unsupported',
        'ambiguous_duplicate',
    ]
    requests_before_match: int | None = Field(default=None, ge=0)
    source_lines_before_match: int | None = Field(default=None, ge=0)


class PipelineEvent(V2Contract):
    sequence: int = Field(ge=1)
    run_id: StableID
    stage: StageName | None = None
    kind: Literal['run_created', 'stage_started', 'stage_finished', 'run_finished',
                  'cancellation_requested', 'resume_requested', 'run_cancelled', 'run_interrupted']
    status: StageStatus
    summary: str
    created_at: AwareDatetime
