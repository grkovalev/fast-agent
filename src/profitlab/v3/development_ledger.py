"""G6b post-run development ledger.

This scorer reads sealed V3 audit records only.  It deliberately imports neither
the graph service nor provider adapters: reviewer/SEC ground truth cannot become
an exploration or answer input through this module.
"""
from collections.abc import Iterable

from .contracts import DevelopmentCaseRubric, DevelopmentCohort, DevelopmentLedgerReport
from .rubric import PostSealRubricService


class DevelopmentLedgerService:
    ledger_version = 'g6b-development-v1'
    _EXCLUDED_TICKERS = frozenset({'FGN', 'CRVL', 'SPRO', 'WOR', 'MSFT'})

    @staticmethod
    def _matches_configuration(manifest, configuration) -> bool:
        return (manifest.application_revision == configuration.application_revision and
                manifest.model == configuration.model and
                manifest.prompt_version == configuration.prompt_version and
                manifest.budgets == configuration.budgets)

    @staticmethod
    def _range_is_exact(document, source) -> bool:
        if (source.document_id != document.ref.document_id or
                source.source_hash != document.ref.source_hash):
            return False
        # slice performs the canonical bounds and character-coordinate validation;
        # it never consults a provider or any document-layout inference.
        try:
            document.slice(source)
        except ValueError:
            return False
        return True

    @staticmethod
    def _citation_valid(document, answers, paths) -> bool:
        path_lookup = {path.path_id: path for path in paths}
        if not answers:
            return False
        for answer in answers:
            selected = [path_lookup.get(path_id) for path_id in answer.path_ids]
            if not selected or any(path is None for path in selected):
                return False
            for citation in answer.source_ranges:
                if not DevelopmentLedgerService._range_is_exact(document, citation):
                    return False
                if not any(PostSealRubricService._contains(path_range, citation)
                           for path in selected for path_range in path.source_ranges):
                    return False
        return True

    @staticmethod
    def _coverage(required, evidence: Iterable) -> float:
        evidence = list(evidence)
        return sum(any(PostSealRubricService._contains(found, expected) for found in evidence)
                   for expected in required) / len(required)

    @classmethod
    def score(cls, cohort: DevelopmentCohort, repository) -> DevelopmentLedgerReport:
        if cohort.ledger_version != cls.ledger_version or cohort.held_out:
            raise ValueError('G6b requires the non-held-out g6b-development-v1 ledger contract.')
        rows = []
        seen_experiments = set()
        for case in cohort.cases:
            if case.experiment_id in seen_experiments:
                raise ValueError(f'{case.case_id}: an experiment may appear only once in a G6b cohort.')
            seen_experiments.add(case.experiment_id)
            inspection = repository.inspection(case.experiment_id)
            manifest, document = inspection['manifest'], inspection['document']
            if manifest.ticker in cls._EXCLUDED_TICKERS:
                raise ValueError(f'{case.case_id}: {manifest.ticker} is excluded from G6b development cases.')
            if manifest.finished_at is None or manifest.frontier_state == 'active':
                raise ValueError(f'{case.case_id}: ground truth may attach only after the graph run is sealed.')
            if case.question != manifest.question:
                raise ValueError(f'{case.case_id}: question does not match its sealed graph experiment.')
            if not cls._matches_configuration(manifest, cohort.configuration):
                raise ValueError(f'{case.case_id}: experiment does not match the fixed G6b configuration.')
            for expected in case.ground_truth_ranges:
                if not cls._range_is_exact(document, expected):
                    raise ValueError(f'{case.case_id}: ground-truth range is not an exact canonical range.')
            evidence = [source for item in [*inspection['nodes'], *inspection['edges']]
                        for source in item.evidence_ranges if cls._range_is_exact(document, source)]
            evidence.extend(source for answer in inspection['answers'] for source in answer.source_ranges
                            if cls._range_is_exact(document, source))
            actions = inspection['actions']
            rows.append(DevelopmentCaseRubric(
                case_id=case.case_id, experiment_id=case.experiment_id,
                ground_truth_coverage=cls._coverage(case.ground_truth_ranges, evidence),
                exact_citations_valid=cls._citation_valid(document, inspection['answers'], inspection['paths']),
                answer_support=case.answer_support, ambiguity_handling=case.ambiguity_handling,
                action_count=len(actions), continuation_count=sum(bool(action.parent_path) for action in actions),
                terminal_frontier_state=manifest.frontier_state,
                provider_calls=sum(action.status != 'cached' for action in actions) + len(inspection['answers']),
                provider_input_tokens=None, provider_output_tokens=None,
                # The current V3 audit records per-exploration timing.  Answer
                # timing is intentionally reported as unavailable rather than
                # invented from wall clock timestamps.
                latency_seconds=sum(action.elapsed_seconds for action in actions),
            ))
        return DevelopmentLedgerReport(cohort=cohort, cases=rows, summary={
            'cases': len(rows),
            'mean_ground_truth_coverage': sum(row.ground_truth_coverage for row in rows) / len(rows),
            'exact_citation_valid_cases': sum(row.exact_citations_valid for row in rows),
            'supported_or_partial_cases': sum(row.answer_support in ('supported', 'partial') for row in rows),
            'forced_ambiguity_cases': sum(row.ambiguity_handling == 'forced' for row in rows),
            'provider_calls': sum(row.provider_calls for row in rows),
            'provider_input_tokens': None,
            'provider_output_tokens': None,
            'mean_latency_seconds': sum(row.latency_seconds or 0 for row in rows) / len(rows),
        })
