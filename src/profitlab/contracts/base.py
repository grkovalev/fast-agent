from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

StableID = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Missingness = Literal['missing', 'not_applicable', 'unsupported', 'conflicting']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class FiscalPeriod(Contract):
    start: date
    end: date
    fiscal_year: int = Field(ge=1900, le=2200)

    @model_validator(mode='after')
    def interval(self):
        if self.start >= self.end:
            raise ValueError('Fiscal period must have a positive interval')
        return self


class CompanyIdentity(Contract):
    ticker: str = Field(pattern=r'^[A-Z0-9][A-Z0-9.-]{0,19}$')
    name: str = Field(min_length=1)
    cik: str = Field(pattern=r'^\d{10}$')
    exchange: str | None = None
    other_tickers: list[str] = Field(default_factory=list)
    lookup_source: str
    lookup_at: AwareDatetime


class RunManifest(Contract):
    run_id: StableID
    mode: Literal['demo', 'replay', 'live']
    ticker: str
    company: CompanyIdentity | None = None
    requested_years: int = Field(default=4, ge=1, le=4)
    covered_years: list[int] = Field(default_factory=list)
    status: Literal['queued', 'running', 'completed', 'partial', 'failed', 'cancelled',
                    'interrupted'] = 'completed'
    stage: str = 'setup'
    created_at: AwareDatetime
    updated_at: AwareDatetime
    configuration: dict = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)
    provider_models: dict[str, str] = Field(default_factory=dict)
    artifact_ids: list[StableID] = Field(default_factory=list)
    limitation: str = 'Setup only. Financial processing is not implemented yet.'
