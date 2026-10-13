"""Public, bounded inspection of the contracts used by the V2 pipeline."""

from pydantic import BaseModel

from .canonical import CanonicalDocument, CanonicalLine
from .chunk_scoring import EvidenceDescriptor
from .contracts import (
    CanonicalDocumentRef,
    FactComparison,
    FactPresentation,
    FactSourceMapping,
    Finding,
    OutlineContinuation,
    OutlineProposal,
    OutlineSection,
    ScoredItem,
    SourceRange,
    StructuredFact,
    TextChunk,
)
from .findings_service import FindingProposal
from .section_scoring import JevVisibleContext

STAGE_CONTRACTS: dict[str, tuple[type[BaseModel], ...]] = {
    'source': (CanonicalDocument, CanonicalDocumentRef, CanonicalLine, SourceRange),
    'outline': (CanonicalLine, OutlineProposal, OutlineContinuation, OutlineSection, SourceRange),
    'section_score': (OutlineSection, JevVisibleContext, ScoredItem),
    'chunk': (OutlineSection, TextChunk, SourceRange),
    'chunk_score': (TextChunk, EvidenceDescriptor, ScoredItem),
    'findings': (TextChunk, FindingProposal, Finding, SourceRange),
    'facts': (StructuredFact, FactPresentation, FactSourceMapping),
    'evaluate': (Finding, StructuredFact, FactComparison),
}


def contract_envelopes(stage: str, instances: dict[type[BaseModel], BaseModel] | None = None):
    """Expose only named domain contracts, never arbitrary settings or source payloads."""
    instances = instances or {}
    return [
        {
            'identity': model.__name__,
            'stage': stage,
            'kind': 'runtime schema',
            'schema': model.model_json_schema(mode='validation'),
            'input_references': [],
            'output_references': [],
            'provenance': f'{model.__module__}.{model.__qualname__}',
            'availability': 'persisted on this page' if model in instances else 'schema only',
            'instance_kind': 'persisted run data' if model in instances else 'unavailable',
            'instance': instances[model].model_dump(mode='json') if model in instances else None,
        }
        for model in STAGE_CONTRACTS[stage]
    ]
