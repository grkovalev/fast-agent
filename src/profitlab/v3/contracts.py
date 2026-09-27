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
    budget_state: dict[str, int | float] = Field(default_factory=dict)
    request_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    response_status: str
    # A model declaration about this source-cited frontier; never inferred by
    # application policy from document structure or graph labels.
    answerability: Literal['sufficient', 'insufficient'] | None = None
    elapsed_seconds: float = Field(ge=0)
    created_at: datetime


class GraphPath(V3Contract):
    path_id: str = Field(pattern=r'^path-[a-f0-9]{16}$')
    document_id: str
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    node_ids: list[str] = Field(min_length=1)
    edge_ids: list[str] = Field(default_factory=list)
    source_ranges: list[SourceRange] = Field(min_length=1)
    status: Status = 'accepted'


class AnswerClaim(V3Contract):
    """One answer assertion with its independently inspectable source path."""
    claim: str = Field(min_length=1, max_length=4000)
    path_ids: list[str] = Field(min_length=1)
    source_ranges: list[SourceRange] = Field(min_length=1)


class AnswerCandidate(V3Contract):
    answer_id: str = Field(pattern=r'^answer-[a-f0-9]{16}$')
    experiment_id: str
    answer: str = Field(min_length=1, max_length=10000)
    limitation: str | None = Field(default=None, max_length=2000)
    path_ids: list[str] = Field(min_length=1)
    source_ranges: list[SourceRange] = Field(min_length=1)
    claims: list[AnswerClaim] = Field(min_length=1)
    status: Literal['accepted', 'limited', 'rejected']
    model: str
    prompt_version: str

    @model_validator(mode='before')
    @classmethod
    def upgrade_legacy_claims(cls, value):
        """Read answer rows written before G5 added claim-level provenance."""
        if isinstance(value, dict) and 'claims' not in value:
            value = dict(value)
            value['claims'] = [{
                'claim': value.get('answer', ''),
                'path_ids': value.get('path_ids', []),
                'source_ranges': value.get('source_ranges', []),
            }]
        return value


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
    frontier_state: Literal['active', 'exhausted', 'partial', 'answered', 'budget_exhausted'] = 'active'


class GraphAnswer(V3Contract):
    manifest: ExperimentManifest
    answer: AnswerCandidate
    paths: list[GraphPath]
    cited_text: dict[str, str]

    @model_validator(mode='after')
    def citations_have_paths(self):
        available = {path.path_id for path in self.paths}
        if not set(self.answer.path_ids) <= available:
            raise ValueError('Answer cites a missing graph path')
        if any(not set(claim.path_ids) <= available for claim in self.answer.claims):
            raise ValueError('Answer claim cites a missing graph path')
        return self


# G6 contracts are deliberately post-seal.  They describe a reviewer-supplied,
# frozen comparison record; none are accepted by graph construction or answer
# synthesis.
ReviewMethod = Literal['graph', 'v2_packet', 'bounded_window']
AnswerSupport = Literal['supported', 'partial', 'unsupported', 'unresolved']
AmbiguityHandling = Literal['handled', 'disclosed', 'forced', 'not_applicable']


class FrozenArtifact(V3Contract):
    """One immutable method result attached after every provider call has ended."""
    artifact_id: str = Field(min_length=1, max_length=200)
    method: ReviewMethod
    source_ranges: list[SourceRange] = Field(min_length=1)
    citation_ranges: list[SourceRange] = Field(default_factory=list)
    graph_path_ids: list[str] = Field(default_factory=list)
    answer_support: AnswerSupport
    ambiguity_handling: AmbiguityHandling
    provider_calls: int = Field(ge=0)
    provider_input_tokens: int | None = Field(default=None, ge=0)
    provider_output_tokens: int | None = Field(default=None, ge=0)
    latency_seconds: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class PostSealCase(V3Contract):
    """A held-out question and its reviewed coverage ranges, never model input."""
    case_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
    experiment_id: str = Field(pattern=r'^v3-[a-f0-9]{16}$')
    question: str = Field(min_length=1, max_length=4000)
    required_ranges: list[SourceRange] = Field(min_length=1)
    artifacts: list[FrozenArtifact] = Field(min_length=1)


class RubricCohort(V3Contract):
    """An immutable, held-out evaluation cohort in the isolated V3 repository."""
    cohort_id: str = Field(pattern=r'^cohort-[a-f0-9]{16}$')
    rubric_version: str = Field(min_length=1, max_length=200)
    configuration_id: str = Field(min_length=1, max_length=200)
    held_out: bool
    cases: list[PostSealCase] = Field(min_length=1)
    created_at: datetime


class ArtifactRubric(V3Contract):
    case_id: str
    artifact_id: str
    method: ReviewMethod
    source_coverage: float = Field(ge=0, le=1)
    citation_valid: bool
    path_fidelity: Literal['valid', 'invalid', 'not_applicable']
    answer_support: AnswerSupport
    ambiguity_handling: AmbiguityHandling
    provider_calls: int = Field(ge=0)
    provider_input_tokens: int | None = Field(default=None, ge=0)
    provider_output_tokens: int | None = Field(default=None, ge=0)
    latency_seconds: float | None = Field(default=None, ge=0)


class RubricReport(V3Contract):
    cohort: RubricCohort
    artifacts: list[ArtifactRubric]
    method_summary: dict[ReviewMethod, dict[str, int | float | None]]


# G6b is intentionally a different, development-only post-run ledger.  It has
# no frozen alternate methods and is never accepted by graph construction.
class DevelopmentConfiguration(V3Contract):
    """The complete fixed graph identity selected before this cohort runs."""
    application_revision: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=200)
    budgets: dict[str, int | float] = Field(min_length=1)


class DevelopmentCase(V3Contract):
    """Reviewer/SEC annotations attached only to an already-sealed V3 run."""
    case_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
    experiment_id: str = Field(pattern=r'^v3-[a-f0-9]{16}$')
    question: str = Field(min_length=1, max_length=4000)
    ground_truth_ranges: list[SourceRange] = Field(min_length=1)
    answer_support: AnswerSupport
    ambiguity_handling: AmbiguityHandling
    notes: str | None = Field(default=None, max_length=2000)


class DevelopmentCohort(V3Contract):
    cohort_id: str = Field(pattern=r'^development-cohort-[a-f0-9]{16}$')
    ledger_version: Literal['g6b-development-v1'] = 'g6b-development-v1'
    held_out: Literal[False] = False
    configuration_id: str = Field(min_length=1, max_length=200)
    configuration: DevelopmentConfiguration
    cases: list[DevelopmentCase] = Field(min_length=1)
    created_at: datetime


class DevelopmentCaseRubric(V3Contract):
    case_id: str
    experiment_id: str
    ground_truth_coverage: float = Field(ge=0, le=1)
    exact_citations_valid: bool
    answer_support: AnswerSupport
    ambiguity_handling: AmbiguityHandling
    action_count: int = Field(ge=0)
    continuation_count: int = Field(ge=0)
    terminal_frontier_state: str
    provider_calls: int = Field(ge=0)
    provider_input_tokens: int | None = Field(default=None, ge=0)
    provider_output_tokens: int | None = Field(default=None, ge=0)
    latency_seconds: float | None = Field(default=None, ge=0)


class DevelopmentLedgerReport(V3Contract):
    cohort: DevelopmentCohort
    cases: list[DevelopmentCaseRubric]
    summary: dict[str, int | float | None]


# G6b.1 deliberately does not extend the post-seal ledger above.  A campaign is
# the pre-run boundary: it seals every input that can affect a graph request or
# traversal before the first development filing is acquired.
class CampaignConfiguration(V3Contract):
    application_revision: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    exploration_prompt_version: str = Field(min_length=1, max_length=200)
    answer_prompt_version: str = Field(min_length=1, max_length=200)
    request_schema_version: str = Field(min_length=1, max_length=200)
    relation_vocabulary: tuple[Relation, ...] = Field(min_length=1)
    source_window_lines: int = Field(ge=10, le=1000)
    source_window_overlap_lines: int = Field(ge=0, le=300)
    max_actions: int = Field(ge=1, le=100)
    max_total_source_characters: int = Field(ge=1000, le=1000000)
    max_wall_seconds: float = Field(gt=0, le=1800)
    continuation_policy_version: str = Field(min_length=1, max_length=200)
    stopping_policy_version: str = Field(min_length=1, max_length=200)


class DevelopmentCampaign(V3Contract):
    campaign_id: str = Field(pattern=r'^campaign-[a-f0-9]{16}$')
    campaign_version: Literal['g6b-campaign-v1'] = 'g6b-campaign-v1'
    question: str = Field(min_length=1, max_length=4000)
    configuration: CampaignConfiguration
    created_at: datetime


class CampaignRun(V3Contract):
    run_id: str = Field(pattern=r'^campaign-run-[a-f0-9]{16}$')
    campaign_id: str = Field(pattern=r'^campaign-[a-f0-9]{16}$')
    ticker: str = Field(pattern=r'^[A-Z][A-Z0-9.-]{0,19}$')
    status: Literal['queued', 'running', 'sealed', 'failed', 'interrupted']
    experiment_id: str | None = Field(default=None, pattern=r'^v3-[a-f0-9]{16}$')
    error: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
