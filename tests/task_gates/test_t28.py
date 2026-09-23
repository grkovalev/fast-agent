"""T28 keeps exact Decimal evaluation separate from bounded scale-aware Jev verdicts."""
import asyncio
from datetime import date
from decimal import Decimal

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.contracts import Finding, SourceRange, StructuredFact
from profitlab.v2.evaluation_service import EvaluationService


def test_scale_aware_verdict_requires_visible_context_and_is_cached(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000, outline_window_lines=100,
                        section_score_batch_size=2, evaluation_scale_max_pairs=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='scale-t28')
    asyncio.run(pipeline.run('scale-t28', implement_source=True))
    document = pipeline.repo.canonical_document(
        'scale-t28', pipeline.repo.canonical_refs('scale-t28')[0].document_id)
    line = document.lines[0]
    source_range = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                               start_line=line.line_number, end_line=line.line_number,
                               start_character=0, end_character=1)
    finding = Finding(finding_id='finding-thousands', exact_quote='237,789', source_range=source_range,
                      amount=Decimal(237789), target='annual_profit', unit='USD', period='2025',
                      finding_type='annual_profit',
                      validation_state='validated')
    mismatch = Finding(finding_id='finding-mismatch', exact_quote='111', source_range=source_range,
                       amount=Decimal(111), target='diluted_eps', unit='USD/shares', period='2025',
                       finding_type='diluted_eps',
                       validation_state='validated')
    facts = [
        StructuredFact(fact_id='fact-thousands', concept='NetIncomeLoss', metric='net_income_consolidated',
                       value=Decimal(237789000), unit='USD', period_end=date(2025, 12, 31),
                       accession='x', form='10-K', filed_date=date(2026, 1, 1)),
        StructuredFact(fact_id='fact-mismatch', concept='EarningsPerShareDiluted', metric='eps_diluted',
                       value=Decimal(2), unit='USD/shares', period_end=date(2025, 12, 31),
                       accession='x', form='10-K', filed_date=date(2026, 1, 1)),
    ]
    pipeline.repo.save_findings('scale-t28', [finding, mismatch])
    pipeline.repo.save_structured_facts('scale-t28', facts)
    service = EvaluationService(settings, pipeline.repo)
    service._scale_context = lambda _run, item: {  # controlled retained visible context
        'declared_core_evidence_line': {'line_number': 1, 'text': item.exact_quote},
        'retained_context_lines': [{'line_number': 2,
                                    'text': 'Amounts in thousands' if item.finding_id == 'finding-thousands' else 'Amounts in dollars'}]}

    result = asyncio.run(service.compare_with_scale_verdicts('scale-t28', offline=True))
    states = {item.fact_id: item for item in result.comparisons}
    assert states['fact-thousands'].state == 'scale_aware_equivalent'
    assert states['fact-thousands'].deterministic_state == 'period_match_value_mismatch'
    assert states['fact-thousands'].jev_verdict is True
    assert states['fact-mismatch'].state == 'jev_rejected'
    assert states['fact-mismatch'].jev_verdict is False
    assert result.summary['exact_matches'] == 0
    actions = pipeline.repo.exploration_actions('scale-t28', 'evaluate')
    assert len(actions) == 2 and all('structured_fact' in item['request']['state'] for item in actions)

    cached = asyncio.run(service.compare_with_scale_verdicts('scale-t28', offline=True))
    assert cached.summary['evaluation_jev_calls'] == 0
    assert cached.summary['evaluation_jev_cached'] == 2


def test_same_value_unit_label_difference_is_a_judge_candidate_not_an_additional_duplicate(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='eps-label-t28')
    asyncio.run(pipeline.run('eps-label-t28', implement_source=True))
    document = pipeline.repo.canonical_document(
        'eps-label-t28', pipeline.repo.canonical_refs('eps-label-t28')[0].document_id)
    source_range = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                               start_line=1, end_line=1, start_character=0, end_character=1)
    finding = Finding(finding_id='wrong-retrieval-target', exact_quote='A visible source value $ 0.74',
                      source_range=source_range, amount=Decimal('0.74'), target='annual_profit',
                      finding_type='diluted_eps', period='2025', unit='per share',
                      validation_state='validated')
    fact = StructuredFact(fact_id='eps-fact', concept='EarningsPerShareDiluted', metric='eps_diluted',
                          value=Decimal('0.74'), unit='USD/shares', period_end=date(2025, 12, 31),
                          accession='x', form='10-K', filed_date=date(2026, 1, 1))
    pipeline.repo.save_findings('eps-label-t28', [finding])
    pipeline.repo.save_structured_facts('eps-label-t28', [fact])

    result = asyncio.run(EvaluationService(settings, pipeline.repo).compare_with_scale_verdicts(
        'eps-label-t28', offline=True))
    assert [(item.fact_id, item.state) for item in result.comparisons] == [('eps-fact', 'jev_rejected')]
    assert result.comparisons[0].deterministic_state == 'period_match_unit_mismatch'
    assert result.summary['additional_visible_numbers'] == 0
