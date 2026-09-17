from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .base import Contract, StableID


class FilingRecord(Contract):
    filing_id: StableID
    cik: str = Field(pattern=r'^\d{10}$')
    accession: str = Field(pattern=r'^\d{10}-\d{2}-\d{6}$')
    accession_compact: str | None = Field(default=None, pattern=r'^\d{18}$')
    form: str
    report_date: date
    filing_date: date
    primary_document_url: str
    amendment_of: StableID | None = None
    fetch_status: Literal['pending', 'saved', 'failed'] = 'pending'
    source_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def accession_identity(self):
        compact = self.accession.replace('-', '')
        if self.accession_compact is not None and self.accession_compact != compact:
            raise ValueError('Accession representations disagree')
        object.__setattr__(self, 'accession_compact', compact)
        return self


class SourceBlock(Contract):
    block_id: StableID
    filing_id: StableID
    dom_locator: str | None = None
    original_anchor: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    kind: Literal['heading', 'paragraph', 'table', 'note']
    text: str
    table_id: StableID | None = None
    page_label: str | None = None
    ordinal: int = Field(ge=0)


class TableCell(Contract):
    cell_id: StableID
    table_id: StableID
    row_id: StableID
    column_id: StableID
    raw_text: str
    normalized_text: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    header_cell_ids: list[StableID] = Field(default_factory=list)
    year_cell_ids: list[StableID] = Field(default_factory=list)
    unit_cell_ids: list[StableID] = Field(default_factory=list)
    xbrl_fact_ids: list[str] = Field(default_factory=list)


class Chunk(Contract):
    chunk_id: StableID
    filing_id: StableID
    block_ids: list[StableID]
    primary_block_ids: list[StableID]
    overlap_block_ids: list[StableID] = Field(default_factory=list)
    text: str
    token_estimate: int = Field(ge=0)
    estimator_version: str
    source_anchors: list[str]


class EvidenceRef(Contract):
    evidence_id: StableID
    filing_id: StableID
    block_id: StableID
    table_id: StableID | None = None
    cell_ids: list[StableID] = Field(default_factory=list)
    original_url: str
    original_anchor: str | None = None
    local_anchor: str
    exact_segments: list[str]
    normalized_offsets: list[tuple[int, int]] = Field(default_factory=list)
    page_label: str | None = None
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
