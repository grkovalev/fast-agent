"""Untrusted proposals and inspectable extraction diagnostics."""
from decimal import Decimal
from typing import Literal

from pydantic import Field

from profitlab.contracts.base import Contract, FiscalPeriod, StableID
from profitlab.contracts.facts import FactCandidate, Metric


class FigureProposal(Contract):
    block_id: str
    cell_id: str
    metric: Metric
    raw_numeric_text: str
    value: Decimal
    scale: Decimal = Field(default=Decimal(1), gt=0)
    period: FiscalPeriod


class PassageProposal(Contract):
    block_id: str
    quote: str = Field(min_length=1)


class ExtractionOutput(Contract):
    figures: list[FigureProposal] = Field(default_factory=list)
    passages: list[PassageProposal] = Field(default_factory=list)


class ExtractionAttempt(Contract):
    attempt_id: StableID
    method: str
    status: Literal['accepted', 'ambiguous', 'rejected', 'unsupported']
    reasons: list[str]
    proposal: dict
    candidate: FactCandidate | None = None
    evidence_id: StableID | None = None
