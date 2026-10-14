"""Prepared source enumeration/storage with saved real SEC and JEV provenance."""
import copy
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from profitlab.v2.canonical import CanonicalDocument, canonicalize_html
from profitlab.v2.contracts import ScoredItem, TextChunk, V2Run
from profitlab.v2.finding_concepts import FindingConcept
from profitlab.v2.findings_batching import CompletedJevBatch
from profitlab.v2.findings_candidates import FindingsCandidatesResult, enumerate_candidates
from profitlab.v2.findings_contracts import (
    ConversionDiagnostic,
    FindingLineCandidate,
    FindingsInputIdentity,
    FindingsPhase,
    FindingsStepResult,
    visible_numeric_spans,
)
from profitlab.v2.findings_examples import safe_findings_examples
from profitlab.v2.findings_policy import FindingsPolicy
from profitlab.v2.findings_storage import ARTIFACTS
from profitlab.v2.storage import V2Repository

BASE = Path(__file__).parents[1] / 'fixtures' / 'benchmarks'


def saved_inputs():
    saved = json.loads(gzip.decompress((BASE/'t69/v2-6eca22455a84.json.gz').read_bytes()))
    document = CanonicalDocument.model_validate_json(saved['canonical_documents'][0]['canonical_json'])
    chunks = [TextChunk.model_validate_json(x['payload']) for x in saved['chunks']]
    scores = [ScoredItem.model_validate_json(x['payload']) for x in saved['scores']
              if x['score_kind'] == 'chunk_score']
    return document, chunks, scores


def create_repo(path):
    repo = V2Repository(path)
    repo.create_run(V2Run(run_id='test', ticker='AZZ', created_at=datetime.now(UTC),
                          updated_at=datetime.now(UTC)))
    return repo


def test_real_saved_enumeration_exact_source_caps_and_roundtrip():
    document, chunks, scores = saved_inputs()
    policy = FindingsPolicy()
    result = enumerate_candidates(document, chunks, scores, relevance_threshold=.2, policy=policy)
    assert result.lines and result.step.status == 'completed'
    assert FindingsCandidatesResult.model_validate_json(result.model_dump_json()) == result
    reversed_result = enumerate_candidates(document, list(reversed(chunks)), list(reversed(scores)),
                                          relevance_threshold=.2, policy=policy)
    # Record omissions in stable order as well as stable admitted candidate ownership.
    assert reversed_result.lines == result.lines
    assert reversed_result.step.input_hash == result.step.input_hash
    for line in result.lines:
        assert document.slice(line.source_range) == line.exact_text
        assert line.numeric_spans == visible_numeric_spans(line.exact_text)
        assert all(x.chunk.core_range.start_line <= line.source_range.start_line <=
                   x.chunk.core_range.end_line for x in line.owners)
    capped = enumerate_candidates(document, chunks, scores, relevance_threshold=.2,
                                  policy=FindingsPolicy(max_candidate_lines=2))
    assert len(capped.lines) == 2 and capped.step.status == 'partial'
    assert any(x.kind == 'count_limit' and x.coverage_cut for x in capped.step.omissions)
    empty = enumerate_candidates(document, chunks, [], relevance_threshold=.2, policy=policy)
    assert not empty.lines and empty.step.status == 'completed'
    assert empty.step.accounting.dispatched == 0


def test_inclusion_boundary_shared_owners_and_source_isolation():
    document, chunks, _ = saved_inputs()
    chunk = next(x for x in chunks if any(visible_numeric_spans(line.text)
        for line in document.lines[x.core_range.start_line-1:x.core_range.end_line]))
    duplicate = chunk.model_copy(update={'chunk_id': 'another-owner'})
    low = chunk.model_copy(update={'chunk_id': 'low'})
    def score(item, value, decision='selected'):
        return ScoredItem(item_id=item.chunk_id, target_scores={x.value: value for x in FindingConcept},
                          model='saved-control', call_id='controlled-inclusion',
                          policy_decision=decision, policy_reason='Threshold control')
    inputs = [chunk, duplicate, low]
    result = enumerate_candidates(document, inputs,
        [score(chunk,.2), score(duplicate,.9), score(low,.199)], relevance_threshold=.2,
        policy=FindingsPolicy())
    assert {x.concept for x in result.lines} == set(FindingConcept)
    for line in result.lines:
        assert line.owning_chunk_id == duplicate.chunk_id
        assert [x.chunk.chunk_id for x in line.owners] == [duplicate.chunk_id, chunk.chunk_id]
    assert all(any(x.item_id == 'low' and not x.coverage_cut for x in c.omissions)
               for c in result.concepts)
    wrong = chunk.model_copy(update={'core_range': chunk.core_range.model_copy(
        update={'source_hash': 'f'*64})})
    with pytest.raises(ValueError, match='does not belong'):
        enumerate_candidates(document, [wrong], [score(wrong,.9)], relevance_threshold=.2,
                             policy=FindingsPolicy())
    with pytest.raises(ValueError, match='unavailable chunk'):
        enumerate_candidates(document, [chunk], [score(duplicate,.9)], relevance_threshold=.2,
                             policy=FindingsPolicy())
    # An external HTML caption cannot be invented as a canonical candidate.
    assert all(document.lines[x.source_range.start_line-1].text == x.exact_text for x in result.lines)
    excluded = enumerate_candidates(document, [chunk], [score(chunk,.9,'uncertain')],
                                    relevance_threshold=.2, policy=FindingsPolicy())
    assert not excluded.lines


def test_numeric_offsets_signs_punctuation_and_repeated_values():
    text = '2025: (1,234.50), -12; −13; (+14); +15; 0; .25; -.5; 10%; 2.40, 2.40.'
    spans = visible_numeric_spans(text)
    assert [str(x.displayed_amount) for x in spans] == [
        '2025', '-1234.50', '-12', '-13', '-14', '15', '0', '0.25', '-0.5', '10', '2.40', '2.40']
    # A sentence-final period must not suppress a valid displayed number.
    # Controlled malformed grouping is never silently interpreted as a 1,23 amount.
    assert not any(x.raw_text == '1,23' for x in visible_numeric_spans('Bad 1,23'))
    assert all(text[x.start_character:x.end_character] == x.raw_text for x in spans)
    assert [str(x.displayed_amount) for x in visible_numeric_spans('( 1,200 ) | − 12 | (- 3.5)')] == [
        '-1200', '-12', '-3.5']


def test_fresh_schema_old_rejection_atomic_typed_artifacts_and_pagination(tmp_path):
    repo = create_repo(tmp_path)
    examples = safe_findings_examples()['contracts']
    values = [x for x in examples.values() if type(x) in ARTIFACTS]
    proposal = examples['proposal']
    values.extend([ConversionDiagnostic(bundle_id=proposal.bundle_id, proposal=proposal,
                                        state='accepted'),
                   ConversionDiagnostic(bundle_id='empty-bundle', state='empty')])
    assert {type(x) for x in values} == set(ARTIFACTS)
    for phase in FindingsPhase:
        artifacts = [x for x in values if ARTIFACTS[type(x)][1] == phase]
        step = FindingsStepResult(phase=phase, status='completed', availability='final',
                                 input_hash='a'*64, policy_hash=FindingsPolicy().identity())
        repo.complete_findings_step('test', step, artifacts)
        assert repo.findings_step('test', phase) == step
        for model in {type(x) for x in artifacts}:
            expected = [x for x in artifacts if type(x) == model]
            assert repo.findings_artifacts('test', model) == expected
            assert repo.findings_artifacts('test', model, page=2, per_page=1) == expected[1:2]
            assert repo.findings_artifacts('absent', model) == []
    previous = repo.findings_step('test', FindingsPhase.CANDIDATES)
    with pytest.raises(ValueError, match='different phase'):
        repo.complete_findings_step('test', previous, [examples['assignment']])
    assert repo.findings_step('test', FindingsPhase.CANDIDATES) == previous
    assert repo.findings_artifacts('test', FindingLineCandidate)
    with repo.connect() as db:
        db.execute('PRAGMA user_version=0')
    before = repo.db_path.read_bytes()
    with pytest.raises(ValueError, match='Unsupported existing V2 data'):
        V2Repository(tmp_path)
    assert repo.db_path.read_bytes() == before


def test_checkpoint_restart_reuse_identity_isolation_and_route_remapping(tmp_path):
    repo = create_repo(tmp_path)
    record = json.loads((BASE/'t70/live-mixed-azz.json').read_text())
    completed = CompletedJevBatch.model_validate(record['execution']['completed'][0])
    identity = FindingsInputIdentity(canonical_source_hashes=[
        saved_inputs()[0].ref.source_hash], exact_inputs_hash='a'*64,
        phase=FindingsPhase.RANK, policy_hash=FindingsPolicy().identity(),
        question_version='t70-probe', model_identity=completed.response.model)
    controlled = copy.deepcopy(completed.batch.request.model_dump(mode='json'))
    controlled['state']['items']['item_0']['document_id'] = 'old-local-document'
    completed = completed.model_copy(update={'batch': completed.batch.model_copy(update={
        'request': type(completed.batch.request).model_validate(controlled)})})
    repo.save_findings_checkpoint('test', identity, completed)
    repo = V2Repository(tmp_path)
    batch = completed.batch.model_copy(update={'routes': {
        key: ('current-run-occurrence', route[1]) for key, route in completed.batch.routes.items()}})
    for run_id in ('test', None):
        cached = repo.findings_checkpoint(identity, batch, run_id=run_id)
        assert cached.cached and cached.batch.routes == batch.routes
        assert cached.response == completed.response
    for changes in ({'policy_hash':'b'*64}, {'exact_inputs_hash':'b'*64},
                    {'canonical_source_hashes':['b'*64]}, {'question_version':'different'},
                    {'model_identity':'different'}, {'phase':FindingsPhase.ASSIGN}):
        assert repo.findings_checkpoint(identity.model_copy(update=changes), batch) is None
    assert repo.findings_checkpoint(identity, batch, run_id='another-run') is None
    changed = copy.deepcopy(batch.request.model_dump(mode='json'))
    changed['state']['extra_visible_line'] = 'Changed exact input'
    modified = batch.model_copy(update={'request': type(batch.request).model_validate(changed)})
    assert repo.findings_checkpoint(identity, modified) is None
    # Pure run-local source routing changes retain semantic request identity.
    state = copy.deepcopy(batch.request.model_dump(mode='json'))
    def remap(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('document_id','filing_id','section_id','chunk_id'):
                    value[key] = 'fresh-run-local-id'
                else:
                    remap(item)
        elif isinstance(value, list):
            for item in value:
                remap(item)
    remap(state)
    remapped = batch.model_copy(update={'request': type(batch.request).model_validate(state)})
    assert remapped.request != batch.request
    assert repo.findings_checkpoint(identity, remapped).batch.request == remapped.request
    assert repo.findings_checkpoints('test', identity) == [completed]
    assert repo.findings_checkpoints('test', identity, page=2, per_page=1) == []
    with pytest.raises(ValueError, match='actual model'):
        repo.save_findings_checkpoint('test', identity.model_copy(update={'model_identity':'wrong'}), completed)
    summary = safe_findings_examples()['contracts']['summary']
    repo.save_findings_run_result('test', summary)
    assert repo.findings_run_result('test') == summary


def test_external_visible_caption_absent_from_canonical_is_not_imported():
    # Saved Apple 2024 filing: external div/span caption is visible HTML, outside
    # canonical line types. Preserve this known limitation rather than adding IX facts.
    raw = gzip.decompress((BASE.parent / 't64/aapl-20240928.htm.gz').read_bytes())
    document, visible = canonicalize_html(raw, document_id='aapl', filing_id='aapl-filing')
    from lxml import html
    tree = html.fromstring(visible)
    captions = [x for x in tree.xpath('//div|//span')
                if 'In millions, except number of shares' in x.text_content() and
                len(x.text_content()) < 200]
    assert captions
    exact_caption = ' '.join(captions[0].text_content().split())
    assert all(exact_caption not in x.text for x in document.lines)
    result = enumerate_candidates(document, [], [], relevance_threshold=.2, policy=FindingsPolicy())
    assert not result.lines  # No HTML/structured-fact fallback or invented line range.
