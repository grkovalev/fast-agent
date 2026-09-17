"""Optional cross-check of supplied SEC Company Facts; never a value source."""
from decimal import Decimal

from pydantic import Field

from profitlab.contracts.base import Contract
from profitlab.contracts.facts import FactCandidate
from profitlab.documents.extraction import CONCEPTS


class CompanyFact(Contract):
    start: str | None = None
    end: str
    val: Decimal
    accn: str
    form: str
    fy: int | None = None
    fp: str | None = None
    filed: str | None = None
    frame: str | None = None


class ConceptFacts(Contract):
    label: str
    description: str
    units: dict[str, list[CompanyFact]] = Field(default_factory=dict)


def crosscheck(candidate: FactCandidate, payload: dict, accession: str):
    """Match exact concept/unit/interval/accession, disclosing duplicate provenance."""
    expected_unit = 'USD/shares' if candidate.unit == 'currency_per_share' else 'shares' if candidate.unit == 'shares' else 'USD'
    matching = []
    for concept, metric in CONCEPTS.items():
        if candidate.metric != metric:
            continue
        raw = payload.get('facts', {}).get('us-gaap', {}).get(concept.split(':')[1])
        if raw is None:
            continue
        parsed = ConceptFacts.model_validate(raw)
        for fact in parsed.units.get(expected_unit, []):
            if (fact.accn == accession and fact.form in ('10-K', '10-K/A') and
                fact.start == candidate.period.start.isoformat() and fact.end == candidate.period.end.isoformat()):
                matching.append(fact.val)
    return {'status': 'unavailable' if not matching else 'match' if all(v == candidate.value for v in matching) else 'conflict',
            'values': [str(v) for v in matching], 'cited_value': str(candidate.value),
            'note': 'Same filing data; not independent corroboration. Cited filing value remains unchanged.'}
