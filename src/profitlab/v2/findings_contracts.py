"""Prepared replacement domain contracts; no runtime or persistence activation.

References retain source identity; text exists once in a line candidate or request.
Provider answers remain independent from application decisions and omissions.
"""
import hashlib
import re
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from profitlab.providers.jev import NoulAnswer, Probability, TokenUsage

from .contracts import Finding, Hash, SourceRange, StableID, TextChunk, V2Contract
from .finding_concepts import FindingConcept
from .findings_policy import RequiredCondition, SupportDecision


class FindingsPhase(StrEnum):
    CANDIDATES = 'candidates'
    ASSIGN = 'assign_lines'
    ATTACH = 'attach_context'
    RANK = 'rank_select'
    CONVERT = 'convert'
    VALIDATE = 'validate'
    SEAL = 'seal'


class ContextRole(StrEnum):
    PERIOD = 'period_duration'
    UNIT = 'unit_scale'
    ENTITY = 'entity_attribution'
    QUALIFICATION = 'qualification_comparability'


class Omission(V2Contract):
    item_id: StableID
    reason: str = Field(min_length=1, max_length=2000)
    coverage_cut: bool
    # Threshold/rank exclusion is intentional; count/size omission cuts coverage.
    kind: Literal['relevance', 'selection', 'count_limit', 'size_limit', 'unavailable_context']


class ConceptChunkReference(V2Contract):
    chunk: TextChunk
    concept_score: Probability
    reason: str = Field(min_length=1)


class ConceptChunkCandidates(V2Contract):
    concept: FindingConcept
    relevance_threshold: Probability
    chunks: list[ConceptChunkReference] = Field(max_length=10000)
    omissions: list[Omission] = Field(default_factory=list, max_length=10000)

    @model_validator(mode='after')
    def admitted(self):
        ids = [x.chunk.chunk_id for x in self.chunks]
        if len(set(ids)) != len(ids) or any(x.concept_score < self.relevance_threshold for x in self.chunks):
            raise ValueError('Candidate chunks must be unique and above inclusion threshold')
        return self


# This parser only identifies displayed numeric spans; no metric/year inference.
_DIGITS = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+'
_NUMBER = re.compile(r'(?<![\w.])(?:\(\s*[−+-]?\s*(?:' + _DIGITS +
                     r')\s*\)|[−+-]\s*(?:' + _DIGITS + r')|(?:' + _DIGITS + r'))(?!\w|\.\d|,\d)')


def displayed_decimal(raw: str) -> Decimal:
    value = ''.join(raw.split()).replace(',', '').replace('−', '-')
    if value.startswith('(') and value.endswith(')'):
        # Parentheses denote a displayed loss, including redundant inner minus.
        value = '-' + value[1:-1].lstrip('+-')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Displayed amount must be finite')
    return result


class VisibleNumericSpan(V2Contract):
    start_character: int = Field(ge=0)
    end_character: int = Field(gt=0)
    raw_text: str = Field(min_length=1, max_length=1000)
    displayed_amount: Decimal

    @model_validator(mode='after')
    def exact_span(self):
        if (self.end_character - self.start_character != len(self.raw_text) or
                _NUMBER.fullmatch(self.raw_text) is None or
                displayed_decimal(self.raw_text) != self.displayed_amount):
            raise ValueError('Numeric span offsets/raw text/sign/amount disagree')
        return self


def visible_numeric_spans(text: str) -> list[VisibleNumericSpan]:
    return [VisibleNumericSpan(start_character=m.start(), end_character=m.end(),
                               raw_text=m.group(), displayed_amount=displayed_decimal(m.group()))
            for m in _NUMBER.finditer(text)]


def occurrence_id(concept: FindingConcept, source: SourceRange) -> str:
    """Reusable line occurrence ignores run-local document/chunk IDs."""
    key = f'{concept.value}:{source.source_hash}:{source.start_line}'
    return 'line-' + hashlib.sha256(key.encode()).hexdigest()[:32]


def same_document(left: SourceRange, right: SourceRange) -> bool:
    return left.document_id == right.document_id and left.source_hash == right.source_hash


def single_line(source: SourceRange):
    if source.start_line != source.end_line or source.start_character is not None:
        raise ValueError('Candidate references must be whole single canonical lines')


class FindingLineCandidate(V2Contract):
    candidate_id: StableID
    concept: FindingConcept
    source_range: SourceRange
    exact_text: str = Field(min_length=1, max_length=100000)
    section_id: StableID
    owners: list[ConceptChunkReference] = Field(min_length=1, max_length=10000)
    owning_chunk_id: StableID
    numeric_spans: list[VisibleNumericSpan] = Field(min_length=1, max_length=10000)

    @model_validator(mode='after')
    def source_owned(self):
        single_line(self.source_range)
        if self.candidate_id != occurrence_id(self.concept, self.source_range):
            raise ValueError('Candidate ID must identify its concept/source occurrence')
        owner_ids = [x.chunk.chunk_id for x in self.owners]
        if len(owner_ids) != len(set(owner_ids)) or self.owning_chunk_id not in owner_ids:
            raise ValueError('Unique eligible owners must include the chosen owner')
        for owner in self.owners:
            core = owner.chunk.core_range
            if (not same_document(core, self.source_range) or
                    owner.chunk.section_id != self.section_id or
                    not core.start_line <= self.source_range.start_line <= core.end_line):
                raise ValueError('Source candidate must belong to every eligible owner core/section')
        spans = [(x.start_character, x.end_character) for x in self.numeric_spans]
        if len(spans) != len(set(spans)):
            raise ValueError('Numeric spans must be unique')
        for span in self.numeric_spans:
            if self.exact_text[span.start_character:span.end_character] != span.raw_text:
                raise ValueError('Numeric span must match exact canonical line text')
        return self


class JudgmentProvenance(V2Contract):
    model: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    question_version: str = Field(min_length=1)
    policy_hash: Hash
    request_hash: Hash
    cached: bool = False


class ConceptLineAssignment(V2Contract):
    candidate_id: StableID
    concept: FindingConcept
    source_range: SourceRange
    answer: NoulAnswer
    decision: SupportDecision
    reason: str = Field(min_length=1)
    provenance: JudgmentProvenance

    @model_validator(mode='after')
    def identity_matches(self):
        single_line(self.source_range)
        if self.candidate_id != occurrence_id(self.concept, self.source_range):
            raise ValueError('Assignment source identity mismatch')
        return self


class ContextPoolRange(V2Contract):
    chunk_id: StableID
    section_id: StableID
    source_range: SourceRange
    kind: Literal['core', 'preceding_context']


class FindingContextPool(V2Contract):
    """Shared allowed coverage; canonical text is resolved only when requested."""
    concept: FindingConcept
    ranges: list[ContextPoolRange] = Field(max_length=100000)
    limitation: str = 'Only retained canonical coverage is available; external captions are unavailable.'


class FindingContextCandidate(V2Contract):
    link_id: StableID
    source_candidate_id: StableID
    context_range: SourceRange
    section_id: StableID
    owning_chunk_ids: list[StableID] = Field(min_length=1, max_length=10000)
    structural: bool


class ContextRoleAnswer(V2Contract):
    role: ContextRole
    answer: NoulAnswer
    decision: SupportDecision
    provenance: JudgmentProvenance


class FindingContextLink(V2Contract):
    link_id: StableID
    source_candidate_id: StableID
    concept: FindingConcept
    source_range: SourceRange
    context_range: SourceRange
    section_id: StableID
    owning_chunk_ids: list[StableID] = Field(min_length=1, max_length=10000)
    support: NoulAnswer
    provenance: JudgmentProvenance
    roles: list[ContextRoleAnswer] = Field(min_length=4, max_length=4)
    decision: Literal['selected', 'uncertain', 'rejected', 'omitted']
    reason: str = Field(min_length=1)

    @model_validator(mode='after')
    def context_identity(self):
        single_line(self.source_range)
        single_line(self.context_range)
        if not same_document(self.source_range, self.context_range):
            raise ValueError('Context must belong to source document/hash')
        if {x.role for x in self.roles} != set(ContextRole):
            raise ValueError('Context requires exactly one independent answer per role')
        if self.source_candidate_id != occurrence_id(self.concept, self.source_range):
            raise ValueError('Context source occurrence mismatch')
        return self


class FindingEvidenceBundle(V2Contract):
    bundle_id: StableID
    concept: FindingConcept
    source: FindingLineCandidate
    assignment: ConceptLineAssignment
    context_links: list[FindingContextLink] = Field(default_factory=list, max_length=200)
    unresolved_roles: list[ContextRole] = Field(default_factory=list, max_length=4)
    omissions: list[Omission] = Field(default_factory=list, max_length=10000)

    @model_validator(mode='after')
    def supported_source_and_selected_context(self):
        if (self.concept != self.source.concept or self.assignment.concept != self.concept or
                self.assignment.candidate_id != self.source.candidate_id or
                self.assignment.source_range != self.source.source_range or
                self.assignment.decision != SupportDecision.SUPPORTED):
            raise ValueError('Bundle requires its supported concept/source assignment')
        if self.bundle_id != 'bundle-' + self.source.candidate_id.removeprefix('line-'):
            raise ValueError('Bundle ID must identify source occurrence')
        seen = set()
        resolved = set()
        for link in self.context_links:
            if (link.source_candidate_id != self.source.candidate_id or link.concept != self.concept or
                    link.source_range != self.source.source_range or link.section_id != self.source.section_id or
                    link.decision != 'selected' or link.context_range.start_line in seen):
                raise ValueError('Bundle context must be selected, unique and source/section-owned')
            seen.add(link.context_range.start_line)
            resolved.update(x.role for x in link.roles if x.decision == SupportDecision.SUPPORTED)
        if (len(set(self.unresolved_roles)) != len(self.unresolved_roles) or
                set(self.unresolved_roles) != set(ContextRole) - resolved):
            raise ValueError('Unresolved roles must match missing selected role support')
        return self


class BundleScore(V2Contract):
    score: float = Field(ge=0, le=3)
    probabilities: dict[Literal['0', '1', '2', '3'], Probability] = Field(min_length=4, max_length=4)
    confidence: Probability
    rubric_version: str = Field(min_length=1)
    provenance: JudgmentProvenance

    @model_validator(mode='after')
    def distribution(self):
        if (abs(sum(self.probabilities.values()) - 1) > 1e-6 or
                abs(sum(int(k) * v for k, v in self.probabilities.items()) - self.score) > 1e-6):
            raise ValueError('Score must equal weighted complete rubric distribution')
        return self


class RequiredConditionAnswer(V2Contract):
    condition: RequiredCondition
    answer: NoulAnswer
    decision: SupportDecision
    provenance: JudgmentProvenance


class RankedFindingBundle(V2Contract):
    bundle_id: StableID
    concept: FindingConcept
    score: BundleScore
    required_conditions: list[RequiredConditionAnswer] = Field(min_length=4, max_length=4)
    eligibility: Literal['eligible', 'uncertain', 'ineligible']
    decision: Literal['selected', 'losing', 'uncertain', 'rejected', 'omitted']
    rank_within_concept: int | None = Field(default=None, ge=1)
    source_support: Probability
    upstream_concept_score: Probability
    source_range: SourceRange
    reason: str = Field(min_length=1)

    @model_validator(mode='after')
    def eligibility_gate(self):
        if {x.condition for x in self.required_conditions} != set(RequiredCondition):
            raise ValueError('Rank requires all independent required conditions')
        decisions = {x.decision for x in self.required_conditions}
        expected = ('ineligible' if SupportDecision.REJECTED in decisions else
                    'uncertain' if SupportDecision.UNCERTAIN in decisions else 'eligible')
        if self.eligibility != expected:
            raise ValueError('High Score cannot overrule required-condition decisions')
        allowed = {'eligible': {'selected', 'losing', 'omitted'},
                   'uncertain': {'uncertain', 'omitted'}, 'ineligible': {'rejected', 'omitted'}}
        if self.decision not in allowed[expected]:
            raise ValueError('Only eligible bundles can be selected')
        return self


class MetadataClaim(V2Contract):
    value: str = Field(min_length=1, max_length=1000)
    source_references: list[SourceRange] = Field(min_length=1, max_length=200)


class FindingConversionProposal(V2Contract):
    bundle_id: StableID
    concept: FindingConcept
    source_range: SourceRange
    numeric_span: VisibleNumericSpan
    exact_quote: str = Field(min_length=1, max_length=100000)
    amount: Decimal
    period: MetadataClaim | None = None
    unit: MetadataClaim | None = None
    scale: MetadataClaim | None = None
    attribution: MetadataClaim | None = None
    limitations: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def displayed_value(self):
        single_line(self.source_range)
        if self.amount != self.numeric_span.displayed_amount:
            raise ValueError('Amount must equal displayed value, with scale separate')
        for claim in (self.period, self.unit, self.scale, self.attribution):
            if claim:
                for reference in claim.source_references:
                    single_line(reference)
                    if not same_document(reference, self.source_range):
                        raise ValueError('Metadata must reference the same canonical document/hash')
        return self


class FindingPublicationProvenance(V2Contract):
    """T75 binds this provenance to Finding; current consumers stay unchanged."""
    finding: Finding
    concept: FindingConcept
    bundle_id: StableID
    numeric_span: VisibleNumericSpan
    context_references: list[SourceRange] = Field(default_factory=list, max_length=200)
    metadata_claims: dict[Literal['period', 'unit', 'scale', 'attribution'], MetadataClaim] = Field(default_factory=dict)

    @model_validator(mode='after')
    def published_identity(self):
        if (self.finding.finding_type != self.concept.value or
                self.finding.validation_state != 'validated' or
                self.finding.amount != self.numeric_span.displayed_amount):
            raise ValueError('Publication requires a validated fixed-concept displayed value')
        expected = 'bundle-' + occurrence_id(self.concept, self.finding.source_range).removeprefix('line-')
        if self.bundle_id != expected:
            raise ValueError('Publication bundle must identify the same concept/source occurrence')
        for source in self.context_references:
            if not same_document(source, self.finding.source_range):
                raise ValueError('Published context must share source identity')
        available = {(x.start_line, x.end_line) for x in self.context_references}
        available.add((self.finding.source_range.start_line, self.finding.source_range.end_line))
        for claim in self.metadata_claims.values():
            if any(not same_document(x, self.finding.source_range) or
                   (x.start_line, x.end_line) not in available for x in claim.source_references):
                raise ValueError('Published metadata must reference supplied source/context')
        return self


class ConversionDiagnostic(V2Contract):
    bundle_id: StableID
    proposal: FindingConversionProposal | None = None
    state: Literal['accepted', 'rejected', 'empty']
    reasons: list[str] = Field(default_factory=list, max_length=100)
    repaired: bool = False


class PhaseAccounting(V2Contract):
    planned: int = Field(default=0, ge=0)
    dispatched: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    cached: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    omitted: int = Field(default=0, ge=0)
    usage: TokenUsage | None = None
    elapsed_seconds: float = Field(default=0, ge=0)
    models: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def distinct_work(self):
        if self.completed + self.failed > self.dispatched:
            raise ValueError('Completed/failed requests must have been dispatched')
        if self.dispatched + self.cached + self.omitted > self.planned:
            raise ValueError('Live/cache/omitted work cannot exceed planned work')
        return self


class FindingsStepResult(V2Contract):
    phase: FindingsPhase
    status: Literal['pending', 'running', 'completed', 'partial', 'failed', 'cancelled', 'interrupted', 'skipped']
    availability: Literal['unavailable', 'checkpointed', 'final']
    input_hash: Hash
    policy_hash: Hash
    accounting: PhaseAccounting = Field(default_factory=PhaseAccounting)
    output_ids: list[StableID] = Field(default_factory=list, max_length=10000)
    omissions: list[Omission] = Field(default_factory=list, max_length=10000)
    reason: str | None = None

    @model_validator(mode='after')
    def result_state(self):
        if self.status == 'pending' and self.availability != 'unavailable':
            raise ValueError('Pending results are unavailable')
        if self.status in ('completed', 'partial', 'skipped') and self.availability != 'final':
            raise ValueError('Terminal successful/skipped steps have final availability')
        if self.status == 'completed' and any(x.coverage_cut for x in self.omissions):
            raise ValueError('Coverage omissions require a partial step')
        return self


class FindingsRunSummary(V2Contract):
    status: Literal['completed', 'partial', 'failed', 'cancelled', 'interrupted', 'running']
    sealed: bool = False
    policy_hash: Hash
    steps: list[FindingsStepResult] = Field(max_length=7)
    published_finding_ids: list[StableID] = Field(default_factory=list, max_length=10000)
    jev_assign: PhaseAccounting = Field(default_factory=PhaseAccounting)
    jev_attach: PhaseAccounting = Field(default_factory=PhaseAccounting)
    jev_rank: PhaseAccounting = Field(default_factory=PhaseAccounting)
    llm_conversion: PhaseAccounting = Field(default_factory=PhaseAccounting)
    llm_repair: PhaseAccounting = Field(default_factory=PhaseAccounting)
    rejection_count: int = Field(default=0, ge=0)
    limitation: str | None = None

    @model_validator(mode='after')
    def seal_gate(self):
        if len({x.phase for x in self.steps}) != len(self.steps):
            raise ValueError('Each Findings phase has one step result')
        if any(x.policy_hash != self.policy_hash for x in self.steps):
            raise ValueError('Summary steps must use the same policy')
        if self.sealed:
            if (self.status not in ('completed', 'partial') or len(self.steps) != 7 or
                    any(x.status not in ('completed', 'partial', 'skipped') for x in self.steps)):
                raise ValueError('Seal requires all seven successful terminal phases')
            if self.status == 'completed' and any(x.status == 'partial' for x in self.steps):
                raise ValueError('Partial coverage cannot seal as completed')
        elif self.published_finding_ids:
            raise ValueError('Unsealed work cannot publish findings')
        return self


class FindingsInputIdentity(V2Contract):
    """Caller supplies a digest of exact safe inputs with local IDs remapped out."""
    canonical_source_hashes: list[Hash] = Field(min_length=1, max_length=100)
    exact_inputs_hash: Hash
    concept: FindingConcept | None = None
    phase: FindingsPhase
    policy_hash: Hash
    question_version: str = Field(min_length=1)
    model_identity: str = Field(min_length=1)

    def cache_key(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class FindingsFilingMetadata(V2Contract):
    ticker: str = Field(pattern=r'^[A-Z0-9][A-Z0-9.-]{0,19}$')
    filing_id: StableID
    report_date: date


class VisibleFindingLine(V2Contract):
    source_range: SourceRange
    exact_text: str = Field(min_length=1, max_length=100000)

    @model_validator(mode='after')
    def whole_line(self):
        single_line(self.source_range)
        return self


class AssignmentState(V2Contract):
    filing: FindingsFilingMetadata
    candidate_id: StableID
    concept: FindingConcept
    candidate: VisibleFindingLine
    concept_definition: str = Field(min_length=1)

    @model_validator(mode='after')
    def candidate_identity(self):
        if self.candidate_id != occurrence_id(self.concept, self.candidate.source_range):
            raise ValueError('Assignment state identity must match concept/source')
        return self


class ContextState(V2Contract):
    filing: FindingsFilingMetadata
    source_candidate_id: StableID
    concept: FindingConcept
    source: VisibleFindingLine
    context: VisibleFindingLine
    concept_definition: str = Field(min_length=1)

    @model_validator(mode='after')
    def same_source(self):
        if not same_document(self.source.source_range, self.context.source_range):
            raise ValueError('Context request must reference the source document/hash')
        if self.source_candidate_id != occurrence_id(self.concept, self.source.source_range):
            raise ValueError('Context state identity must match concept/source')
        return self


class ConversionBundleInput(V2Contract):
    bundle_id: StableID
    concept: FindingConcept
    source: VisibleFindingLine
    numeric_spans: list[VisibleNumericSpan] = Field(min_length=1, max_length=10000)
    context: list[VisibleFindingLine] = Field(default_factory=list, max_length=200)
    context_roles: dict[ContextRole, list[int]] = Field(default_factory=dict)
    unresolved_roles: list[ContextRole] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def owned_context(self):
        expected = 'bundle-' + occurrence_id(self.concept, self.source.source_range).removeprefix('line-')
        if self.bundle_id != expected:
            raise ValueError('Conversion bundle identity must match concept/source')
        for line in self.context:
            if not same_document(line.source_range, self.source.source_range):
                raise ValueError('Conversion context must share source document/hash')
        available = {x.source_range.start_line for x in self.context} | {self.source.source_range.start_line}
        if any(n not in available for nums in self.context_roles.values() for n in nums):
            raise ValueError('Conversion roles must reference supplied lines')
        for span in self.numeric_spans:
            if self.source.exact_text[span.start_character:span.end_character] != span.raw_text:
                raise ValueError('Conversion numeric span must match source')
        return self


class ConversionState(V2Contract):
    filing: FindingsFilingMetadata
    selected_bundles: list[ConversionBundleInput] = Field(min_length=1, max_length=300)

    @model_validator(mode='after')
    def unique_bundles(self):
        ids = [x.bundle_id for x in self.selected_bundles]
        if len(set(ids)) != len(ids):
            raise ValueError('Conversion bundles must be unique')
        return self


class RankState(V2Contract):
    filing: FindingsFilingMetadata
    bundle: ConversionBundleInput
    concept_definition: str = Field(min_length=1)
    required_conditions: dict[RequiredCondition, str] = Field(min_length=4, max_length=4)
    rubric: list[str] = Field(min_length=4, max_length=4)
