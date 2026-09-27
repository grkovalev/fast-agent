"""Post-seal, deterministic scoring for frozen graph comparisons.

This module has no provider dependency.  In particular, reviewed coverage ranges
and V2 packet records are accepted only after an experiment is sealed and never
flow back into a graph or answer request.
"""
from collections import defaultdict

from .contracts import ArtifactRubric, RubricCohort, RubricReport


class PostSealRubricService:
    rubric_version = 'g6-post-seal-v1'

    @staticmethod
    def _contains(outer, inner):
        if outer.document_id != inner.document_id or outer.source_hash != inner.source_hash:
            return False
        if outer.start_line > inner.start_line or outer.end_line < inner.end_line:
            return False
        if inner.start_character is None:
            return outer.start_character is None
        if outer.start_character is None:
            return True
        return (outer.start_line == outer.end_line == inner.start_line == inner.end_line and
                outer.start_character <= inner.start_character and outer.end_character >= inner.end_character)

    @classmethod
    def score(cls, cohort: RubricCohort, repository) -> RubricReport:
        if not cohort.held_out:
            raise ValueError('G6 comparison cohorts must be explicitly held out.')
        if cohort.rubric_version != cls.rubric_version:
            raise ValueError('Unsupported post-seal rubric version.')
        rows = []
        for case in cohort.cases:
            inspection = repository.inspection(case.experiment_id)
            document, paths = inspection['document'], {item.path_id: item for item in inspection['paths']}
            if case.question != inspection['manifest'].question:
                raise ValueError(f'{case.case_id}: question does not match its sealed graph experiment.')
            for required in case.required_ranges:
                if required.document_id != document.ref.document_id or required.source_hash != document.ref.source_hash:
                    raise ValueError(f'{case.case_id}: reviewed range is not from the held-out canonical source.')
                document.slice(required)
            for artifact in case.artifacts:
                all_ranges = [*artifact.source_ranges, *artifact.citation_ranges]
                for source in all_ranges:
                    if source.document_id != document.ref.document_id or source.source_hash != document.ref.source_hash:
                        raise ValueError(f'{artifact.artifact_id}: source range is cross-document.')
                    document.slice(source)
                coverage = sum(any(cls._contains(source, required) for source in artifact.source_ranges)
                               for required in case.required_ranges) / len(case.required_ranges)
                citation_valid = bool(artifact.citation_ranges) and all(
                    any(cls._contains(source, citation) for source in artifact.source_ranges)
                    for citation in artifact.citation_ranges)
                if artifact.method == 'graph':
                    selected = [paths.get(path_id) for path_id in artifact.graph_path_ids]
                    path_valid = bool(selected) and all(selected) and all(
                        any(cls._contains(path_range, citation) for path in selected for path_range in path.source_ranges)
                        for citation in artifact.citation_ranges)
                    fidelity = 'valid' if path_valid else 'invalid'
                    citation_valid = citation_valid and path_valid
                else:
                    if artifact.graph_path_ids:
                        raise ValueError(f'{artifact.artifact_id}: non-graph artifact cannot cite graph paths.')
                    fidelity = 'not_applicable'
                rows.append(ArtifactRubric(case_id=case.case_id, artifact_id=artifact.artifact_id,
                    method=artifact.method, source_coverage=coverage, citation_valid=citation_valid,
                    path_fidelity=fidelity, answer_support=artifact.answer_support,
                    ambiguity_handling=artifact.ambiguity_handling, provider_calls=artifact.provider_calls,
                    provider_input_tokens=artifact.provider_input_tokens,
                    provider_output_tokens=artifact.provider_output_tokens,
                    latency_seconds=artifact.latency_seconds))
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.method].append(row)
        summary = {}
        for method, entries in grouped.items():
            summary[method] = {
                'artifacts': len(entries),
                'mean_source_coverage': sum(item.source_coverage for item in entries) / len(entries),
                'citation_valid_artifacts': sum(item.citation_valid for item in entries),
                'path_fidelity_valid_artifacts': sum(item.path_fidelity == 'valid' for item in entries),
                'supported_or_partial_artifacts': sum(item.answer_support in ('supported', 'partial') for item in entries),
                'forced_ambiguity_artifacts': sum(item.ambiguity_handling == 'forced' for item in entries),
                'provider_calls': sum(item.provider_calls for item in entries),
                'provider_input_tokens': sum(item.provider_input_tokens or 0 for item in entries),
                'provider_output_tokens': sum(item.provider_output_tokens or 0 for item in entries),
                'mean_latency_seconds': (sum(item.latency_seconds for item in entries if item.latency_seconds is not None) /
                                         sum(item.latency_seconds is not None for item in entries)
                                         if any(item.latency_seconds is not None for item in entries) else None),
            }
        return RubricReport(cohort=cohort, artifacts=rows, method_summary=summary)
