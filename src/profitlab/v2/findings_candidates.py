"""Provider-free enumeration from selected persisted evidence only."""
import hashlib
import json

from pydantic import Field

from .canonical import CanonicalDocument
from .contracts import ScoredItem, SourceRange, TextChunk, V2Contract
from .finding_concepts import FindingConcept
from .findings_contracts import (
    ConceptChunkCandidates,
    ConceptChunkReference,
    FindingLineCandidate,
    FindingsPhase,
    FindingsStepResult,
    Omission,
    occurrence_id,
    visible_numeric_spans,
)
from .findings_policy import FindingsPolicy


class FindingsCandidatesResult(V2Contract):
    concepts: list[ConceptChunkCandidates] = Field(max_length=3)
    lines: list[FindingLineCandidate] = Field(max_length=10000)
    step: FindingsStepResult


def enumerate_candidates(document: CanonicalDocument, chunks: list[TextChunk],
                         scores: list[ScoredItem], *, relevance_threshold: float,
                         policy: FindingsPolicy) -> FindingsCandidatesResult:
    """No semantic number filtering; only core lines own source occurrences.

    A global cap is applied after deterministic concept/score/source ordering.
    Overlap context remains available upstream for T73, never source evidence here.
    """
    if not 0 <= relevance_threshold <= 1:
        raise ValueError('Invalid upstream uncertain relevance threshold')
    by_id = {x.chunk_id: x for x in chunks}
    if len(by_id) != len(chunks) or len({x.item_id for x in scores}) != len(scores):
        raise ValueError('Chunk and score IDs must be unique')
    for chunk in chunks:
        document.slice(chunk.core_range)
        for context in chunk.context_ranges:
            document.slice(context)
    if any(x.item_id not in by_id for x in scores):
        raise ValueError('Score references an unavailable chunk')
    concepts, lines, omissions = [], [], []
    for concept in FindingConcept:
        references, excluded = [], []
        for score in sorted(scores, key=lambda x: x.item_id):
            value = score.target_scores.get(concept.value)
            if score.policy_decision != 'selected' or value is None or value < relevance_threshold:
                excluded.append(Omission(item_id=score.item_id, kind='relevance', coverage_cut=False,
                    reason='Not retained upstream' if score.policy_decision != 'selected' else
                           'Concept score absent or below upstream uncertain relevance threshold'))
                continue
            references.append(ConceptChunkReference(chunk=by_id[score.item_id], concept_score=value,
                reason='Selected upstream and concept score meets uncertain relevance threshold'))
        references.sort(key=lambda x: (-x.concept_score, x.chunk.core_range.start_line, x.chunk.chunk_id))
        concepts.append(ConceptChunkCandidates(concept=concept, relevance_threshold=relevance_threshold,
                                               chunks=references, omissions=excluded))
        owners = {}
        for reference in references:
            core = reference.chunk.core_range
            for number in range(core.start_line, core.end_line + 1):
                owners.setdefault(number, []).append(reference)
        for number, eligible in owners.items():
            text = document.lines[number - 1].text
            spans = visible_numeric_spans(text)
            source = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                                 start_line=number, end_line=number)
            candidate_id = occurrence_id(concept, source)
            if not spans:
                omissions.append(Omission(item_id=candidate_id, kind='selection', coverage_cut=False,
                                          reason='No numeric span; remains available as context'))
                continue
            if len(lines) >= policy.max_candidate_lines:
                omissions.append(Omission(item_id=candidate_id, kind='count_limit', coverage_cut=True,
                                          reason='Global numeric source candidate limit'))
                continue
            lines.append(FindingLineCandidate(candidate_id=candidate_id, concept=concept,
                source_range=source, exact_text=text, section_id=eligible[0].chunk.section_id,
                owners=eligible, owning_chunk_id=eligible[0].chunk.chunk_id, numeric_spans=spans))
    inputs = {'source_hash': document.ref.source_hash, 'chunks': [x.model_dump(mode='json') for x in sorted(chunks, key=lambda x: x.chunk_id)],
              'scores': [x.model_dump(mode='json') for x in sorted(scores, key=lambda x: x.item_id)], 'threshold': relevance_threshold}
    step = FindingsStepResult(phase=FindingsPhase.CANDIDATES,
        status='partial' if any(x.coverage_cut for x in omissions) else 'completed', availability='final',
        input_hash=hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
        policy_hash=policy.identity(), output_ids=[x.candidate_id for x in lines], omissions=omissions,
        reason='Core-only numeric enumeration; no metric or fiscal-year inference')
    return FindingsCandidatesResult(concepts=concepts, lines=lines, step=step)
