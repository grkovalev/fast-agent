"""Shared financial vocabulary, independent of provider or stage services."""
from enum import StrEnum
from types import MappingProxyType


class FindingConcept(StrEnum):
    ANNUAL_PROFIT = 'annual_profit'
    DILUTED_EPS = 'diluted_eps'
    DILUTED_SHARES = 'diluted_shares'


CONCEPT_DEFINITIONS = MappingProxyType({
    FindingConcept.ANNUAL_PROFIT: 'Annual net income, profit, or loss attributable to shareholders.',
    FindingConcept.DILUTED_EPS: 'Annual diluted earnings or net income per common share.',
    FindingConcept.DILUTED_SHARES: 'Annual diluted weighted-average common shares outstanding.',
})
# Earnings change and comparability remain retrieval/context targets, never types.
CONCEPT_SCOPE = MappingProxyType({
    FindingConcept.ANNUAL_PROFIT: 'Reported consolidated shareholder profit/net income or loss, not a segment or adjusted measure.',
    FindingConcept.DILUTED_EPS: 'Reported diluted earnings per common share, not basic EPS or a segment/adjusted measure.',
    FindingConcept.DILUTED_SHARES: 'Reported diluted weighted-average common shares, not basic shares or period-end shares.',
})
