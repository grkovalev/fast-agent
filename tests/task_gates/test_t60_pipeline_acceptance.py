"""Assembled pipeline inspection follows runtime contracts and request builders."""

from datetime import UTC, datetime
from typing import get_args

from fastapi.testclient import TestClient
from lxml import html
from pydantic import Field, create_model

from profitlab.settings import Settings
from profitlab.v2.chunk_scoring import ChunkScoringService
from profitlab.v2.contracts import FindingType, TextChunk, V2Run
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.inspection import STAGE_CONTRACTS
from profitlab.v2.outline_service import OutlineService
from profitlab.v2.section_scoring import TARGETS, SectionScoringService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_runtime_field_and_constraint_reach_selected_route(tmp_path, monkeypatch):
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='t60-contract', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    extended = create_model('ExtendedTextChunk',
                            audit_marker=(int | None, Field(default=None, ge=7)),
                            __base__=TextChunk)
    monkeypatch.setitem(STAGE_CONTRACTS, 'chunk', (*STAGE_CONTRACTS['chunk'], extended))

    with TestClient(create_app(Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None))) as client:
        page = client.get('/v2/runs/t60-contract/pipeline?stage=chunk')

    assert page.status_code == 200
    assert 'ExtendedTextChunk · runtime schema' in page.text
    assert '"audit_marker"' in page.text
    assert '"minimum": 7' in page.text
    assert 'Persisted instance unavailable on this page.' in page.text


def test_shared_prompt_questions_and_discovery_vocabulary(tmp_path, monkeypatch):
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='t60-builders', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    original = OutlineService._prompt_template()
    prompt_marker = 'T60 visible navigation instruction.'
    question_marker = 'T60 visible annual profit question?'
    monkeypatch.setattr(OutlineService, '_prompt_template',
                        staticmethod(lambda: original + '\n' + prompt_marker))
    monkeypatch.setitem(TARGETS, 'annual_profit', question_marker)

    def no_network(*args, **kwargs):
        raise AssertionError('Page inspection must not make provider or SEC requests')

    monkeypatch.setattr('httpx.AsyncClient.send', no_network)
    monkeypatch.setattr('httpx.Client.send', no_network)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/t60-builders/pipeline')
        selected = {stage: client.get(f'/v2/runs/t60-builders/pipeline?stage={stage}')
                    for stage in ('source', 'outline', 'section_score', 'chunk', 'chunk_score', 'findings')}

    assert page.status_code == 200
    assert prompt_marker in page.text
    assert question_marker in page.text
    assert 'illustrative request built with current configuration' in page.text

    # T65: bounded editorial copy stays aligned with the runtime target/type owners.
    document = html.fromstring(page.text)
    purpose, = document.xpath('//section[@aria-labelledby="discovery-purpose-title"]')
    assert purpose.xpath('.//@data-discovery-target') == list(TARGETS)
    assert purpose.xpath('.//@data-finding-type') == list(FindingsService.FINDING_TYPES)
    assert set(get_args(FindingType)) == {*FindingsService.FINDING_TYPES, 'unresolved'}
    text = purpose.text_content()
    assert 'Three numeric finding types, five retrieval targets' in text
    assert text.count('no dedicated published output type') == 2
    assert 'not year-end shares outstanding' in text
    assert 'unresolved type' in text
    assert 'not financial correctness or published evidence' in text
    assert 'does not compute EPS from profit and shares' in text
    assert 'What Findings delivers' in text
    assert 'current fiscal year' in text
    assert 'source-line link' in text
    assert 'not a saved run result' in text
    assert 'does not mean exactly three findings' in text
    assert 'an empty result' in text
    assert 'without separate narrative findings' in text
    assert 'Source validation does not establish financial correctness' in text
    assert len(text) < 3000
    assert not purpose.xpath('.//details | .//button | .//script | .//*[@hidden]')
    assert page.text.index('discovery-purpose-title') < page.text.index('pipeline-route-locator')
    for stage, response in selected.items():
        assert response.status_code == 200
        if stage == 'findings':
            for finding_type in FindingsService.FINDING_TYPES:
                assert finding_type in response.text
            assert 'unresolved' in response.text
    for service in (SectionScoringService, ChunkScoringService):
        assert service.inspection_view(settings)['score']['targets'] == list(TARGETS)
    assert 'not probabilities of financial correctness' in selected['section_score'].text
    assert 'No XBRL, Company Facts, or evaluation values are supplied' in selected['chunk_score'].text
    for target in TARGETS:
        assert target in page.text

    # T66: explanations are visible before station selection and agree with
    # selected-stage copy. Shared Evidence still describes complete chunk text.
    source, = document.xpath('//*[@data-source-card]')
    assert 'primary supported annual filing HTML (10-K)' in source.text_content()
    for kind in ('headings', 'paragraphs', 'list items', 'captions', 'table rows'):
        assert kind in source.text_content()
    assert 'retaining visible text inside Inline XBRL wrappers' in source.text_content()
    assert 'additional visible text outside those numbered lines' in source.text_content()
    outline, = document.xpath('//*[@data-outline-card]')
    example, = outline.xpath('.//*[@class="outline-navigation-example"]')
    assert 'Illustrative navigation example, not saved run data' in example.text_content()
    assert 'Financial performance → Earnings per share → lines 120–149' in example.text_content()
    assert not example.xpath('.//details | .//button | .//script | .//*[@hidden]')
    assert 'not an independently selected parent object' in example.text_content()
    assert 'Proposed end lines' in outline.text_content()
    assert 'each saved range' in outline.text_content().lower()
    sections, = document.xpath('//*[@data-sections-card]')
    assert 'One Jev scoring pass' in sections.text_content()
    assert 'First 600 characters · source line count · ticker and filing ID' in sections.text_content()
    assert 'does not contain full-section text' in sections.text_content()
    assert 'parent topics are not scored as a separate selection level' in sections.text_content()
    assert 'Only this set continues downstream' in sections.text_content()
    evidence, = document.xpath('//*[@data-evidence-card]')
    assert 'Jev reads full exact core plus preceding context' in evidence.text_content()
    assert 'First 600 characters' not in evidence.text_content()
    assert 'additional visible text outside those lines' in selected['source'].text
    assert 'not source text or independently selected parent objects' in selected['outline'].text
    assert 'first 600 characters of canonical section text' in selected['section_score'].text
    assert 'uncertain sections remain inspectable without continuing downstream' in selected['section_score'].text

    # T67: the initial route and selected stage agree, without requiring inspection.
    chunks, = document.xpath('//*[@data-chunks-card]')
    assert 'Only the core can supply a finding citation' in chunks.text_content()
    intro, = evidence.xpath('.//*[@id="evidence-composition-description"]')
    for phrase in ('same five targets', 'high score does not guarantee retention',
                   'do not validate fiscal periods', 'overlap suppression'):
        assert phrase in intro.text_content()
    assert not intro.xpath('.//details | .//button | .//script | .//*[@hidden]')
    for phrase in ('cannot supply a finding citation for this chunk',
                   'additional request-size limit', 'Uncertain', 'Skipped'):
        assert phrase in evidence.text_content()
    detail, = html.fromstring(selected['chunk_score'].text).xpath('//section[@class="stage-detail"]')
    assert 'not calibrated probabilities that a value exists' in detail.text_content()
    assert 'Only selected chunks enter Findings request assembly' in detail.text_content()
    assert 'Comparison uses exact Decimal equality' not in detail.text_content()
    assert 'same selected section' in selected['chunk'].text

    # T68: cardinality and publication guarantees are legible without inspection.
    findings, = document.xpath('//*[@data-findings-card]')
    illustration, = findings.xpath('.//*[@data-findings-cardinality]')
    assert 'Not saved run data' in illustration.text_content()
    assert not illustration.xpath('.//button | .//details | .//template | .//*[@hidden]')
    for phrase in ('including initially accepted ones', 'finite Decimal',
                   'Keep the first candidate', 'zero or multiple types',
                   'Per-request size overflow', 'Unresolved type alone does not reject'):
        assert phrase in findings.text_content()
    detail, = html.fromstring(selected['findings'].text).xpath('//section[@class="stage-detail"]')
    for phrase in ('zero or more candidates', 'Saved results by step',
                   'Initial and replacement candidates', 'not deterministic validation guarantees',
                   'provider and total-call-budget failure limits'):
        assert phrase in detail.text_content()
