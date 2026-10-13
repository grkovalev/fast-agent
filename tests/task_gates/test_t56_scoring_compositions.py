"""Scoring diagrams reflect service-owned targets, bounds, and outcomes."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.chunk_scoring import ChunkScoringService
from profitlab.v2.contracts import (
    CanonicalDocumentRef,
    OutlineSection,
    ScoredItem,
    SourceRange,
    TextChunk,
    V2Run,
)
from profitlab.v2.section_scoring import TARGETS, SectionScoringService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def _score(item_id, value):
    return ScoredItem(item_id=item_id, target_scores={'annual_profit': value},
                      model='illustrative', call_id='call',
                      policy_decision='skipped', policy_reason='pending')


def test_scoring_policies_preserve_three_distinct_decisions(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        section_score_max_selected=1, section_score_max_uncertain=1,
                        chunk_score_max_retained=1, chunk_score_max_uncertain=1)
    ref = CanonicalDocumentRef(document_id='doc', filing_id='filing',
                               source_hash='0' * 64, line_count=3)
    lines = [CanonicalLine(line_number=n, text=f'Visible {n}', element_type='paragraph',
                           html_anchor=f'line-{n}', dom_reference=f'/p[{n}]') for n in range(1, 4)]
    document = CanonicalDocument(ref=ref, lines=lines)
    ranges = [SourceRange(document_id='doc', source_hash=ref.source_hash,
                          start_line=n, end_line=n) for n in range(1, 4)]
    sections = [OutlineSection(section_id=f's{n}', generated_topic=f'Topic {n}',
                               primary_range=ranges[n - 1]) for n in range(1, 4)]
    chunks = [TextChunk(chunk_id=f'c{n}', section_id=f's{n}', core_range=ranges[n - 1],
                        request_size_estimate=3) for n in range(1, 4)]
    values = (.95, .60, .10)
    section_scores = SectionScoringService._policy(
        [_score(f's{n}', value) for n, value in enumerate(values, 1)], sections, settings)
    chunk_scores = ChunkScoringService(settings, None)._policy(
        [_score(f'c{n}', value) for n, value in enumerate(values, 1)], chunks, document)
    assert [item.policy_decision for item in section_scores] == ['selected', 'uncertain', 'skipped']
    assert [item.policy_decision for item in chunk_scores] == ['selected', 'uncertain', 'skipped']
    assert all(item.policy_reason for item in section_scores + chunk_scores)


def test_scoring_overview_shows_service_questions_and_separate_outcomes(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        section_score_keep_threshold=.81,
                        chunk_score_retained_text_char_budget=4321)
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='score-map', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    with TestClient(create_app(settings)) as client:
        response = client.get('/v2/runs/score-map/pipeline')
    assert response.status_code == 200
    html = response.text
    for stage in ('sections', 'evidence'):
        fragment = html.split(f'data-{stage}-card', 1)[1].split('</article>', 1)[0]
        assert fragment.count('class="scoring-outcome ') == 3
        assert 'Only this set continues downstream.' in fragment
        assert 'No downstream continuation.' in fragment
        assert 'Persisted decision accounting pending.' in fragment
        for target in TARGETS:
            assert target.replace('_', ' ') in fragment
    assert 'Keep ≥ 0.81' in html
    assert 'text ≤ 4321 characters' in html
    assert 'Generated topic <em>navigation label</em>' in html
    assert 'Exact visible heading <em>source text, when present</em>' in html
    assert 'Core lines + preceding context' in html
    assert 'data-sections-connector="score-select"' in html
    assert 'data-evidence-connector="score-retain"' in html
