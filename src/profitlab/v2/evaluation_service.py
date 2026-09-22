"""Independent, non-mutating comparison of sealed discovery and SEC facts."""
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass

from .contracts import FactComparison, Finding, StructuredFact

# This application-owned mapping is intentionally used only after discovery is
# sealed.  It is never part of a Jev or findings-model payload.
TARGET_METRICS = {
    'annual_profit': 'net_income_consolidated',
    'diluted_eps': 'eps_diluted',
    'diluted_shares': 'weighted_average_shares_diluted',
}


@dataclass(frozen=True)
class EvaluationResult:
    comparisons: list[FactComparison]
    summary: dict


class EvaluationService:
    """Compare; never recover, rewrite, or otherwise improve discovery output."""

    def __init__(self, repository):
        self.repo = repository

    @staticmethod
    def _year(period):
        if not isinstance(period, str):
            return None
        match = re.search(r'(?<!\d)((?:19|20)\d{2})(?!\d)', period)
        return int(match.group(1)) if match else None

    @staticmethod
    def _unit_matches(finding: Finding, fact: StructuredFact):
        # A missing visible unit remains unresolved, rather than being guessed.
        return finding.unit is None or finding.unit.strip().lower() == fact.unit.lower()

    @staticmethod
    def _comparison_id(state, fact_id, finding_ids):
        material = '|'.join([state, fact_id or '', *sorted(finding_ids)])
        return 'comparison-' + hashlib.sha256(material.encode()).hexdigest()[:20]

    def compare(self, run_id: str) -> EvaluationResult:
        if self.repo.stage(run_id, 'findings').status != 'completed':
            raise ValueError('Findings must be sealed before independent evaluation begins.')
        if self.repo.stage(run_id, 'facts').status != 'completed':
            raise ValueError('Structured facts must be loaded before independent evaluation begins.')
        findings = self.repo.findings(run_id)
        facts = self.repo.structured_facts(run_id)
        # A repeated quote/number is overlap context, not another discovery event.
        unique_findings = {(item.exact_quote, item.raw_number): item for item in findings}.values()
        findings = list(unique_findings)
        by_metric = defaultdict(list)
        for fact in facts:
            by_metric[fact.metric].append(fact)
        comparisons, consumed = [], set()

        for metric, metric_facts in sorted(by_metric.items()):
            by_period = defaultdict(list)
            for fact in metric_facts:
                by_period[fact.period_end].append(fact)
            for period, period_facts in sorted(by_period.items()):
                candidates = [item for item in findings
                              if TARGET_METRICS.get(item.target) == metric]
                if len(period_facts) > 1:
                    comparisons.append(FactComparison(
                        comparison_id=self._comparison_id('ambiguous_duplicate', None,
                                                          [item.finding_id for item in candidates]),
                        metric=metric, fact_id=None,
                        finding_ids=[item.finding_id for item in candidates],
                        state='ambiguous_duplicate'))
                    consumed.update(item.finding_id for item in candidates)
                    continue
                fact = period_facts[0]
                same_value = [item for item in candidates if item.normalized_value == fact.value
                              and self._unit_matches(item, fact)]
                exact = [item for item in same_value if self._year(item.period) == fact.period_end.year]
                unresolved = [item for item in same_value if self._year(item.period) is None]
                period_value_mismatches = [item for item in candidates
                    if self._year(item.period) == fact.period_end.year
                    and item.normalized_value is not None and item.normalized_value != fact.value
                    and self._unit_matches(item, fact)]
                if exact:
                    state, matched = 'exact_match', exact
                elif unresolved:
                    state, matched = 'value_match_period_unresolved', unresolved
                elif period_value_mismatches:
                    state, matched = 'period_match_value_mismatch', period_value_mismatches
                else:
                    state, matched = 'structured_fact_missed', []
                consumed.update(item.finding_id for item in matched)
                comparisons.append(FactComparison(
                    comparison_id=self._comparison_id(state, fact.fact_id,
                                                      [item.finding_id for item in matched]),
                    metric=metric, fact_id=fact.fact_id,
                    finding_ids=[item.finding_id for item in matched], state=state,
                    requests_before_match=self._requests_before_match(run_id) if matched else None,
                    source_lines_before_match=min((item.source_range.start_line - 1 for item in matched),
                                                  default=None)))

        for finding in findings:
            if finding.finding_id in consumed:
                continue
            state = ('unsupported' if TARGET_METRICS.get(finding.target) is None
                     else 'additional_visible_value')
            comparisons.append(FactComparison(
                comparison_id=self._comparison_id(state, None, [finding.finding_id]),
                metric=TARGET_METRICS.get(finding.target), finding_ids=[finding.finding_id], state=state))
        comparisons.sort(key=lambda item: (item.metric or '', item.state, item.comparison_id))
        summary = self._summary(run_id, comparisons, facts)
        self.repo.save_comparisons(run_id, comparisons)
        self.repo.save_comparison_summary(run_id, summary)
        return EvaluationResult(comparisons, summary)

    def _requests_before_match(self, run_id):
        # These persisted batch counts are available without reading evaluation from discovery.
        chunk_summary = self.repo.chunk_score_summary(run_id) or {}
        finding_summary = self.repo.finding_summary(run_id) or {}
        return int(chunk_summary.get('calls', 0)) + int(finding_summary.get('calls', 0))

    def _summary(self, run_id, comparisons, facts):
        counts = {state: sum(item.state == state for item in comparisons)
                  for state in ('exact_match', 'value_match_period_unresolved',
                                'period_match_value_mismatch', 'structured_fact_missed',
                                'additional_visible_value', 'unsupported', 'ambiguous_duplicate')}
        # Expected-fact denominators deduplicate repeated comparative facts by
        # configured metric and fiscal period, including ambiguous candidates.
        expected = len({(item.metric, item.period_end) for item in facts})
        value_attempts = counts['exact_match'] + counts['value_match_period_unresolved'] + counts['period_match_value_mismatch']
        period_attempts = counts['exact_match'] + counts['period_match_value_mismatch']
        stages = self.repo.stages(run_id)
        chunk_summary = self.repo.chunk_score_summary(run_id) or {}
        finding_summary = self.repo.finding_summary(run_id) or {}
        retained_chars = int(chunk_summary.get('retained_characters', 0))
        canonical_characters = sum(
            len(line.text) for ref in self.repo.canonical_refs(run_id)
            for line in self.repo.canonical_document(run_id, ref.document_id).lines)
        return {
            **counts, 'expected_facts': expected, 'exact_matches': counts['exact_match'],
            'misses': counts['structured_fact_missed'],
            'additional_visible_numbers': counts['additional_visible_value'],
            'value_accuracy': counts['exact_match'] / value_attempts if value_attempts else None,
            'period_accuracy': counts['exact_match'] / period_attempts if period_attempts else None,
            'provider_requests': self._requests_before_match(run_id),
            'source_lines_before_first_match': min(
                (item.source_lines_before_match for item in comparisons
                 if item.state == 'exact_match' and item.source_lines_before_match is not None), default=None),
            'retained_document_percentage': (retained_chars / max(1, canonical_characters)) * 100,
            'time_to_first_finding_seconds': next((item.elapsed_seconds for item in stages
                                                    if item.stage == 'findings'), None),
            'total_latency_seconds': sum(item.elapsed_seconds for item in stages
                                         if item.stage in ('section_score', 'chunk_score', 'findings', 'facts')),
            'provider_usage': chunk_summary.get('usage', {}),
            'deterministic_recovery_applied': False,
            'discovery_output_mutated': False,
            'structured_facts_considered': len(facts),
            'finding_provider_calls': finding_summary.get('calls', 0),
        }
