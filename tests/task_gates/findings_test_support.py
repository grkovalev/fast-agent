from profitlab.v2.findings_contracts import FindingsPhase, FindingsRunSummary, FindingsStepResult
from profitlab.v2.findings_policy import FindingsPolicy


def seal_empty(repo, run_id):
    policy_hash = FindingsPolicy().identity()
    steps = [FindingsStepResult(phase=p, status='completed', availability='final',
        input_hash='0'*64, policy_hash=policy_hash) for p in FindingsPhase]
    repo.seal_findings(run_id, FindingsRunSummary(status='completed', sealed=True,
        policy_hash=policy_hash, steps=steps), [])
