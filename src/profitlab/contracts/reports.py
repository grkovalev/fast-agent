from decimal import Decimal
from typing import Literal

from pydantic import Field

from .base import Contract, StableID


class Calculation(Contract):
    calculation_id: StableID
    formula: str
    formula_version: str
    input_ids: list[StableID]
    results: dict[str, Decimal] = Field(default_factory=dict)
    status: Literal['applicable', 'missing', 'not_applicable', 'unsupported', 'conflicting']
    metric: str = ''
    years: list[int] = Field(default_factory=list)
    reason: str = ''
    label: str = ''
    evidence_ids: list[StableID] = Field(default_factory=list)
    input_values: list[Decimal] = Field(default_factory=list)
    rounding_policy: str
    display_policy: str


class ReportSentence(Contract):
    sentence_id: StableID
    text: str
    kind: Literal['comparison', 'management_explanation', 'interpretation', 'coverage', 'limitation']
    fact_ids: list[StableID] = Field(default_factory=list)
    calculation_ids: list[StableID] = Field(default_factory=list)
    evidence_ids: list[StableID] = Field(default_factory=list)
    attribution: str
    validation_state: Literal['pending', 'valid', 'invalid'] = 'pending'


class Report(Contract):
    report_id: StableID
    company_id: str
    covered_years: list[int]
    summary: str
    sentences: list[ReportSentence]
    table_fact_ids: list[StableID]
    table_calculation_ids: list[StableID]
    limitations: list[str]
    source_index: list[StableID]
    validation_status: Literal['pending', 'valid', 'invalid', 'partial']
