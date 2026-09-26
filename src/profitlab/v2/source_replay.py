"""Post-run source-row replay diagnostics for controlled T39 experiments.

The checked-in expectations are review data.  This module deliberately has no
provider client and must never be imported by discovery or findings services.
It makes the first loss point for a reviewed source row visible without turning
the expected rows into an input to retrieval, Jev, or the findings model.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ExpectedSourceRow(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    line_number: int = Field(ge=1)
    target: str = Field(pattern='^(annual_profit|diluted_eps|diluted_shares)$')
    note: str = Field(min_length=1, max_length=500)


class SourceReplayCase(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    case_id: str
    ticker: str
    accession: str
    source_hash: str = Field(pattern='^[0-9a-f]{64}$')
    rows: list[ExpectedSourceRow] = Field(min_length=1, max_length=25)


class SourceReplayDataset(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    dataset_version: str
    cases: list[SourceReplayCase]

    def case_for(self, *, ticker: str, accession: str | None, source_hash: str):
        return next((item for item in self.cases
                     if item.ticker == ticker and item.accession == (accession or '')
                     and item.source_hash == source_hash), None)


def load_source_replay_dataset(path: Path | None = None) -> SourceReplayDataset:
    path = path or Path(__file__).parents[1] / 'fixtures' / 'source_replay' / 't39-v1.json'
    return SourceReplayDataset.model_validate_json(path.read_text())


class SourceReplayService:
    """Trace reviewed rows through persisted pipeline checkpoints only."""

    def __init__(self, repository, dataset: SourceReplayDataset | None = None):
        self.repo = repository
        self.dataset = dataset or load_source_replay_dataset()

    def inspect(self, run_id: str) -> dict | None:
        run, filing = self.repo.get_run(run_id), self.repo.filing(run_id)
        document = self.repo.canonical_document(run_id, filing['document_id'])
        case = self.dataset.case_for(ticker=run.ticker, accession=filing.get('accession'),
                                     source_hash=document.ref.source_hash)
        if not case:
            return None

        selected_ids = {item.item_id for item in self.repo.scores(run_id, 'chunk_score')
                        if item.policy_decision == 'selected'}
        selected_chunks = [item for item in self.repo.chunks(run_id) if item.chunk_id in selected_ids]
        actions = [item for item in self.repo.exploration_actions(run_id, 'findings')
                   if item['action_id'] == 'findings-request']
        action = actions[-1] if actions else None
        request = action.get('request', {}) if action else {}
        requested_lines = {line.get('line_number')
                           for chunk in request.get('retained_chunks', [])
                           for line in chunk.get('core_evidence_lines', [])}
        audit = action.get('proposal_audit') if action else None
        findings = self.repo.findings(run_id)
        comparisons = self.repo.comparisons(run_id)
        matching_finding_ids = {finding_id for comparison in comparisons
                                if comparison.state in {'exact_match', 'scale_aware_equivalent'}
                                for finding_id in comparison.finding_ids}

        rows = []
        for expected in case.rows:
            row_findings = [item for item in findings
                            if item.source_range.start_line == expected.line_number]
            row_audit = ([item for item in audit if item.get('source_line') == expected.line_number]
                         if audit is not None else [])
            rows.append({
                'line_number': expected.line_number,
                'target': expected.target,
                'note': expected.note,
                'flat_retained': any(chunk.core_range.start_line <= expected.line_number <= chunk.core_range.end_line
                                     for chunk in selected_chunks),
                'sent_to_findings': expected.line_number in requested_lines if action else None,
                # Older runs intentionally report unknown here: their trace did not
                # retain raw proposal references, so absence cannot mean rejection.
                'proposed': bool(row_audit) if audit is not None else None,
                'quote_validated': any(item.get('quote_validated') for item in row_audit)
                                   if audit is not None else None,
                'classification': [item.finding_type for item in row_findings],
                'published': any(item.finding_type == expected.target for item in row_findings),
                'independent_match': any(item.finding_id in matching_finding_ids for item in row_findings),
            })
        return {'dataset_version': self.dataset.dataset_version, 'case_id': case.case_id,
                'trace_version': 't39-source-row-trace-v1',
                'proposal_audit_available': audit is not None, 'rows': rows,
                'non_leak_rule': 'Reviewed expected rows are post-run diagnostics and are never provider inputs.'}
