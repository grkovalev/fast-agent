"""Small, shared contracts for the V2 source-ranged pipeline."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

STAGE_NAMES = (
    'source', 'outline', 'section_score', 'chunk',
    'chunk_score', 'findings', 'facts', 'evaluate',
)
StableID = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")]
StageName = Literal[
    'source', 'outline', 'section_score', 'chunk',
    'chunk_score', 'findings', 'facts', 'evaluate',
]
StageStatus = Literal[
    'queued', 'running', 'completed', 'partial', 'failed', 'cancelled', 'interrupted',
]
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
FindingType = Literal['annual_profit', 'diluted_eps', 'diluted_shares', 'unresolved']
BatchStatus = Literal['queued', 'running', 'cancelling', 'cancelled', 'completed']
BatchItemOutcome = Literal['completed', 'failed', 'cancelled', 'skipped']


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
    queued_seconds: float = Field(default=0, ge=0)
    active_seconds: float = Field(default=0, ge=0)
    retry_backoff_seconds: float = Field(default=0, ge=0)
    active_started_monotonic: float | None = Field(default=None, ge=0)
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
    status: StageStatus = 'queued'
    selected_stage: StageName = 'source'
    cancellation_requested: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    summary: str = ''
    # Pipeline-created runs replace this test-safe default with a content-addressed
    # implementation/configuration identity.  Keeping it explicit makes direct
    # repository fixtures usable without pretending that they came from production.
    version_id: str = 'test-default-v1'
    version_components: dict[str, str] = Field(default_factory=dict)
    version_state: Literal['comparable', 'unknown'] = 'comparable'
    total_elapsed_seconds: float | None = Field(default=None, ge=0)
    queued_seconds: float | None = Field(default=None, ge=0)
    active_seconds: float | None = Field(default=None, ge=0)
    # Monotonic timestamps are process/host-local. A missing origin is displayed
    # as unavailable instead of deriving a duration from wall-clock timestamps.
    timing_origin_monotonic: float | None = Field(default=None, ge=0)


class ReportBatch(V2Contract):
    batch_id: StableID
    requested_count: int = Field(ge=1)
    status: BatchStatus = 'queued'
    cancellation_requested: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    summary: str = ''


class ReportBatchItem(V2Contract):
    batch_id: StableID
    ordinal: int = Field(ge=1)
    ticker: str | None = Field(default=None, pattern=r'^[A-Z0-9][A-Z0-9.-]{0,19}$')
    run_id: StableID | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    outcome: BatchItemOutcome | None = None
    message: str = ''


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


class OutlineProposal(BaseModel):
    """The navigation-only object requested from the outline model."""
    model_config = ConfigDict(extra='ignore', frozen=True)

    generated_topic: str
    exact_source_title: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    exact_representative_quote: str | None = None
    section_type: str | None = None
    parent_topic_hint: str | None = None
    continues_previous: bool = False


class OutlineContinuation(BaseModel):
    """Validated navigation metadata carried into the next outline window."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    generated_topic: str
    exact_source_title: str | None = None
    end_line: int = Field(ge=1)
    parent_topic_hint: str | None = None


class OutlineRunSummary(V2Contract):
    """Persisted, run-specific accounting for the bounded outline pass."""
    source_line_count: int = Field(ge=0)
    window_count: int = Field(ge=0)
    live_requests: int = Field(ge=0)
    cached_batches: int = Field(ge=0)
    rejected_proposals: int = Field(ge=0)
    validated_ranges: int = Field(ge=0)
    models: list[str] = Field(default_factory=list)
    prompt_version: str = Field(min_length=1)


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
    exact_quote: str = Field(min_length=1)
    source_range: SourceRange
    amount: Decimal
    source_chunk_id: StableID | None = None
    target: str | None = None
    finding_type: FindingType = 'unresolved'
    unit: str | None = None
    period: str | None = None
    attribution: str | None = None
    limitations: list[str] = Field(default_factory=list)
    validation_state: Literal['validated', 'rejected', 'unresolved']
    model: str | None = None
    repair_attempted: bool = False
    bundle_id: StableID | None = None
    context_references: list[SourceRange] = Field(default_factory=list, max_length=200)
    source_chunk_ids: list[StableID] = Field(default_factory=list, max_length=10000)
    scale: str | None = None


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


class StatementDatasetRef(V2Contract):
    source_url: str
    source_hash: Hash
    retrieved_at: AwareDatetime
    accession: str
    quarter: str = Field(pattern=r'^\d{4}q[1-4]$')


class StatementNumericRecord(V2Contract):
    tag: str
    taxonomy_version: str
    period_end_month: date
    duration_quarters: int = Field(ge=0)
    unit: str
    value: Decimal
    coreg: str = ''
    segments: str = ''


class StatementLocation(V2Contract):
    tag: str
    taxonomy_version: str
    report: int = Field(ge=1)
    statement: str
    presentation_row: int = Field(ge=1)
    filer_label: str
    report_url: str | None = None


class FactPresentation(V2Contract):
    """Inspection-only SEC provenance; never a canonical filing-line claim."""
    fact_id: StableID
    status: Literal['matched', 'ambiguous', 'missing', 'retrieval_failed']
    dataset: StatementDatasetRef | None = None
    numeric_records: list[StatementNumericRecord] = Field(default_factory=list, max_length=10000)
    locations: list[StatementLocation] = Field(default_factory=list, max_length=10000)
    diagnostics: list[str] = Field(default_factory=list, max_length=20)
    method: Literal['sec-pre-num-v1'] = 'sec-pre-num-v1'


class FactSourceLocation(V2Contract):
    """Verified visible occurrence; display metadata never supplies comparator values."""
    fact_id: StableID
    source_range: SourceRange
    html_anchor: str
    quote: str = Field(min_length=1, max_length=20000)
    raw_dom_reference: str
    cell_dom_reference: str | None = None
    cell_text: str = Field(min_length=1, max_length=20000)
    inline_id: str | None = None
    concept_namespace: str
    context_id: str
    entity_identifier: str
    period_start: date
    period_end: date
    unit: str
    display_text: str = Field(min_length=1, max_length=1000)
    format: str | None = None
    format_namespace: str | None = None
    sign: Literal['', '-'] = ''
    scale: int = Field(ge=-100, le=100)
    displayed_value: Decimal
    transformed_value: Decimal
    header_context: list[str] = Field(default_factory=list, max_length=12)


class FactSourceMapping(V2Contract):
    fact_id: StableID
    status: Literal['verified', 'ambiguous', 'hidden_only', 'unavailable']
    method: Literal['inline-visible-1'] = 'inline-visible-1'
    document_id: StableID | None = None
    source_hash: Hash | None = None
    locations: list[FactSourceLocation] = Field(default_factory=list, max_length=1000)
    # Supporting concept presentations, not an assertion that PRE identifies a cell.
    presentation_references: list[StatementLocation] = Field(default_factory=list, max_length=10000)
    diagnostics: list[str] = Field(default_factory=list, max_length=20)


class FactComparison(V2Contract):
    comparison_id: StableID
    metric: str | None = None
    fact_id: StableID | None = None
    finding_ids: list[StableID] = Field(default_factory=list)
    state: Literal[
        'exact_match', 'value_match_period_unresolved', 'period_match_value_mismatch',
        'period_match_unit_mismatch',
        'structured_fact_missed', 'additional_visible_value', 'unsupported',
        'ambiguous_duplicate', 'scale_aware_equivalent', 'jev_rejected', 'jev_inconclusive',
    ]
    deterministic_state: str | None = None
    jev_verdict: bool | None = None
    jev_model: str | None = None
    jev_prompt_version: str | None = None
    requests_before_match: int | None = Field(default=None, ge=0)
    source_lines_before_match: int | None = Field(default=None, ge=0)
    evaluation_run_version: str | None = None
    evaluation_total_elapsed_seconds: float | None = Field(default=None, ge=0)


class PipelineEvent(V2Contract):
    sequence: int = Field(ge=1)
    run_id: StableID
    stage: StageName | None = None
    kind: Literal['run_created', 'stage_started', 'stage_finished', 'run_finished',
                  'cancellation_requested', 'resume_requested', 'run_cancelled', 'run_interrupted']
    status: StageStatus
    summary: str
    created_at: AwareDatetime
