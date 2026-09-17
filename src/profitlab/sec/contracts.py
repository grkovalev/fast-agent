from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from profitlab.contracts.base import CompanyIdentity, Contract
from profitlab.contracts.sources import FilingRecord


class TickerEntry(BaseModel):
    model_config = ConfigDict(extra='ignore')
    cik_str: int = Field(gt=0, le=9999999999)
    ticker: str = Field(min_length=1)
    title: str = Field(min_length=1)


class FilingArrays(BaseModel):
    model_config = ConfigDict(extra='ignore')
    accessionNumber: list[str]
    form: list[str]
    reportDate: list[str]
    filingDate: list[str]
    primaryDocument: list[str]

    @model_validator(mode='after')
    def aligned(self):
        if len({len(getattr(self, field)) for field in type(self).model_fields}) != 1:
            raise ValueError('SEC filing arrays have different lengths')
        return self

    def rows(self):
        return [dict(zip(type(self).model_fields, row)) for row in zip(
            *(getattr(self, field) for field in type(self).model_fields), strict=True)]


class HistoryFile(BaseModel):
    model_config = ConfigDict(extra='ignore')
    name: str = Field(pattern=r'^CIK\d{10}-submissions-\d+\.json$')
    filingTo: date | None = None


class FilingHistory(BaseModel):
    model_config = ConfigDict(extra='ignore')
    recent: FilingArrays
    files: list[HistoryFile] = Field(default_factory=list)


class Submissions(BaseModel):
    model_config = ConfigDict(extra='ignore')
    cik: int = Field(gt=0, le=9999999999)
    name: str
    filings: FilingHistory


class DiscoveryResult(Contract):
    outcome: Literal['found', 'not_found', 'ambiguous', 'unsupported', 'service_error']
    ticker: str
    company: CompanyIdentity | None = None
    filings: list[FilingRecord] = Field(default_factory=list)
    report_periods: list[date] = Field(default_factory=list)
    message: str
    error_code: str | None = None
    history_complete: bool = True
