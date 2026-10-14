"""T69: source-owned contracts and safe prepared builders, with saved real inputs."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument
from profitlab.v2.contracts import SourceRange, TextChunk
from profitlab.v2.finding_concepts import FindingConcept
from profitlab.v2.findings_builders import (
    build_assignment_request,
    build_context_request,
    build_conversion_state,
    guard_findings_payload,
)
from profitlab.v2.findings_contracts import (
    AssignmentState,
    ConceptChunkReference,
    FindingConversionProposal,
    FindingLineCandidate,
    FindingsFilingMetadata,
    FindingsRunSummary,
    FindingsStepResult,
    PhaseAccounting,
    RankedFindingBundle,
    VisibleFindingLine,
    occurrence_id,
    visible_numeric_spans,
)
from profitlab.v2.findings_examples import safe_findings_examples
from profitlab.v2.findings_policy import (
    FindingsPolicy,
    JevPhaseBudget,
    SupportDecision,
    build_findings_policy,
)

BASELINE = Path(__file__).parents[1] / 'fixtures' / 'benchmarks' / 't69'


def test_validated_safe_examples_roundtrip_and_public_schemas():
    examples = safe_findings_examples()
    for value in examples['contracts'].values():
        assert type(value).model_validate_json(value.model_dump_json()) == value
        assert type(value).model_json_schema()['properties']
    for key in ('assignment_request', 'rank_state', 'conversion_state', 'policy'):
        value = examples[key]
        assert type(value).model_validate_json(value.model_dump_json()) == value
        guard_findings_payload(value.model_dump(mode='json'))
    assert len(examples['context_requests'][0].questions) == 5
    assert 'concept_definition' in examples['assignment_request'].questions['source_support'].instructions
    serialized = json.dumps(examples['conversion_state'].model_dump(mode='json'))
    assert 'owners' not in serialized and 'outline' not in serialized
    assert 'selected_bundles' in examples['conversion_messages'][0]['content']
    # Examples are prepared only; active inspectors retain the old executed contracts.
    from profitlab.v2.inspection import STAGE_CONTRACTS
    assert FindingLineCandidate not in STAGE_CONTRACTS['findings']


def test_contract_invariants_identity_eligibility_and_sealing():
    examples = safe_findings_examples()['contracts']
    candidate = examples['candidate']
    assignment = examples['assignment']
    rank = examples['rank']
    proposal = examples['proposal']
    summary = examples['summary']
    def invalid(model, value, **changes):
        with pytest.raises(ValidationError):
            model.model_validate({**value.model_dump(), **changes})
    invalid(FindingLineCandidate, candidate, owning_chunk_id='unowned')
    invalid(FindingLineCandidate, candidate, exact_text='wrong line text')
    invalid(FindingLineCandidate, candidate, concept=FindingConcept.DILUTED_EPS)
    invalid(FindingConversionProposal, proposal, amount=proposal.amount * 1000000)
    invalid(FindingConversionProposal, proposal, amount='NaN')
    invalid(RankedFindingBundle, rank, eligibility='ineligible')
    required = [x.model_dump() for x in rank.required_conditions]
    required[0]['decision'] = SupportDecision.REJECTED
    invalid(RankedFindingBundle, rank, required_conditions=required)
    invalid(FindingsRunSummary, summary, status='failed')
    invalid(FindingsRunSummary, summary, steps=[])
    invalid(FindingsRunSummary, summary, sealed=False)
    invalid(FindingsRunSummary, summary, steps=[summary.steps[0]] * 7)
    invalid(FindingsStepResult, summary.steps[0], omissions=[{
        'item_id': 'cut', 'reason': 'Count cap', 'coverage_cut': True, 'kind': 'count_limit'}])
    with pytest.raises(ValidationError):
        PhaseAccounting(planned=1, dispatched=0, completed=1)
    with pytest.raises(ValidationError):
        PhaseAccounting(planned=1, dispatched=1, cached=1)
    changed = candidate.source_range.model_copy(update={'document_id':'another-run-document'})
    assert occurrence_id(candidate.concept, changed) == candidate.candidate_id
    changed = changed.model_copy(update={'start_line':4,'end_line':4})
    assert occurrence_id(candidate.concept, changed) != candidate.candidate_id
    with pytest.raises(ValidationError):
        AssignmentState(filing=safe_findings_examples()['assignment_request'].state['filing'],
            candidate_id=assignment.candidate_id, concept=FindingConcept.DILUTED_EPS,
            candidate=VisibleFindingLine(source_range=candidate.source_range,exact_text=candidate.exact_text),
            concept_definition='Diluted EPS')


def test_numeric_spans_are_exact_displayed_values_not_metric_or_year_selection():
    text = '2025 | (1,234.50) | -12 | −13 | 0 | 2.40 | 10% | (-14) | (−15) | 2.40'
    spans = visible_numeric_spans(text)
    assert [str(x.displayed_amount) for x in spans] == [
        '2025','-1234.50','-12','-13','0','2.40','10','-14','-15','2.40']
    assert all(text[x.start_character:x.end_character] == x.raw_text for x in spans)
    assert spans[-1].start_character != spans[5].start_character
    assert visible_numeric_spans('No numeric content') == []


def test_policy_boundaries_settings_and_request_isolation(monkeypatch):
    policy = FindingsPolicy()
    assert policy.source_decision(.65) == SupportDecision.SUPPORTED
    assert policy.source_decision(.20) == SupportDecision.UNCERTAIN
    assert policy.source_decision(.199) == SupportDecision.REJECTED
    assert policy.required_decision(.65) == SupportDecision.SUPPORTED
    assert len(policy.required_conditions(FindingConcept.DILUTED_EPS)) == 4
    for changes in ({'source_uncertain_threshold': .65}, {'required_uncertain_threshold': .7},
                    {'max_context_candidates_per_bundle': 5}):
        with pytest.raises(ValidationError):
            FindingsPolicy(**changes)
    budget = JevPhaseBudget(serialized_characters=1000,estimated_input_tokens=1000,token_margin=10)
    assert budget.admits('x'*1000,64)
    assert not budget.admits('x'*1001,64)
    assert not budget.admits('x',65)
    assert not budget.admits('x',0)
    assert not JevPhaseBudget(estimated_input_tokens=600,token_margin=512).admits('x'*1000,1)
    monkeypatch.setenv('FINDINGS_POLICY',json.dumps({'max_jev_requests':3}))
    configured = build_findings_policy(Settings(_env_file=None))
    assert configured.max_jev_requests == 3 and configured.identity() != policy.identity()
    assert 'api_key' not in configured.model_dump_json()
    for bad in ({'company_facts':[]}, {'nested':{'evaluation_value':10}},
                {'text':'us-gaap:NetIncomeLoss'}, {'text':'contextRef=hidden'}):
        with pytest.raises(ValueError):
            guard_findings_payload(bad)
    with pytest.raises(ValidationError):
        FindingsFilingMetadata(ticker='EXAMPLE',filing_id='example',report_date='2025-12-31',expected_value=10)


def test_saved_real_baseline_to_safe_assignment_and_context():
    manifest=json.loads((BASELINE/'manifest.json').read_text())
    assert len(manifest['runs']) == 3 and not manifest['reset_performed']
    for entry in manifest['runs']:
        packed=(BASELINE/entry['artifact']).read_bytes()
        assert hashlib.sha256(packed).hexdigest() == entry['sha256']
        raw=gzip.decompress(packed)
        assert hashlib.sha256(raw).hexdigest() == entry['uncompressed_sha256']
        assert len(packed) <= manifest['bounds']['compressed_bytes_per_run']
        saved=json.loads(raw)
        document=CanonicalDocument.model_validate_json(saved['canonical_documents'][0]['canonical_json'])
        finding=json.loads(saved['findings'][0]['payload'])
        chunk=next(TextChunk.model_validate_json(x['payload']) for x in saved['chunks']
                   if x['chunk_id'] == finding['source_chunk_id'])
        number=finding['source_range']['start_line']
        source=SourceRange(document_id=document.ref.document_id,source_hash=document.ref.source_hash,
                           start_line=number,end_line=number)
        score=next(json.loads(x['payload']) for x in saved['scores']
                   if x['score_kind']=='chunk_score' and x['item_id']==chunk.chunk_id)
        text=document.slice(source)
        concept=FindingConcept.ANNUAL_PROFIT
        candidate=FindingLineCandidate(candidate_id=occurrence_id(concept,source),concept=concept,
            source_range=source,exact_text=text,section_id=chunk.section_id,
            owners=[ConceptChunkReference(chunk=chunk,concept_score=score['target_scores'][concept.value],
                                           reason='Saved upstream selected score')],
            owning_chunk_id=chunk.chunk_id,numeric_spans=visible_numeric_spans(text))
        filing=json.loads(saved['filings'][0]['payload'])
        metadata=FindingsFilingMetadata(ticker=entry['ticker'],filing_id=document.ref.filing_id,
                                       report_date=filing['report_date'])
        policy=FindingsPolicy()
        request=build_assignment_request(metadata,candidate,'jev-1.13.0',policy)
        assert request.state['candidate']['exact_text'] == text
        # Shared occurrence may independently belong to EPS, without exclusive choice.
        eps=candidate.model_copy(update={'concept':FindingConcept.DILUTED_EPS,
                                        'candidate_id':occurrence_id(FindingConcept.DILUTED_EPS,source)})
        eps=FindingLineCandidate.model_validate(eps.model_dump())
        eps_request=build_assignment_request(metadata,eps,'jev-1.13.0',policy)
        assert eps_request.state['candidate'] == request.state['candidate']
        assert eps_request.state['concept'] != request.state['concept']
        context=VisibleFindingLine(source_range=source,exact_text=text)
        build_context_request(metadata,candidate,context,context_section_id=chunk.section_id,
            allowed_pool=[chunk.core_range,*chunk.context_ranges],model='jev-1.13.0',policy=policy)
        with pytest.raises(ValueError,match='allowed canonical pool'):
            build_context_request(metadata,candidate,context,context_section_id='other-section',
                allowed_pool=[chunk.core_range],model='jev-1.13.0',policy=policy)
        with pytest.raises(ValueError,match='Whole request'):
            build_assignment_request(metadata,candidate,'jev-1.13.0',
                FindingsPolicy(assign_budget=JevPhaseBudget(serialized_characters=1000)))
        examples=safe_findings_examples()
        with pytest.raises(ValueError,match='selected matching eligible'):
            loser=examples['contracts']['rank'].model_copy(update={'decision':'losing'})
            build_conversion_state(metadata,[(examples['contracts']['bundle'],loser)],document,policy)
    live = manifest['live_baseline']
    packed = (BASELINE/live['artifact']).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == live['sha256']
    assert hashlib.sha256(gzip.decompress(packed)).hexdigest() == live['uncompressed_sha256']
    assert json.loads(gzip.decompress(packed))['status'] == 'completed'
