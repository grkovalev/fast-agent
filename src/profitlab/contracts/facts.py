from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .base import Contract, FiscalPeriod, Missingness, Probability, StableID


class Metric(StrEnum):
    NET_INCOME_COMMON = 'net_income_common'
    NET_INCOME_PARENT = 'net_income_parent'
    NET_INCOME_CONSOLIDATED = 'net_income_consolidated'
    EPS_DILUTED = 'eps_diluted'
    SHARES_DILUTED = 'weighted_average_shares_diluted'


class ScreeningDecision(Contract):
    decision_id: StableID
    chunk_id: StableID
    prompt_version: str
    probabilities: dict[str, Probability]
    decision: Literal['keep', 'uncertain', 'drop']
    reasons: list[str]
    provider_call_id: StableID
    actual_model: str
    structural_override: bool = False
    recovery_for: list[str] = Field(default_factory=list)
    error: str | None = None
    synthetic: bool = False
    cache_key: str = ''
    requested_model: str = ''
    alias_uncertainty: bool = False
    token_usage: dict[str, int] = Field(default_factory=dict)


class FactCandidate(Contract):
    candidate_id: StableID
    metric: Metric
    raw_label: str
    raw_numeric_text: str
    value: Decimal
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    unit: Literal['currency', 'currency_per_share', 'shares']
    scale: Decimal = Field(default=Decimal(1), gt=0)
    period: FiscalPeriod
    annuality: Literal['annual', 'quarterly', 'ytd', 'unknown']
    basis: Literal['gaap', 'adjusted', 'unknown']
    scope: Literal['consolidated', 'segment', 'unknown']
    attribution: str
    share_class: str | None = None
    extraction_method: str
    evidence_ids: list[StableID] = Field(min_length=1)
    validation_results: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode='after')
    def units(self):
        expected = ('currency_per_share' if self.metric == Metric.EPS_DILUTED else
                    'shares' if self.metric == Metric.SHARES_DILUTED else 'currency')
        if self.unit != expected or (self.unit != 'shares' and self.currency is None):
            raise ValueError('Metric and currency/unit are inconsistent')
        if self.unit == 'shares' and self.currency is not None:
            raise ValueError('Share counts cannot have a currency')
        return self


class CandidateGroup(Contract):
    group_id: StableID
    metric: Metric
    period: FiscalPeriod
    unit: str
    currency: str | None = None
    scope: str
    attribution: str
    share_class: str | None = None
    basis: str
    annuality: str = 'annual'
    candidate_ids: list[StableID] = Field(min_length=1)
    selected_id: StableID | None = None
    duplicate_groups: list[list[StableID]] = Field(default_factory=list)
    selection_reasons: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    latest_comparative_id: StableID | None = None

    @model_validator(mode='after')
    def selection(self):
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError('Candidate group IDs must be unique')
        if self.latest_comparative_id and self.latest_comparative_id not in self.candidate_ids:
            raise ValueError('Latest comparative must belong to the group')
        if any(len(ids) < 2 or not set(ids) <= set(self.candidate_ids)
               for ids in self.duplicate_groups):
            raise ValueError('Duplicate sets must contain group members')
        if self.selected_id and self.selected_id not in self.candidate_ids:
            raise ValueError('Selected candidate must belong to the group')
        if self.selected_id and self.unresolved_conflicts:
            raise ValueError('Unresolved conflicts cannot have a selected candidate')
        return self


class AnnualObservation(Contract):
    observation_id: StableID
    period: FiscalPeriod
    selected_facts: dict[Metric, StableID] = Field(default_factory=dict)
    missingness: dict[Metric, Missingness] = Field(default_factory=dict)
    comparability_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[StableID] = Field(default_factory=list)

    @model_validator(mode='after')
    def availability(self):
        if self.selected_facts.keys() & self.missingness.keys():
            raise ValueError('A metric cannot be both selected and missing')
        if set(self.selected_facts) | set(self.missingness) != set(Metric):
            raise ValueError('Every metric requires a selected fact or explicit missingness')
        return self
