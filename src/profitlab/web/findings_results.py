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


def findings_step_results(repo, run_id, summary, finding_count):
    actions = {item['action_id']: item
               for item in repo.exploration_actions(run_id, 'findings')}
    results = {}
    for step in ('assemble', 'propose', 'validate', 'classify', 'publish'):
        action = actions.get(f'findings-step-{step}')
        data = action.get('result') if action else None
        provenance = 'Saved at this step in this run.'
        if data is None and step == 'assemble' and 'findings-request' in actions:
            data = {'request': actions['findings-request']['request']}
            provenance = 'Saved request from this run’s extraction diagnostic.'
        if data is None and step in ('classify', 'publish') and summary is not None:
            data = {'findings': [item.model_dump(mode='json') for item in
                                 repo.findings(run_id, page=1, per_page=20)],
                    'count': finding_count}
            provenance = ('Saved final findings; intermediate classification output was not recorded.'
                          if step == 'classify' else 'Saved sealed findings from this run.')
        if data is None:
            results[step] = {'available': False,
                             'provenance': 'No saved result for this step. It may not have run, '
                                           'or this run predates step result recording.'}
        else:
            results[step] = {'available': True, 'provenance': provenance,
                             **bounded_result(data)}
            if step in ('classify', 'publish') and finding_count > 20:
                results[step]['truncated'] = True
    return results
