"""Bounded, deterministic source-shape reserve for a T39 routing experiment.

This is deliberately a layout/vocabulary signal, not a financial classifier. It
does not inspect replay expectations, XBRL, Company Facts, findings, or evaluation
data, and its matches still require detailed Jev chunk scoring before Findings can
receive a chunk.
"""
import re

from .canonical import CanonicalDocument
from .contracts import OutlineSection

PATTERN_VERSION = 'target-shaped-source-reserve-v1'
_TARGET_PATTERNS = {
    'annual_profit': re.compile(
        r'\b(?:net\s+(?:income|loss|earnings)|profit(?:s|\s+loss)?)\b', re.IGNORECASE),
    'diluted_eps': re.compile(
        r'\b(?:diluted\s+eps|(?:diluted\s+)?(?:earnings|income|loss)\s+'
        r'(?:per|/)\s+(?:common\s+)?share)\b', re.IGNORECASE),
    'diluted_shares': re.compile(
        r'\bweighted[-\s]+average(?:\s+(?:number\s+of|common|diluted))*\s+shares?\b', re.IGNORECASE),
}


def reserve_sections(document: CanonicalDocument, sections: list[OutlineSection], maximum: int) -> set[str]:
    """Return at most ``maximum`` source-order-stable target-shaped sections."""
    if maximum == 0:
        return set()
    candidates = []
    for section in sections:
        visible = document.slice(section.primary_range)
        targets = {target for target, pattern in _TARGET_PATTERNS.items() if pattern.search(visible)}
        if targets:
            candidates.append((section, targets))
    selected, covered = [], set()
    while candidates and len(selected) < maximum:
        section, targets = max(candidates, key=lambda item: (
            len(item[1] - covered), len(item[1]),
            -(item[0].primary_range.end_line - item[0].primary_range.start_line + 1),
            -item[0].primary_range.start_line, item[0].section_id))
        candidates.remove((section, targets))
        selected.append(section.section_id)
        covered.update(targets)
    return set(selected)
