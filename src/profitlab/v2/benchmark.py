"""Immutable, post-run retrieval benchmark replays.

Gold review data is deliberately consumed here, after discovery has completed.  This
module has no provider client and must never be imported by a discovery service.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .contracts import SourceRange


class ReviewedRange(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    range: SourceRange
    kind: str = Field(pattern='^(relevant|misleading_quarterly|misleading_segment|misleading_non_gaap|explanation|comparability|irrelevant)$')
    metric: str | None = None


class RequiredFact(BaseModel):
    """A required fact with an optional evidence location after automatic generation."""
    model_config = ConfigDict(extra='forbid', frozen=True)
    metric: str
    fiscal_year: int = Field(ge=1900, le=2200)
    evidence_range: SourceRange | None = None


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    case_id: str
    split: str = Field(pattern='^(development|held_out)$')
    company_id: str
    accession: str
    source_hash: str
    reviewed_ranges: list[ReviewedRange]
    required_facts: list[RequiredFact]
    label_source: str = Field(default='reviewed', pattern='^(reviewed|automatic_post_run)$')


class BenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    dataset_version: str
    cases: list[BenchmarkCase]

    def case_for(self, *, ticker: str, accession: str | None, source_hash: str):
        # Company/accession identity is intentionally exact; a changed source must
        # be reviewed again rather than silently reusing a neighboring filing's gold.
        return next((item for item in self.cases
                     if item.company_id == ticker and item.accession == (accession or '')
                     and item.source_hash == source_hash), None)


def load_dataset(path: Path | None = None) -> BenchmarkDataset:
    """Load the checked-in review manifest; callers may inject a test manifest."""
    path = path or Path(__file__).parents[1] / 'fixtures' / 'benchmark' / 'v1.json'
    return BenchmarkDataset.model_validate_json(path.read_text())


def _overlap(left: SourceRange, right: SourceRange) -> bool:
    return left.document_id == right.document_id and left.start_line <= right.end_line and right.start_line <= left.end_line


def _selected_lines(ranges: list[SourceRange]) -> set[int]:
    return {line for item in ranges for line in range(item.start_line, item.end_line + 1)}


@dataclass(frozen=True)
class BenchmarkResult:
    payload: dict


class RetrievalBenchmarkService:
    """Replay deterministic selection policies over persisted, sealed run output."""

    def __init__(self, repository, settings=None):
        self.repo, self.settings = repository, settings

    @staticmethod
    def _score_selected(scores, *, policy: bool):
        if policy:
            return {item.item_id for item in scores if item.policy_decision in {'selected', 'uncertain'}}
        return {item.item_id for item in scores if max(item.target_scores.values(), default=0) >= .20}

    def _strategies(self, run_id):
        sections = self.repo.outline_sections(run_id)
        chunks = self.repo.chunks(run_id)
        section_scores = self.repo.scores(run_id, 'section_score')
        chunk_scores = self.repo.scores(run_id, 'chunk_score')
        document = self.repo.canonical_document(run_id, self.repo.canonical_refs(run_id)[0].document_id)
        keywords = ('income', 'profit', 'earnings', 'diluted', 'share', 'restatement', 'compar')
        keep_all = [item.primary_range for item in sections]
        keyword = [item.primary_range for item in sections if any(
            word in (item.generated_topic + ' ' + (item.exact_source_title or '') + ' ' + document.slice(item.primary_range)[:600]).lower()
            for word in keywords)]
        structural = [item.primary_range for item in sections if (item.exact_source_title or '').lower().startswith(('item ', 'consolidated', 'financial'))]
        jev_sections = self._score_selected(section_scores, policy=False)
        policy_sections = self._score_selected(section_scores, policy=True)
        jev_chunks = self._score_selected(chunk_scores, policy=False)
        policy_chunks = self._score_selected(chunk_scores, policy=True)
        by_section = {item.section_id: item.primary_range for item in sections}
        by_chunk = {item.chunk_id: item.core_range for item in chunks}
        return [
            ('keep_all', 'baseline', keep_all),
            ('heading_keyword', 'baseline', keyword),
            ('structural', 'baseline', structural),
            ('jev_section', 'jev_only', [by_section[item] for item in jev_sections if item in by_section]),
            ('jev_section', 'application_policy', [by_section[item] for item in policy_sections if item in by_section]),
            ('jev_section_chunk', 'jev_only', [by_chunk[item] for item in jev_chunks if item in by_chunk]),
            ('jev_section_chunk', 'application_policy', [by_chunk[item] for item in policy_chunks if item in by_chunk]),
        ]

    def automatic_case(self, run_id: str) -> BenchmarkCase:
        """Derive operational labels only after the run's comparison is sealed."""
        run, filing = self.repo.get_run(run_id), self.repo.filing(run_id)
        document = self.repo.canonical_document(run_id, filing['document_id'])
        findings = {item.finding_id: item for item in self.repo.findings(run_id)
                    if item.validation_state == 'validated'}
        comparisons = self.repo.comparisons(run_id)
        # A run's own findings can link an observed value to a structured fact
        # below, but they cannot be gold relevant ranges: treating them as gold
        # makes retrieval recall circular and trivially 1.0.
        required = []
        for fact in self.repo.structured_facts(run_id):
            comparison = next((item for item in comparisons if item.fact_id == fact.fact_id), None)
            evidence = next((findings[item].source_range for item in (comparison.finding_ids if comparison else [])
                             if item in findings), None)
            required.append(RequiredFact(metric=fact.metric, fiscal_year=fact.period_end.year,
                                         evidence_range=evidence))
        return BenchmarkCase(
            case_id='automatic-' + run_id, split='development', company_id=run.ticker,
            accession=filing.get('accession', ''), source_hash=document.ref.source_hash,
            reviewed_ranges=[], required_facts=required, label_source='automatic_post_run')

    def evaluate_automatic(self, run_id: str) -> BenchmarkResult:
        return self.evaluate(run_id, self.automatic_case(run_id),
                             provider_identity='automatic post-run replay')

    def evaluate(self, run_id: str, case: BenchmarkCase, *, provider_identity: str = 'replayed') -> BenchmarkResult:
        document = self.repo.canonical_document(run_id, self.repo.canonical_refs(run_id)[0].document_id)
        if document.ref.source_hash != case.source_hash:
            raise ValueError('Benchmark case source hash does not match this immutable canonical filing.')
        relevant = [item.range for item in case.reviewed_ranges if item.kind == 'relevant']
        misleading = [item.range for item in case.reviewed_ranges if item.kind.startswith('misleading_')]
        facts = self.repo.structured_facts(run_id)
        comparisons = self.repo.comparisons(run_id)
        findings = {item.finding_id: item for item in self.repo.findings(run_id)}
        comparison_by_fact = {item.fact_id: item for item in comparisons if item.fact_id}
        stage_seconds = sum(item.elapsed_seconds for item in self.repo.stages(run_id))
        rows = []
        for strategy, result_kind, ranges in self._strategies(run_id):
            selected = _selected_lines(ranges)
            relevant_hits = sum(bool(selected & _selected_lines([item])) for item in relevant)
            misleading_hits = sum(bool(selected & _selected_lines([item])) for item in misleading)
            covered, exact, wrong = 0, 0, 0
            first_match = None
            for required in case.required_facts:
                has_source = bool(required.evidence_range and selected & _selected_lines([required.evidence_range]))
                fact = next((item for item in facts if item.metric == required.metric and item.period_end.year == required.fiscal_year), None)
                if has_source and fact:
                    covered += 1
                comparison = comparison_by_fact.get(fact.fact_id) if fact else None
                linked = [findings[item] for item in (comparison.finding_ids if comparison else []) if item in findings]
                linked = [item for item in linked if item.source_range.start_line in selected]
                if linked and comparison and comparison.state in {'exact_match', 'scale_aware_equivalent'}:
                    exact += 1
                    first_match = min(first_match, min(item.source_range.start_line for item in linked)) if first_match else min(item.source_range.start_line for item in linked)
                elif linked:
                    wrong += 1
            source_lines = len(selected)
            total = document.ref.line_count
            rows.append({
                'strategy': strategy, 'result_kind': result_kind,
                'relevant_range_recall': round(relevant_hits / len(relevant), 4) if relevant else None,
                'structured_fact_coverage': round(covered / len(case.required_facts), 4) if case.required_facts else None,
                'exact_value_accuracy': round(exact / len(case.required_facts), 4) if case.required_facts else None,
                'wrong_metric_or_year_values': wrong,
                'recall_at_retained_source_budget': round(relevant_hits / len(relevant), 4) if relevant else None,
                'source_percentage_explored': round(source_lines / total, 4) if total else 0,
                'retained_source_lines': source_lines, 'misleading_ranges_retained': misleading_hits,
                'missed_ranges': [item.model_dump(mode='json') for item in relevant
                                  if not (selected & _selected_lines([item]))],
                'calls': 0 if strategy in {'keep_all', 'heading_keyword', 'structural'} else len(self.repo.exploration_actions(run_id, 'section_score')) + (len(self.repo.exploration_actions(run_id, 'chunk_score')) if strategy == 'jev_section_chunk' else 0),
                'usage': {}, 'latency_seconds': round(stage_seconds, 3),
                'source_lines_before_first_matching_fact': first_match,
                'targets_met': bool((not relevant or relevant_hits / len(relevant) >= .95) and (not case.required_facts or covered == len(case.required_facts)) and wrong == 0),
            })
        versions = {
            'dataset_version': 'reviewed-case', 'case_id': case.case_id, 'split': case.split,
            'provider_identity': provider_identity,
            'section_prompt_version': getattr(self.settings, 'section_score_prompt_version', 'persisted'),
            'chunk_prompt_version': getattr(self.settings, 'chunk_score_prompt_version', 'persisted'),
            'question_version': 'section-targets-v1',
            'model_ids': sorted({item.model for item in self.repo.scores(run_id, 'section_score') + self.repo.scores(run_id, 'chunk_score')}),
        }
        payload = {'case': case.model_dump(mode='json'), 'configuration': versions, 'results': rows,
                   'gold_access': 'post-run benchmark only; never supplied to Jev or findings requests'}
        payload['benchmark_hash'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.repo.save_retrieval_benchmark(run_id, payload)
        return BenchmarkResult(payload)
