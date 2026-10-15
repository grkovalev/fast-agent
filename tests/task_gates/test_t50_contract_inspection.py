from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from pydantic import Field, create_model

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.chunk_scoring import ChunkScoringService, EvidenceDescriptor
from profitlab.v2.contracts import (
    CanonicalDocumentRef,
    OutlineSection,
    ScoredItem,
    SourceRange,
    StructuredFact,
    TextChunk,
    V2Run,
)
from profitlab.v2.inspection import STAGE_CONTRACTS, contract_envelopes
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_runtime_schema_and_persisted_instances_keep_fields_and_decimal_precision():
    source_range = SourceRange(document_id='doc', source_hash='0' * 64,
                               start_line=5, end_line=9)
    chunk = TextChunk(chunk_id='chunk-1', section_id='section-1', core_range=source_range,
                      request_size_estimate=120, next_chunk_id='chunk-2')
    fact = StructuredFact(fact_id='fact-1', concept='NetIncomeLoss', metric='annual_profit',
                          value=Decimal('123456789.0000000001'), unit='USD',
                          period_end=date(2025, 12, 31), accession='filing-1',
                          form='10-K', filed_date=date(2026, 2, 1))
    chunk_entry = next(item for item in contract_envelopes('chunk', {TextChunk: chunk})
                       if item['identity'] == 'TextChunk')
    fact_entry = contract_envelopes('facts', {StructuredFact: fact})[0]
    assert {'previous_chunk_id', 'next_chunk_id'} <= chunk_entry['schema']['properties'].keys()
    assert chunk_entry['instance']['core_range']['start_line'] == 5
    assert chunk_entry['instance']['next_chunk_id'] == 'chunk-2'
    assert fact_entry['instance']['value'] == '123456789.0000000001'

    extended = create_model('ExtendedTextChunk', extra_note=(str | None, Field(default=None)),
                            __base__=TextChunk)
    original = STAGE_CONTRACTS['chunk']
    try:
        STAGE_CONTRACTS['chunk'] = (*original, extended)
        assert 'extra_note' in contract_envelopes('chunk')[-1]['schema']['properties']
    finally:
        STAGE_CONTRACTS['chunk'] = original


def test_selected_stage_renders_runtime_schema_without_loading_source(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, LLM_API_KEY='inspector-secret',
                        _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='contract-inspection', ticker='CNTR',
                          created_at=now, updated_at=now))
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/contract-inspection/pipeline?stage=chunk').text
    assert 'Runtime contracts' in page
    assert 'TextChunk · runtime schema' in page
    assert '"next_chunk_id"' in page
    assert 'Persisted instance unavailable on this page.' in page
    assert 'inspector-secret' not in page


def test_overview_uses_bounded_aggregates_instead_of_expanding_artifacts(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='bounded-inspection', ticker='BNDD',
                          created_at=now, updated_at=now))
    source_range = SourceRange(document_id='doc', source_hash='0' * 64,
                               start_line=5, end_line=9)
    repo.save_chunks('bounded-inspection', [TextChunk(
        chunk_id='chunk-1', section_id='section-1', core_range=source_range,
        request_size_estimate=120)])
    repo.save_scores('bounded-inspection', 'chunk_score', [ScoredItem(
        item_id='chunk-1', target_scores={'annual_profit': .9}, model='model', call_id='call',
        policy_decision='selected', policy_reason='high signal')])
    assert repo.inspection_totals('bounded-inspection')['chunks'] == {
        'count': 1, 'core_lines': 5, 'max_request_size': 120}
    assert [item.chunk_id for item in repo.chunks_for_ids(
        'bounded-inspection', ['chunk-1', 'missing'])] == ['chunk-1']

    def forbid_expansion(*_args, **_kwargs):
        raise AssertionError('overview expanded a persisted artifact')

    original_chunks = V2Repository.chunks

    def bounded_chunks(self, run_id, *, page=None, per_page=100):
        assert (page, per_page) == (1, 3)
        return original_chunks(self, run_id, page=page, per_page=per_page)

    monkeypatch.setattr(V2Repository, 'chunks', bounded_chunks)
    for method in ('scores', 'findings', 'company_fact_dataset', 'canonical_document'):
        monkeypatch.setattr(V2Repository, method, forbid_expansion)
    with TestClient(create_app(settings)) as client:
        response = client.get('/v2/runs/bounded-inspection/pipeline')
    assert response.status_code == 200
    assert 'Bounded persisted example from this run' in response.text
    assert 'Pipeline overview' in response.text


def test_evidence_descriptor_schema_is_used_by_runtime_builder(tmp_path):
    source_range = SourceRange(document_id='doc', source_hash='0' * 64,
                               start_line=2, end_line=2)
    document = CanonicalDocument(
        ref=CanonicalDocumentRef(document_id='doc', filing_id='filing',
                                 source_hash='0' * 64, line_count=2),
        lines=[CanonicalLine(line_number=1, text='Revenue increased.',
                             element_type='paragraph', html_anchor='line-1',
                             dom_reference='/html/body/p[1]'),
               CanonicalLine(line_number=2, text='Net income was $12.50.',
                             element_type='paragraph', html_anchor='line-2',
                             dom_reference='/html/body/p[2]')])
    chunk = TextChunk(chunk_id='chunk-1', section_id='section-1',
                      core_range=source_range, context_ranges=[source_range.model_copy(
                          update={'start_line': 1, 'end_line': 1})], request_size_estimate=50)
    section = OutlineSection(section_id='section-1', generated_topic='Revenue',
                             exact_source_title='Revenue', parent_topic_hint='Performance',
                             primary_range=source_range.model_copy(update={'start_line': 1}))
    service = ChunkScoringService(Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None), None)
    descriptor = service._descriptor(chunk, section, document,
                                     {'ticker': 'EXAMPLE', 'filing_id': 'filing'})
    assert EvidenceDescriptor.model_validate(descriptor).exact_chunk_text == 'Revenue increased.\nNet income was $12.50.'
    assert set(descriptor) == set(EvidenceDescriptor.model_fields)
    assert descriptor['visible_heading_path'] == ['Performance', 'Revenue']
    request = service._request([descriptor])
    assert len(request.questions) == 5
