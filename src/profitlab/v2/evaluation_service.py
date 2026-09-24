"""Independent, non-mutating comparison of sealed discovery and SEC facts."""
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass

from profitlab.providers.jev import JevRequest, NoulQuestion

from .contracts import FactComparison, Finding, StructuredFact
from .section_scoring import SectionScoringService

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


def cross_run_scorecard(repo) -> dict:
    """Aggregate sealed evaluation comparisons without re-running an evaluator.

    A missed value is an expected fact without a matching finding. This includes a
    visible-but-wrong value, because it still misses the expected value. An
    additional value has no expected fact, so mismatches always equal additional
    values plus missed values.
    """
    counts = {'heuristic_matches': 0, 'jev_matches': 0,
              'additional_values': 0, 'missed_values': 0}
    included_runs, excluded_runs = [], []
    for run in repo.runs():
        evaluation = repo.stage(run.run_id, 'evaluate')
        comparisons = repo.comparisons(run.run_id)
        if not evaluation or evaluation.status != 'completed' or not comparisons:
            reason = ('evaluation is not completed' if not evaluation or evaluation.status != 'completed'
                      else 'evaluation produced no comparable values')
            excluded_runs.append({'run': run, 'reason': reason})
            continue
        included_runs.append(run)
        for comparison in comparisons:
            heuristic_match = (comparison.deterministic_state or comparison.state) == 'exact_match'
            jev_match = comparison.state in {'exact_match', 'scale_aware_equivalent'}
            if comparison.fact_id:
                counts['heuristic_matches'] += heuristic_match
                counts['jev_matches'] += jev_match
                counts['missed_values'] += not jev_match
            elif comparison.state == 'additional_visible_value':
                counts['additional_values'] += 1
    counts['mismatches'] = counts['additional_values'] + counts['missed_values']
    denominator = counts['jev_matches'] + counts['mismatches']
    percentages = {key: (value / denominator * 100 if denominator else None)
                   for key, value in counts.items()}
    return {'counts': counts, 'percentages': percentages, 'denominator': denominator,
            'included_runs': included_runs, 'excluded_runs': excluded_runs}


class EvaluationService:
    """Compare; never recover, rewrite, or otherwise improve discovery output."""

    def __init__(self, settings_or_repository, repository=None):
        # The one-argument form remains useful for deterministic contract tests.
        self.settings = settings_or_repository if repository is not None else None
        self.repo = repository or settings_or_repository

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
    def _metric_for_finding(finding: Finding):
        """Use only the sealed Jev-assigned finite type; never reinterpret prose here."""
        return TARGET_METRICS.get(finding.finding_type)

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
        finding_groups = defaultdict(list)
        for item in findings:
            finding_groups[(item.exact_quote, item.amount)].append(item)
        findings = [items[0] for items in finding_groups.values()]

        def all_finding_ids(items):
            """Keep every persisted citation visible without double-counting its verdict."""
            return [duplicate.finding_id for item in items
                    for duplicate in finding_groups[(item.exact_quote, item.amount)]]
        by_metric = defaultdict(list)
        for fact in facts:
            by_metric[fact.metric].append(fact)
        comparisons, consumed = [], set()

        for metric, metric_facts in sorted(by_metric.items()):
            by_period = defaultdict(list)
            for fact in metric_facts:
                by_period[fact.period_end].append(fact)
            for period, period_facts in sorted(by_period.items()):
                candidates = [item for item in findings if self._metric_for_finding(item) == metric]
                if len(period_facts) > 1:
                    candidate_ids = all_finding_ids(candidates)
                    comparisons.append(FactComparison(
                        comparison_id=self._comparison_id('ambiguous_duplicate', None,
                                                          candidate_ids),
                        metric=metric, fact_id=None,
                        finding_ids=candidate_ids,
                        state='ambiguous_duplicate'))
                    consumed.update(candidate_ids)
                    continue
                fact = period_facts[0]
                same_value = [item for item in candidates if item.amount == fact.value
                              and self._unit_matches(item, fact)]
                same_value_unit_mismatches = [item for item in candidates
                                              if item.amount == fact.value
                                              and self._year(item.period) == fact.period_end.year
                                              and not self._unit_matches(item, fact)]
                exact = [item for item in same_value if self._year(item.period) == fact.period_end.year]
                unresolved = [item for item in same_value if self._year(item.period) is None]
                period_value_mismatches = [item for item in candidates
                    if self._year(item.period) == fact.period_end.year
                    and item.amount != fact.value]
                if exact:
                    state, matched = 'exact_match', exact
                elif unresolved:
                    state, matched = 'value_match_period_unresolved', unresolved
                elif same_value_unit_mismatches:
                    state, matched = 'period_match_unit_mismatch', same_value_unit_mismatches
                elif period_value_mismatches:
                    state, matched = 'period_match_value_mismatch', period_value_mismatches
                else:
                    state, matched = 'structured_fact_missed', []
                matched_ids = all_finding_ids(matched)
                consumed.update(matched_ids)
                comparisons.append(FactComparison(
                    comparison_id=self._comparison_id(state, fact.fact_id,
                                                      matched_ids),
                    metric=metric, fact_id=fact.fact_id,
                    finding_ids=matched_ids, state=state,
                    requests_before_match=self._requests_before_match(run_id) if matched else None,
                    source_lines_before_match=min((item.source_range.start_line - 1 for item in matched),
                                                  default=None)))

        for finding in findings:
            finding_ids = all_finding_ids([finding])
            if finding.finding_id in consumed:
                continue
            metric = self._metric_for_finding(finding)
            state = ('unsupported' if metric is None
                     else 'additional_visible_value')
            comparisons.append(FactComparison(
                comparison_id=self._comparison_id(state, None, finding_ids),
                metric=metric, finding_ids=finding_ids, state=state))
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
                                'period_match_value_mismatch', 'period_match_unit_mismatch', 'structured_fact_missed',
                                'additional_visible_value', 'unsupported', 'ambiguous_duplicate')}
        # Expected-fact denominators deduplicate repeated comparative facts by
        # configured metric and fiscal period, including ambiguous candidates.
        expected = len({(item.metric, item.period_end) for item in facts})
        value_attempts = (counts['exact_match'] + counts['value_match_period_unresolved'] +
                          counts['period_match_value_mismatch'] + counts['period_match_unit_mismatch'])
        period_attempts = counts['exact_match'] + counts['period_match_value_mismatch'] + counts['period_match_unit_mismatch']
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

    def _scale_context(self, run_id: str, finding: Finding):
        """Return only the cited core line plus separately labelled retained context."""
        document = self.repo.canonical_document(run_id, finding.source_range.document_id)
        core = document.slice(finding.source_range)
        contexts, retained_core = [], []
        if finding.source_chunk_id:
            try:
                chunk = self.repo.chunk(run_id, finding.source_chunk_id)
            except FileNotFoundError:
                chunk = None
            if chunk:
                retained_core = [{'line_number': line.line_number, 'text': line.text}
                                 for line in document.lines[chunk.core_range.start_line - 1:chunk.core_range.end_line]]
                for source_range in chunk.context_ranges:
                    contexts.extend({'line_number': line.line_number, 'text': line.text}
                                    for line in document.lines[source_range.start_line - 1:source_range.end_line])
        return {'declared_core_evidence_line': {'line_number': finding.source_range.start_line, 'text': core},
                'retained_chunk_core_lines': retained_core, 'retained_context_lines': contexts}

    def _request(self, finding: Finding, fact: StructuredFact, context: dict):
        state = {
            'finding': {'finding_id': finding.finding_id, 'amount': str(finding.amount),
                        'period': finding.period, 'unit': finding.unit,
                        'finding_type': finding.finding_type, **context},
            'structured_fact': {'fact_id': fact.fact_id, 'amount': str(fact.value),
                                'unit': fact.unit, 'fiscal_period_end': fact.period_end.isoformat()},
            'rule': ('Answer true only when the visible core/context explicitly states a scale or unit that '
                     'proves these are the same annual metric and value. Otherwise answer false. Never infer a conversion.'),
        }
        request = JevRequest(model=self.settings.typesafe_model,
            state=state, questions={'same_visible_scaled_value': NoulQuestion(
                instructions='Are these the same annual metric/value after an explicitly visible scale or unit?')})
        if len(json.dumps(request.model_dump(mode='json'))) > self.settings.evaluation_scale_request_char_budget:
            raise ValueError('Evaluation scale request exceeds the configured visible-context budget.')
        return request

    async def compare_with_scale_verdicts(self, run_id: str):
        """Apply bounded, post-seal Jev verdicts without changing either input source."""
        if self.settings is None:
            raise ValueError('Scale-aware evaluation requires settings.')
        result = self.compare(run_id)  # Preserve the deterministic baseline first.
        if self.settings.evaluation_scale_max_pairs == 0:
            return result
        facts = {item.fact_id: item for item in self.repo.structured_facts(run_id)}
        findings = {item.finding_id: item for item in self.repo.findings(run_id)}
        candidates = [(comparison, findings[finding_id], facts[comparison.fact_id])
                      for comparison in result.comparisons
                      if comparison.state in {'period_match_value_mismatch', 'period_match_unit_mismatch'} and comparison.fact_id in facts
                      for finding_id in comparison.finding_ids if finding_id in findings]
        candidates = candidates[:self.settings.evaluation_scale_max_pairs]
        configuration = hashlib.sha256(json.dumps({
            'max_pairs': self.settings.evaluation_scale_max_pairs,
            'request_budget': self.settings.evaluation_scale_request_char_budget}, sort_keys=True).encode()).hexdigest()
        configured_model = self.settings.typesafe_model
        client = SectionScoringService(self.settings, self.repo)._client(run_id, stage='evaluate')
        updated, calls, cached, usage = [], 0, 0, {'input_tokens': 0, 'output_tokens': 0}
        by_id = {item.comparison_id: item for item in result.comparisons}
        for comparison, finding, fact in candidates:
            context = self._scale_context(run_id, finding)
            request = self._request(finding, fact, context)
            pair_hash = hashlib.sha256(json.dumps(request.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
            saved = self.repo.evaluation_scale_verdict(pair_hash, self.settings.evaluation_scale_prompt_version,
                                                       configuration, configured_model)
            if saved:
                verdict, model = bool(saved['verdict']), saved['model']
                cached += 1
            else:
                response = await client.evaluate(request)
                calls += 1
                usage['input_tokens'] += response.usage.input_tokens
                usage['output_tokens'] += response.usage.output_tokens
                verdict, model = response.answers['same_visible_scaled_value'].noul >= .5, response.model
                self.repo.save_evaluation_scale_verdict(pair_hash, self.settings.evaluation_scale_prompt_version,
                                                        configuration, configured_model,
                                                        {'verdict': verdict, 'model': model})
            state = 'scale_aware_equivalent' if verdict else 'jev_rejected'
            by_id[comparison.comparison_id] = comparison.model_copy(update={
                'state': state, 'deterministic_state': comparison.state, 'jev_verdict': verdict,
                'jev_model': model, 'jev_prompt_version': self.settings.evaluation_scale_prompt_version})
        updated = list(by_id.values())
        updated.sort(key=lambda item: (item.metric or '', item.state, item.comparison_id))
        summary = self._summary(run_id, updated, list(facts.values()))
        summary.update({'scale_aware_equivalences': sum(item.state == 'scale_aware_equivalent' for item in updated),
                        'evaluation_jev_calls': calls, 'evaluation_jev_cached': cached,
                        'evaluation_jev_usage': usage, 'evaluation_jev_model': configured_model})
        self.repo.save_comparisons(run_id, updated)
        self.repo.save_comparison_summary(run_id, summary)
        return EvaluationResult(updated, summary)
