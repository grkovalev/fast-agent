"""T35 regression contracts from reviewed live SEC evaluation mismatches."""
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

from profitlab.v2.contracts import Finding, SourceRange, StructuredFact
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.v2.facts_service import CompanyFactsService

FIXTURES = Path(__file__).parents[1] / 'fixtures'
FILING = {'accession': '0001628280-26-019685', 'form': '10-K', 'report_date': '2025-12-31'}


def test_duplicate_company_fact_concepts_are_ordered_oracle_fallbacks():
    """TRC's NetIncomeLoss/ProfitLoss conflict must not make discovery ambiguous."""
    dataset = json.loads((FIXTURES / 't35_company_facts.json').read_text())

    facts, alternatives = CompanyFactsService.normalize(dataset, FILING)

    assert [(fact.metric, fact.concept, fact.value) for fact in facts] == [
        ('net_income_consolidated', 'us-gaap:NetIncomeLoss', Decimal(75000)),
    ]
    assert alternatives == {}

    fallback = deepcopy(dataset)
    del fallback['facts']['us-gaap']['NetIncomeLoss']
    facts, _ = CompanyFactsService.normalize(fallback, FILING)
    assert [(fact.concept, fact.value) for fact in facts] == [
        ('us-gaap:ProfitLoss', Decimal(71000)),
    ]


def test_scale_and_attribution_differences_remain_non_exact_without_visible_normalization():
    """DV's thousands/share labels cannot be silently promoted to exact equality."""
    finding = Finding(
        finding_id='finding-reviewed-scale', exact_quote='Diluted 166,683', amount=Decimal(166683),
        source_range=SourceRange(document_id='document-reviewed', source_hash='a' * 64,
                                 start_line=1, end_line=1),
        finding_type='diluted_shares', unit='thousands of shares', period='2025',
        attribution='DoubleVerify Holdings, Inc.', validation_state='validated')
    fact = StructuredFact(
        fact_id='fact-reviewed-scale', concept='us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',
        metric='weighted_average_shares_diluted', value=Decimal(166683000), unit='shares',
        period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
        accession='0001104659-26-020499', form='10-K', filed_date=date(2026, 2, 26))

    assert EvaluationService._unit_matches(finding, fact) is False
