"""Bounded, persisted Findings step results for the reader UI."""


def bounded_result(data):
    remaining = 24000
    truncated = False

    def project(value):
        nonlocal remaining, truncated
        if remaining <= 0:
            truncated = True
            return '… preview limit reached'
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if remaining <= 0:
                    truncated = True
                    break
                remaining -= len(key)
                result[key] = project(item)
            return result
        if isinstance(value, list):
            truncated |= len(value) > 20
            result = []
            for item in value[:20]:
                if remaining <= 0:
                    truncated = True
                    break
                result.append(project(item))
            return result
        if isinstance(value, str):
            limit = min(2000, max(remaining, 0))
            remaining -= min(len(value), limit)
            if len(value) > limit:
                truncated = True
                return value[:limit] + '…'
        else:
            remaining -= len(str(value))
        return value

    preview = project(data)
    return {'data': preview, 'truncated': truncated}


def findings_phase_detail(repo, run_id, phase, page=1):
    from profitlab.v2.findings_contracts import FindingsPhase
    from profitlab.v2.findings_storage import ARTIFACTS
    step = repo.findings_step(run_id, phase)
    artifacts = {model.__name__: [x.model_dump(mode='json') for x in
                 repo.findings_artifacts(run_id, model, page=page, per_page=20)]
                 for model, (_, owner, _) in ARTIFACTS.items() if owner == phase}
    batches = repo.findings_saved_batches(run_id, phase, page=page) if phase.value in ('assign_lines', 'attach_context', 'rank_select', 'convert') else []
    data = {'checkpoints': [b.model_dump(mode='json') for b in batches], 'step': step.model_dump(mode='json') if step else None, 'artifacts': artifacts}
    if phase == FindingsPhase.SEAL:
        summary = repo.findings_run_result(run_id)
        data['summary'] = summary.model_dump(mode='json') if summary else None
    # Public source routes resolve exactly the stored canonical references.
    sources = {}
    def visit(value):
        if isinstance(value, dict):
            if ({'document_id', 'source_hash', 'start_line', 'end_line'} <= value.keys()
                    and isinstance(value['start_line'], int) and isinstance(value['document_id'], str)):
                key = (value['document_id'], value['start_line'], value['end_line'])
                sources[key] = {'label': f"Lines {key[1]}–{key[2]}",
                    'url': f"/v2/runs/{run_id}/source?document={key[0]}&page={(key[1]-1)//100+1}#line-{key[1]}"}
            else:
                for item in value.values():
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit({'artifacts': artifacts, 'checkpoints': data['checkpoints']})
    return data, list(sources.values())


def findings_step_results(repo, run_id, summary=None, finding_count=0):
    from profitlab.v2.findings_contracts import FindingsPhase
    results = {}
    for phase in FindingsPhase:
        data, sources = findings_phase_detail(repo, run_id, phase)
        available = data['step'] is not None
        results[phase.value] = {'available': available,
            'provenance': 'Saved typed phase result from this run.' if available else
                          'No saved result for this step. Pending or unavailable; no history is reconstructed.',
            'sources': sources[:20], **(bounded_result(data) if available else {})}
    return results
