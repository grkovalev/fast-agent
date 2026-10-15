"""Public station inspection from executed contracts and request builders."""
from .findings_contracts import FindingsPhase
from .findings_examples import safe_findings_examples
from .findings_policy import build_findings_policy

STATIONS = (
    ('candidates', 'Candidates', 'Reuse selected chunk scores per concept; enumerate numeric core lines without metric keyword filtering. Core lines own citations; dates, zeros and comparative columns remain candidates.'),
    ('assign_lines', 'Assign lines', 'JEV independently asks whether each line reports each concept. One source line may support several concepts. Keep supported, uncertain and rejected answers.'),
    ('attach_context', 'Attach context', 'JEV checks general support and period, unit/scale, entity and qualification roles together. Search only explicit candidate/retained-context ranges in the owning section; following lines may be in that pool. Missing roles remain unresolved.'),
    ('rank_select', 'Rank/select', 'JEV scores assembled bundles and checks requested year, annual duration, reported basis and concept scope. Known-negative conditions reject; uncertain conditions stay uncertain. Code selects eligible bundles only, ordered by rank, source support, upstream relevance and source order.'),
    ('convert', 'Convert', 'Only selected whole bundles cross into the LLM. Known concepts, exact source, numeric spans and selected context replace discovery. Zero, one or several proposals per bundle; no full outline, unselected chunks or post-conversion type calls.'),
    ('validate', 'Validate', 'Check selected bundle and fixed concept, exact source line and quote, visible span/offset/sign and finite Decimal. Metadata must reference supplied source/context; provenance does not prove financial interpretation. Preserve accepted findings; one bounded repair addresses invalid proposals, then returns to this gate. Deduplicate by concept, exact source span and amount.'),
    ('seal', 'Seal', 'Atomically publish validated findings with selected bundle/context provenance after all seven phases succeed. Empty sets are valid. Coverage cuts seal partial with omissions. Failure, deadline or cancellation never seals a subset; exact successful checkpoints can resume.'),
)


def findings_inspection(settings, summary=None, finding_count=0):
    policy = build_findings_policy(settings)
    examples = safe_findings_examples(policy)
    contracts = examples['contracts']
    keys = {
        'candidates': ('candidate_map', 'candidate'), 'assign_lines': ('assignment',),
        'attach_context': ('context_pool', 'context_link', 'bundle'), 'rank_select': ('rank', 'conversion_pack'),
        'convert': ('proposal', 'conversion_result'), 'validate': ('publication',), 'seal': ('summary',),
    }
    requests = {'assign_lines': examples['assignment_request'],
                'attach_context': examples['context_requests'][0],
                'rank_select': examples['rank_request'], 'convert': examples['conversion_request']}
    preview = ({k: summary[k] for k in ('status', 'sealed', 'rejection_count', 'limitation',
                'provider_requests', 'cached_batches', 'phases', 'accounting_scope') if k in summary} if summary else None)
    result = {'published': finding_count, 'summary': preview,
              'policy': policy.model_dump(mode='json'), 'stations': STATIONS}
    for phase, title, description in STATIONS:
        models = [contracts[k] for k in keys[phase]]
        result[phase] = {
            'accepts': 'Visible canonical source and typed prior-phase results; no Company Facts, evaluation or raw HTML semantics.',
            'does': description,
            'outputs': [type(x).__name__ for x in models],
            'contracts': [{'identity': type(x).__name__, 'schema': type(x).model_json_schema(),
                           'illustration': x.model_dump(mode='json')} for x in models],
            'policy': policy.model_dump(mode='json'),
            'provenance': 'Validated illustration/current configuration; separate from saved run results.',
        }
        if phase in requests:
            request = requests[phase].model_dump(mode='json')
            # Example model is explicitly illustrative; actual model identity is in saved checkpoints.
            result[phase]['request'] = {'kind': 'validated illustrative runtime request',
                'configured_model': settings.llm_model if phase == 'convert' else settings.typesafe_model,
                'example': request}
    assert {x.value for x in FindingsPhase} == set(keys)
    return result
