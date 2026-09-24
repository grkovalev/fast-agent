"""ProfitLab V2: source-guided discovery pipeline."""

from .batch import SequentialReportBatchService
from .canonical import CanonicalDocument, CanonicalLine, canonicalize_html
from .contracts import STAGE_NAMES, StageSnapshot, V2Run
from .pipeline import V2PipelineService
from .storage import V2Repository

__all__ = [
    'STAGE_NAMES',
    'CanonicalDocument',
    'CanonicalLine',
    'SequentialReportBatchService',
    'StageSnapshot',
    'V2PipelineService',
    'V2Repository',
    'V2Run',
    'canonicalize_html',
]
