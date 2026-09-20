"""Run-scoped report writing and mechanical citation validation."""
import asyncio
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from profitlab.analysis.calculations import CalculationService, display
from profitlab.analysis.reconciliation import ReconciliationService
from profitlab.contracts.reports import Report, ReportSentence
from profitlab.providers.llm import model_factory
from profitlab.providers.transport import TracedTransport
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder

VERSION = 'write-v1'
PROMPT = (Path(__file__).parents[1] / 'prompts' / 'write-v1.txt').read_text()
PLACEHOLDER = re.compile(r'\{\{(fact|calc):([A-Za-z0-9_-]+):([a-z_]+)\}\}')


@dataclass
class ReportInputs:
    repo: Repository
    run_id: str
    trace: TraceRecorder
    index: dict
    facts: dict
    calculations: dict
    groups: dict
    evidence: dict
    passages: list
    company_id: str
    limitations: list

    def read(self, kind, identifiers):
        if len(identifiers) > 8:
            raise ModelRetry('At most eight IDs per call.')
        owned = getattr(self, kind)
        result = []
        for identifier in identifiers:
            if identifier not in owned:
                result.append({'id': identifier, 'status': 'missing', 'reason': 'Unknown ID in this run snapshot'})
                continue
            value = owned[identifier]
            item = value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
            if len(json.dumps(item)) > 24000:
                result.append({'id': identifier, 'status': 'unsupported', 'reason': 'Evidence exceeds tool output limit; use saved source viewer.'})
            else:
                result.append({'id': identifier, 'status': 'available', 'value': item})
        return result

    def replacement(self, match, sentence):
        kind, identifier, field = match.groups()
        if kind == 'fact':
            if identifier not in self.facts or identifier not in sentence.fact_ids or field not in ('display', 'fiscal_year'):
                raise ValueError('Unknown, unselected or unreferenced fact placeholder')
            fact = self.facts[identifier]
            return str(fact.period.fiscal_year if field == 'fiscal_year' else fact.value)
        if identifier not in self.calculations or identifier not in sentence.calculation_ids:
            raise ValueError('Unknown or unreferenced calculation placeholder')
        calc = self.calculations[identifier]
        if field not in calc.results:
            raise ValueError('Unavailable calculation result')
        return display(calc.results[field]) + ('%' if 'percent' in field else '')

    def validate(self, report):
        if report.company_id != self.company_id or report.covered_years != self.index['years']:
            raise ValueError('Company or coverage mismatch')
        if set(report.table_fact_ids) != set(self.facts) or set(report.table_calculation_ids) != set(self.calculations):
            raise ValueError('Table must reference exactly the supplied selected facts and calculations')
        if report.summary != 'Earnings growth report':
            raise ValueError('Use the fixed summary label; put narrative in validated sentences')
        if report.limitations != self.limitations:
            raise ValueError('Preserve supplied limitations exactly')
        if not any(s.kind == 'coverage' and s.text == self.coverage_text() for s in report.sentences):
            raise ValueError('Include exact supplied coverage sentence')
        if len({s.sentence_id for s in report.sentences}) != len(report.sentences):
            raise ValueError('Duplicate sentence IDs')
        references = set()
        rendered = {}
        for s in report.sentences:
            if not set(s.fact_ids) <= self.facts.keys() or not set(s.calculation_ids) <= self.calculations.keys() or not set(s.evidence_ids) <= self.evidence.keys():
                raise ValueError('Fabricated or cross-run references')
            if s.kind == 'coverage' and s.text != self.coverage_text():
                raise ValueError('Coverage sentences must use application coverage text')
            if s.kind == 'limitation' and s.text not in self.limitations:
                raise ValueError('Limitation sentences must use supplied limitations')
            references.update(s.evidence_ids)
            for eid in s.evidence_ids:
                ref = self.evidence[eid]
                block = json.loads(self.repo.read(self.run_id, ref['block_id']))
                if any(segment not in block['text'] for segment in ref['exact_segments']):
                    raise ValueError('Stored evidence quote mismatch')
            if s.kind == 'management_explanation':
                if s.attribution != 'Management explanation' or not s.evidence_ids:
                    raise ValueError('Management explanations require attribution and source')
                quotes = [segment for eid in s.evidence_ids for segment in self.evidence[eid]['exact_segments']]
                if s.text not in quotes or not any(s.text == p['quote'] and p['attribution'].lower().startswith('management') and set(s.evidence_ids) <= set(p['evidence_ids']) for p in self.passages):
                    raise ValueError('Management quote mismatch')
                rendered[s.sentence_id] = s.text
                continue
            if s.kind == 'interpretation' and (s.attribution != 'Analyst interpretation' or not s.evidence_ids):
                raise ValueError('Interpretations require explicit label and evidence')
            if s.kind not in ('coverage', 'limitation') and not (s.fact_ids or s.calculation_ids or s.evidence_ids):
                raise ValueError('Unsupported narrative claim')
            clean = PLACEHOLDER.sub('', s.text)
            if s.kind != 'coverage' and (re.search(r'\d|%|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|twice|double|doubled|triple|tripled|half|halved)\b', clean, re.IGNORECASE)):
                raise ValueError(f'Sentence {s.sentence_id}: unsupported raw quantitative assertion (including fiscal years); use fact fiscal_year/display or actual calculation result-key placeholders. No literal RESULT_KEY.')
            rendered[s.sentence_id] = PLACEHOLDER.sub(lambda m, sentence=s: self.replacement(m, sentence), s.text)
            if '{{' in rendered[s.sentence_id] or '}}' in rendered[s.sentence_id]:
                raise ValueError('Unresolved placeholder')
        if set(report.source_index) != references:
            raise ValueError('Source index must match sentence citations')
        return rendered

    def coverage_text(self):
        return f"Available fiscal years: {', '.join(map(str, self.index['years']))}. Requested years: {self.repo.manifest(self.run_id).requested_years}. Missing/conflicting figures remain explicit in the annual table."

    def base_report(self):
        return Report(report_id='report-' + uuid4().hex, company_id=self.company_id,
            covered_years=self.index['years'], summary='Earnings growth report',
            sentences=[ReportSentence(sentence_id='coverage', text=self.coverage_text(), kind='coverage', attribution='Application coverage')],
            table_fact_ids=sorted(self.facts), table_calculation_ids=sorted(self.calculations),
            limitations=self.limitations, source_index=[], validation_status='pending')


def fixture_model(deps, *, fail=False):
    def respond(messages, info):
        with deps.trace.operation('writer.fixture', {'messages': json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
                'tools': [asdict(t) for t in info.function_tools], 'output_tools': [asdict(t) for t in info.output_tools]}, stage='write', actor='model', provider='fake-llm') as out:
            returns = [p for m in messages for p in m.parts if p.part_kind == 'tool-return']
            retries = [p for m in messages for p in m.parts if p.part_kind == 'retry-prompt']
            if not returns:
                part = ToolCallPart('get_evidence', {'evidence_ids': [p['evidence_ids'][0] for p in deps.passages[:1]]}, tool_call_id='writer-read')
            else:
                report = deps.base_report()
                sentences = list(report.sentences)
                calc = next((c for c in deps.calculations.values() if c.metric == 'eps_diluted' and 'yoy_percent' in c.results), None)
                if calc:
                    sentences.append(ReportSentence(sentence_id='eps-trend', text='Diluted EPS annual change: {{calc:' + calc.calculation_id + ':yoy_percent}}.', kind='comparison', calculation_ids=[calc.calculation_id], attribution='Deterministic comparison'))
                earnings = next((c for c in deps.calculations.values() if c.metric == 'net_income_common' and 'yoy_percent' in c.results), None)
                if earnings:
                    sentences.append(ReportSentence(sentence_id='earnings-trend', text='Common-share earnings annual change: {{calc:' + earnings.calculation_id + ':yoy_percent}}.', kind='comparison', calculation_ids=[earnings.calculation_id], attribution='Deterministic comparison'))
                latest_eps = max((f for f in deps.facts.values() if f.metric == 'eps_diluted'), key=lambda f: f.period.end, default=None)
                if latest_eps:
                    sentences.append(ReportSentence(sentence_id='eps-value', text='Latest annual diluted EPS: {{fact:' + latest_eps.candidate_id + ':display}}.', kind='comparison', fact_ids=[latest_eps.candidate_id], attribution='Reported annual figure'))
                for i, passage in enumerate(deps.passages[:2]):
                    sentences.append(ReportSentence(sentence_id=f'explanation-{i}', text=passage['quote'], kind='management_explanation', evidence_ids=passage['evidence_ids'], attribution='Management explanation'))
                if not retries or fail:
                    sentences.append(ReportSentence(sentence_id='invalid', text='Earnings increased 999%.', kind='comparison', attribution='Unsupported fixture assertion'))
                report = report.model_copy(update={'sentences': sentences, 'source_index': sorted({e for s in sentences for e in s.evidence_ids})})
                part = ToolCallPart(info.output_tools[0].name, report.model_dump(mode='json'), tool_call_id='writer-output')
            response = ModelResponse(parts=[part], model_name='fixture-writer-v1')
            out.update(response=json.loads(ModelMessagesTypeAdapter.dump_json([response])), synthetic=True)
            return response
    return FunctionModel(respond, model_name='fixture-writer-v1')


class ReportingService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.data_dir)

    def inputs(self, run_id):
        index, calcs, _, facts = CalculationService(self.settings).latest(run_id)
        if not index:
            raise ValueError('Calculate current selected facts before writing.')
        reconciliation, groups, _ = ReconciliationService(self.settings).latest(run_id)
        run = self.repo.manifest(run_id)
        evidence = {eid: json.loads(self.repo.read(run_id, eid)) for eid in
            {e for f in facts.values() for e in f.evidence_ids} | {e for p in reconciliation['passages'] for e in p['evidence_ids']}}
        limitations = ['Mechanical checks establish references and arithmetic, not the truth of causal interpretations.']
        from profitlab.providers.extraction import ExtractionService

        _, attempts = ExtractionService(self.settings).latest(run_id)
        if any(a.status in ('ambiguous', 'unsupported') for a in attempts):
            limitations.append('Upstream evidence processing is partial; unsupported contexts remain in candidate diagnostics.')
        if len(index['years']) < run.requested_years:
            limitations.append('Fewer fiscal years are available than requested.')
        if any(state['status'] != 'selected' for row in index['coverage'] for state in row['metrics'].values()):
            limitations.append('Some annual metrics are missing or conflicting; see coverage and competing candidates.')
        return ReportInputs(self.repo, run_id, TraceRecorder(self.repo, run_id, self.settings.redactor()), index, facts,
            {c.calculation_id: c for c in calcs}, {g.group_id: g for g in groups}, evidence,
            reconciliation['passages'], run.company.cik, limitations)

    def latest(self, run_id):
        indexes = [json.loads(self.repo.read(run_id, a['artifact_id'])) for a in self.repo.artifacts(run_id) if a['artifact_id'].startswith('write-index-')]
        if not indexes:
            return None, None, {}
        index = max(indexes, key=lambda x: x['created_at'])
        current, *_ = CalculationService(self.settings).latest(run_id)
        if not current or index['calculate_created_at'] != current['created_at']:
            return None, None, {}
        return index, Report.model_validate_json(self.repo.read(run_id, index['report_id'])), index['rendered']

    def progress(self, run_id):
        return asyncio.run(self.write(run_id))

    async def write(self, run_id, model=None):
        deps = self.inputs(run_id)
        prompt = (Path(__file__).parents[1] / 'prompts' / 'write-v1.txt').read_text()
        run = self.repo.manifest(run_id)
        if run.mode == 'replay':
            raise ValueError('Replay writing is read-only.')
        fake = run.mode == 'demo'
        provider = 'fake-llm' if fake else 'llm'
        conversation = 'conversation-' + uuid4().hex
        failure = None
        async with httpx.AsyncClient(transport=TracedTransport(deps.trace, self.settings, provider, stage='write'), timeout=self.settings.provider_timeout) as client:
            try:
                chosen = model or (fixture_model(deps) if fake else model_factory(self.settings, client))
                output_type = Report if fake or self.settings.llm_output_mode == 'tool' else NativeOutput(Report, strict=True)
                agent = Agent(chosen, deps_type=ReportInputs, output_type=output_type, instructions=prompt,
                    retries=self.settings.structured_output_repairs, model_settings={'timeout': self.settings.provider_timeout})

                def tool_read(ctx, kind, ids, name):
                    with deps.trace.operation(name, {'ids': ids}, actor='agent_tool', stage='write', provider=provider, call_id=ctx.tool_call_id) as out:
                        value = ctx.deps.read(kind, ids)
                        out['result'] = value
                        return value

                @agent.tool
                def get_evidence(ctx: RunContext[ReportInputs], evidence_ids: list[str]) -> list[dict]:
                    """Read exact saved source quotes by run-owned evidence ID; up to eight IDs."""
                    return tool_read(ctx, 'evidence', evidence_ids, 'get_evidence')

                @agent.tool
                def get_candidate_group(ctx: RunContext[ReportInputs], group_id: str) -> list[dict]:
                    """Inspect selection reasons and competing facts in this run."""
                    return tool_read(ctx, 'groups', [group_id], 'get_candidate_group')

                @agent.tool
                def get_calculation(ctx: RunContext[ReportInputs], calculation_id: str) -> list[dict]:
                    """Read deterministic arithmetic; do not calculate new values."""
                    return tool_read(ctx, 'calculations', [calculation_id], 'get_calculation')

                @agent.tool
                def get_coverage(ctx: RunContext[ReportInputs]) -> dict:
                    """Read available and missing annual metrics in this run."""
                    with deps.trace.operation('get_coverage', {}, actor='agent_tool', stage='write', provider=provider, call_id=ctx.tool_call_id) as out:
                        out['coverage'] = ctx.deps.index['coverage']
                        return out['coverage']

                @agent.output_validator
                def validate_output(ctx: RunContext[ReportInputs], report: Report) -> Report:
                    with deps.trace.operation('Validate report draft', report.model_dump(mode='json'), stage='validate') as out:
                        try:
                            ctx.deps.validate(report)
                        except ValueError as error:
                            raise ModelRetry(str(error)) from error
                        out['valid'] = True
                    return report.model_copy(update={'validation_status': 'valid', 'sentences': [s.model_copy(update={'validation_state': 'valid'}) for s in report.sentences]})

                payload = {'base_report': deps.base_report().model_dump(mode='json'),
                    'facts': [f.model_dump(mode='json') for f in deps.facts.values()],
                    'calculations': [c.model_dump(mode='json') for c in deps.calculations.values()],
                    'evidence_index': deps.passages, 'coverage': deps.index['coverage'], 'prompt_version': VERSION,
                    'instructions': prompt}
                seen = set()
                def snapshot(history):
                    messages = history.all_messages()
                    for i, m in enumerate(messages):
                        for j, p in enumerate(m.parts):
                            if p.part_kind == 'retry-prompt' and (i, j) not in seen:
                                seen.add((i, j))
                                deps.trace.emit(kind='structured_repair', span_id=conversation, stage='write', actor='model', provider=provider, summary='Writer validation feedback', result=json.loads(ModelMessagesTypeAdapter.dump_json([m])))
                    deps.trace.emit(kind='conversation', span_id=conversation, stage='write', actor='model', provider=provider, summary='Report writer conversation', result={'native_messages': json.loads(history.all_messages_json()), 'synthetic': fake, 'usage': asdict(history.usage), 'conversation_id': conversation})
                with deps.trace.operation('Report writer agent', payload, stage='write', actor='model', provider=provider) as out:
                    async with asyncio.timeout(self.settings.provider_total_timeout):
                        async with agent.iter(json.dumps(payload), deps=deps, usage_limits=UsageLimits(request_limit=self.settings.writer_max_requests, tool_calls_limit=self.settings.writer_max_tool_calls)) as history:
                            try:
                                async for _ in history:
                                    snapshot(history)
                                report = history.result.output
                                out['output'] = report.model_dump(mode='json')
                            finally:
                                snapshot(history)
            except Exception as error:  # noqa: BLE001 — persist honest data-only fallback
                failure = self.settings.redactor().text(type(error).__name__ + ': ' + str(error))
                report = deps.base_report().model_copy(update={'validation_status': 'partial'})
        rendered = deps.validate(report)
        self.repo.save_contract(run_id, report.report_id, report)
        now = datetime.now(UTC)
        index = {'created_at': now.isoformat(), 'calculate_created_at': deps.index['created_at'], 'report_id': report.report_id,
            'rendered': rendered, 'failure': failure, 'synthetic': fake, 'prompt_version': VERSION,
            'model_narrative': not bool(failure)}
        self.repo.put(run_id, 'write-index-' + uuid4().hex, json.dumps(index).encode())
        result = run.model_copy(update={'stage': 'write', 'updated_at': now, 'status': 'partial' if failure or run.status == 'partial' else 'completed',
            'versions': {**run.versions, 'writer': VERSION}, 'limitation': 'Data-only partial report: ' + failure if failure else 'Validated narrative; mechanical integrity does not establish causal truth.'})
        self.repo.save_contract(run_id, 'manifest-write-' + uuid4().hex, result)
        return result

    def verify(self, run_id):
        index, report, _ = self.latest(run_id)
        if not report:
            raise ValueError('No current report. Run write after calculate.')
        deps = self.inputs(run_id)
        rendered = deps.validate(report)
        if rendered != index['rendered']:
            raise ValueError('Persisted narrative differs from resolved placeholders')
        checks = {'created_at': datetime.now(UTC).isoformat(), 'report_id': report.report_id, 'mechanical_integrity': 'passed',
            'model_narrative': index['model_narrative'], 'validation_status': report.validation_status,
            'checks': ['run-owned references', 'selected table inputs', 'available calculation placeholders', 'source quote matches', 'coverage and limitations'],
            'rendered_matches': rendered == index['rendered'], 'scope': 'Reference integrity only; semantic truth and full end-to-end checks are not established.'}
        with deps.trace.operation('Mechanical report verification', {'report_id': report.report_id}, stage='validate') as out:
            out.update(checks)
        self.repo.put(run_id, 'checks-report-' + uuid4().hex, json.dumps(checks).encode())
        return checks
