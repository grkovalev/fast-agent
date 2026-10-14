"""Validated illustrative objects through prepared runtime builders, never live data."""
import hashlib
from datetime import date
from decimal import Decimal

from profitlab.providers.jev import NoulAnswer

from .canonical import CanonicalDocument, CanonicalLine
from .contracts import CanonicalDocumentRef, Finding, SourceRange, TextChunk
from .finding_concepts import FindingConcept
from .findings_builders import (
    build_assignment_request,
    build_context_request,
    build_conversion_messages,
    build_conversion_state,
    build_rank_state,
)
from .findings_contracts import (
    BundleScore,
    ConceptChunkCandidates,
    ConceptChunkReference,
    ConceptLineAssignment,
    ContextRole,
    ContextRoleAnswer,
    FindingContextLink,
    FindingConversionProposal,
    FindingEvidenceBundle,
    FindingLineCandidate,
    FindingPublicationProvenance,
    FindingsFilingMetadata,
    FindingsInputIdentity,
    FindingsPhase,
    FindingsRunSummary,
    FindingsStepResult,
    JudgmentProvenance,
    MetadataClaim,
    RankedFindingBundle,
    RequiredConditionAnswer,
    VisibleFindingLine,
    occurrence_id,
    visible_numeric_spans,
)
from .findings_policy import FindingsPolicy, RequiredCondition, SupportDecision


def safe_findings_examples(policy: FindingsPolicy | None = None) -> dict:
    """Actual validated contracts/builders, explicitly fictional and unregistered."""
    policy = policy or FindingsPolicy()
    digest = hashlib.sha256(b'illustrative canonical source; not a real filing').hexdigest()
    def source(number):
        return SourceRange(document_id='illustrative-document', source_hash=digest,
                           start_line=number, end_line=number)
    texts = ['Year ended December 31, 2025; USD in millions.',
             'Consolidated net income attributable to common shareholders.',
             'Net income | 1,200 | 1,100']
    document = CanonicalDocument(ref=CanonicalDocumentRef(document_id='illustrative-document',
        filing_id='illustrative-filing', source_hash=digest, line_count=3),
        lines=[CanonicalLine(line_number=i, text=text, element_type='table_row',
               html_anchor=f'line-{i}', dom_reference=f'/table/tr[{i}]')
               for i, text in enumerate(texts, 1)])
    chunk = TextChunk(chunk_id='illustrative-chunk', section_id='illustrative-section',
        core_range=source(3), context_ranges=[SourceRange(document_id='illustrative-document',
            source_hash=digest, start_line=1, end_line=2)], request_size_estimate=200)
    concept = FindingConcept.ANNUAL_PROFIT
    owner = ConceptChunkReference(chunk=chunk, concept_score=.9, reason='Selected upstream chunk; concept score above inclusion threshold.')
    candidate = FindingLineCandidate(candidate_id=occurrence_id(concept, source(3)),
        concept=concept, source_range=source(3), exact_text=texts[2], section_id=chunk.section_id,
        owners=[owner], owning_chunk_id=chunk.chunk_id, numeric_spans=visible_numeric_spans(texts[2]))
    filing = FindingsFilingMetadata(ticker='EXAMPLE', filing_id='illustrative-filing', report_date=date(2025,12,31))
    request = build_assignment_request(filing, candidate, 'illustrative-jev', policy)
    provenance = JudgmentProvenance(model='illustrative-jev', call_id='illustrative-call',
        question_id='source_support', question_version=policy.question_version,
        policy_hash=policy.identity(), request_hash=hashlib.sha256(request.model_dump_json().encode()).hexdigest())
    answer = NoulAnswer(type='noul', noul=.95)
    assignment = ConceptLineAssignment(candidate_id=candidate.candidate_id, concept=concept,
        source_range=source(3), answer=answer, decision=policy.source_decision(answer.noul),
        reason='Illustrative support; not provider output.', provenance=provenance)
    links=[]; context_requests=[]
    for number, supported_roles in ((1,{ContextRole.PERIOD,ContextRole.UNIT}), (2,{ContextRole.ENTITY})):
        context=VisibleFindingLine(source_range=source(number),exact_text=texts[number-1])
        context_requests.append(build_context_request(filing,candidate,context,
            context_section_id=chunk.section_id,allowed_pool=[chunk.core_range,*chunk.context_ranges],
            model='illustrative-jev',policy=policy))
        roles=[ContextRoleAnswer(role=role,answer=NoulAnswer(type='noul',noul=.95 if role in supported_roles else .1),
            decision=SupportDecision.SUPPORTED if role in supported_roles else SupportDecision.REJECTED,
            provenance=provenance.model_copy(update={'question_id':role.value})) for role in ContextRole]
        links.append(FindingContextLink(link_id=f'illustrative-context-{number}',source_candidate_id=candidate.candidate_id,
            concept=concept,source_range=source(3),context_range=source(number),section_id=chunk.section_id,
            owning_chunk_ids=[chunk.chunk_id],support=answer,provenance=provenance,roles=roles,
            decision='selected',reason='Illustrative context support.'))
    bundle=FindingEvidenceBundle(bundle_id='bundle-'+candidate.candidate_id.removeprefix('line-'),
        concept=concept,source=candidate,assignment=assignment,context_links=links,
        unresolved_roles=[ContextRole.QUALIFICATION])
    rank=RankedFindingBundle(bundle_id=bundle.bundle_id,concept=concept,
        score=BundleScore(score=3,probabilities={'0':0,'1':0,'2':0,'3':1},confidence=1,
            rubric_version=policy.rubric_version,provenance=provenance),
        required_conditions=[RequiredConditionAnswer(condition=x,answer=answer,decision=SupportDecision.SUPPORTED,
            provenance=provenance.model_copy(update={'question_id':x.value})) for x in RequiredCondition],
        eligibility='eligible',decision='selected',rank_within_concept=1,source_support=.95,
        upstream_concept_score=.9,source_range=source(3),reason='Illustrative eligible winner.')
    conversion=build_conversion_state(filing,[(bundle,rank)],document,policy)
    proposal=FindingConversionProposal(bundle_id=bundle.bundle_id,concept=concept,source_range=source(3),
        numeric_span=candidate.numeric_spans[0],exact_quote=texts[2],amount=Decimal(1200),
        period=MetadataClaim(value='2025',source_references=[source(1)]),
        unit=MetadataClaim(value='USD',source_references=[source(1)]),
        scale=MetadataClaim(value='millions',source_references=[source(1)]),
        attribution=MetadataClaim(value='common shareholders',source_references=[source(2)]),
        limitations=['Qualification/comparability context unresolved.'])
    finding=Finding(finding_id='illustrative-finding',exact_quote=texts[2],source_range=source(3),
        amount=proposal.amount,source_chunk_id=chunk.chunk_id,finding_type=concept.value,
        validation_state='validated',model='illustrative-llm')
    publication=FindingPublicationProvenance(finding=finding,concept=concept,bundle_id=bundle.bundle_id,
        numeric_span=candidate.numeric_spans[0],context_references=[source(1),source(2)],
        metadata_claims={k:getattr(proposal,k) for k in ('period','unit','scale','attribution')})
    steps=[FindingsStepResult(phase=phase,status='completed',availability='final',
                             input_hash=digest,policy_hash=policy.identity()) for phase in FindingsPhase]
    return {'kind':'validated illustration; no provider calls or active runtime registration',
        'contracts':{'candidate_map':ConceptChunkCandidates(concept=concept,relevance_threshold=.2,chunks=[owner]),
            'candidate':candidate,'assignment':assignment,'context_link':links[0],'bundle':bundle,'rank':rank,
            'proposal':proposal,'publication':publication,
            'identity':FindingsInputIdentity(canonical_source_hashes=[digest],exact_inputs_hash=digest,
                phase=FindingsPhase.ASSIGN,concept=concept,policy_hash=policy.identity(),
                question_version=policy.question_version,model_identity='illustrative-jev'),
            'summary':FindingsRunSummary(status='completed',sealed=True,policy_hash=policy.identity(),steps=steps,
                published_finding_ids=[finding.finding_id])},
        'assignment_request':request,'context_requests':context_requests,
        'rank_state':build_rank_state(filing,bundle,document,policy),'conversion_state':conversion,
        'conversion_messages':build_conversion_messages(conversion,policy),'policy':policy}
