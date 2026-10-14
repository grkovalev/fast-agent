"""One inspectable policy for the prepared JEV-led Findings components.

These are provisional application bounds, not verified provider token limits.
T70 supplies adapter enforcement; T76 activates them in the pipeline.
"""
import hashlib
import json
from enum import StrEnum
from math import ceil
from typing import Annotated

from pydantic import Field, model_validator

from profitlab.providers.jev import Probability

from .contracts import V2Contract
from .finding_concepts import CONCEPT_SCOPE, FindingConcept


class SupportDecision(StrEnum):
    SUPPORTED = 'supported'
    UNCERTAIN = 'uncertain'
    REJECTED = 'rejected'


class RequiredCondition(StrEnum):
    REQUESTED_YEAR = 'requested_year'
    ANNUAL_DURATION = 'annual_duration'
    REPORTED_BASIS = 'reported_basis'
    CONCEPT_SCOPE = 'concept_scope'


class JevPhaseBudget(V2Contract):
    serialized_characters: int = Field(default=20000, ge=1000, le=100000)
    questions: int = Field(default=64, ge=1, le=255)
    estimated_input_tokens: int = Field(default=8000, ge=256, le=32000)
    token_margin: int = Field(default=512, ge=0)
    characters_per_token: float = Field(default=3, gt=0, le=4)

    @model_validator(mode='after')
    def margin_fits(self):
        if self.token_margin >= self.estimated_input_tokens:
            raise ValueError('Token margin must leave room for request input')
        return self

    def admits(self, serialized_request: str, question_count: int) -> bool:
        # Include instructions/criteria/model/state overhead, never state alone.
        return (0 < question_count <= self.questions and
                len(serialized_request) <= self.serialized_characters and
                ceil(len(serialized_request) / self.characters_per_token) + self.token_margin
                <= self.estimated_input_tokens)


class FindingsPolicy(V2Contract):
    version: str = Field(default='findings-jev-policy-v1', min_length=1)
    question_version: str = Field(default='findings-jev-questions-v1', min_length=1)
    rubric_version: str = Field(default='findings-jev-rubric-v1', min_length=1)
    conversion_version: str = Field(default='findings-bundle-conversion-v1', min_length=1)
    source_support_threshold: Probability = .65
    source_uncertain_threshold: Probability = .20
    context_support_threshold: Probability = .65
    required_support_threshold: Probability = .65
    required_uncertain_threshold: Probability = .20
    assign_budget: JevPhaseBudget = Field(default_factory=JevPhaseBudget)
    attach_budget: JevPhaseBudget = Field(default_factory=JevPhaseBudget)
    rank_budget: JevPhaseBudget = Field(default_factory=JevPhaseBudget)
    max_candidate_lines: int = Field(default=1000, ge=1, le=10000)
    local_context_lines_each_direction: int = Field(default=12, ge=0, le=100)
    max_context_candidates_per_bundle: int = Field(default=40, ge=1, le=200)
    reserved_structural_context_candidates: int = Field(default=8, ge=0, le=200)
    max_selected_context_lines_per_bundle: int = Field(default=12, ge=0, le=200)
    max_bundles_per_concept: int = Field(default=3, ge=1, le=100)
    max_selected_bundles: int = Field(default=9, ge=1, le=300)
    max_selected_text_characters: int = Field(default=48000, ge=1000, le=1000000)
    max_jev_requests: int = Field(default=100, ge=1, le=2000)
    total_deadline_seconds: float = Field(default=300, gt=0, le=3600)
    conversion_request_characters: int = Field(default=60000, ge=1000, le=1000000)
    max_conversion_requests: int = Field(default=2, ge=1, le=20)
    max_repair_requests: int = Field(default=1, ge=0, le=1)

    @model_validator(mode='after')
    def coherent_bounds(self):
        if self.source_uncertain_threshold >= self.source_support_threshold:
            raise ValueError('Source uncertain threshold must be below support threshold')
        if self.required_uncertain_threshold >= self.required_support_threshold:
            raise ValueError('Required uncertain threshold must be below support threshold')
        if max(self.reserved_structural_context_candidates,
               self.max_selected_context_lines_per_bundle) > self.max_context_candidates_per_bundle:
            raise ValueError('Context reservations/selections exceed candidate cap')
        return self

    def source_decision(self, probability: Probability) -> SupportDecision:
        return support_decision(probability, self.source_uncertain_threshold,
                                self.source_support_threshold)

    def required_decision(self, probability: Probability) -> SupportDecision:
        return support_decision(probability, self.required_uncertain_threshold,
                                self.required_support_threshold)

    def required_conditions(self, concept: FindingConcept) -> dict[RequiredCondition, str]:
        return {
            RequiredCondition.REQUESTED_YEAR: 'The source row/bundle supports the requested fiscal-reporting year; comparative columns are allowed.',
            RequiredCondition.ANNUAL_DURATION: 'The reported value covers an annual period, not only a quarter.',
            RequiredCondition.REPORTED_BASIS: 'The value is reported, not adjusted, forecast or hypothetical.',
            RequiredCondition.CONCEPT_SCOPE: CONCEPT_SCOPE[concept],
        }

    def identity(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode='json'), sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()


def support_decision(probability: Annotated[float, Field(ge=0, le=1)],
                     uncertain: float, supported: float) -> SupportDecision:
    if not 0 <= probability <= 1:
        raise ValueError('Support probability must be finite and within [0, 1]')
    if probability >= supported:
        return SupportDecision.SUPPORTED
    return SupportDecision.UNCERTAIN if probability >= uncertain else SupportDecision.REJECTED


def build_findings_policy(settings) -> FindingsPolicy:
    """Settings owns only a validated policy, never secrets/provider inputs here."""
    return FindingsPolicy.model_validate(settings.findings_policy.model_dump())
