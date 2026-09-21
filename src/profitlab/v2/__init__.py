"""ProfitLab V2: source-guided discovery pipeline."""

from .contracts import STAGE_NAMES, StageSnapshot, V2Run
from .pipeline import V2PipelineService
from .storage import V2Repository

__all__ = ['STAGE_NAMES', 'StageSnapshot', 'V2PipelineService', 'V2Repository', 'V2Run']
