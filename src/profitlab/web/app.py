"""The bounded reader UI for fresh V2 runs."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from profitlab.sec.ticker_picker import RandomEligibleTickerPicker
from profitlab.settings import Settings
from profitlab.v2 import STAGE_NAMES, SequentialReportBatchService, V2PipelineService
from profitlab.v2.benchmark import RetrievalBenchmarkService, load_dataset
from profitlab.v2.evaluation_service import cross_run_scorecard
from profitlab.v2.source_replay import SourceReplayService
from profitlab.v3.repository import V3Repository

WEB_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, ticker_picker_factory=None,
               benchmark_dataset=None) -> FastAPI:
    settings = settings or Settings()
    pipeline, tasks, batch_tasks = V2PipelineService(settings), {}, {}
    graph_repo = V3Repository(settings.data_dir)

    def new_picker():
        return (ticker_picker_factory(pipeline.repo) if ticker_picker_factory
                else RandomEligibleTickerPicker(settings, pipeline.repo))

    batch_service = SequentialReportBatchService(settings, pipeline, new_picker)

    def start(run_id):
        if (task := tasks.get(run_id)) and not task.done():
            raise ValueError('V2 run is already active.')

        async def guarded_run():
            try:
                return await pipeline.run(run_id, delay=.05, implement_source=True)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # A provider/parser/storage exception must not leave a run looking active.
                # The pipeline already persists expected domain failures; this is the
                # last-resort boundary for failures outside those narrower handlers.
                message = settings.redactor().text(str(error)) or error.__class__.__name__
                logger.exception('V2 worker failed for run %s', run_id)
                try:
                    stage = pipeline.repo.stage(run_id, pipeline.repo.get_run(run_id).selected_stage)
                    if stage and stage.status == 'running':
                        failed = stage.model_copy(update={
                            'status': 'failed',
                            'finished_at': datetime.now(UTC),
                            'summary': 'V2 worker failed unexpectedly.',
                            'error': message,
                        })
                        pipeline.repo.update_stage(failed, event_kind='stage_finished',
                                                   event_summary=failed.summary)
                    pipeline.repo.update_run(run_id, status='failed',
                                             summary='V2 worker failed unexpectedly.',
                                             kind='run_finished')
                except Exception:
                    logger.exception('Could not persist V2 worker failure for run %s', run_id)
                return None

        task = asyncio.create_task(guarded_run())
        tasks[run_id] = task

    def start_batch(batch_id):
        if (task := batch_tasks.get(batch_id)) and not task.done():
            raise ValueError('Batch is already active.')

        async def guarded_batch():
            try:
                await batch_service.run(batch_id)
            except Exception as error:
                logger.exception('Batch worker failed for %s', batch_id)
                batch_service.repo.update_report_batch(
                    batch_id, status='completed', summary=settings.redactor().text(str(error)))

        batch_tasks[batch_id] = asyncio.create_task(guarded_batch())

    @asynccontextmanager
    async def lifespan(_app):
        pipeline.recover()
        for batch in pipeline.repo.report_batches():
            if batch.status in {'queued', 'running', 'cancelling'}:
                pipeline.repo.update_report_batch(batch.batch_id, status='queued',
                                                  cancellation_requested=False,
                                                  summary='Recovered after restart; continuing remaining reports.')
                start_batch(batch.batch_id)
        yield
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        for task in batch_tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*batch_tasks.values(), return_exceptions=True)

    app = FastAPI(title='ProfitLab', lifespan=lifespan)
    templates = Jinja2Templates(directory=WEB_DIR / 'templates')
    app.mount('/static', StaticFiles(directory=WEB_DIR / 'static'), name='static')

    @app.middleware('http')
    async def disable_browser_cache(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    def home_context(**extra):
        return {'v2_runs': pipeline.repo.recent(), 'batches': pipeline.repo.report_batches(),
                'batch_maximum': settings.random_batch_max_reports, 'readiness': settings.readiness(),
                'graph_experiments': graph_repo.experiments(), **extra}

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/')
    def home(request: Request):
        return templates.TemplateResponse(request=request, name='home.html', context=home_context())

    def graph_context(experiment_id: str, path_id: str | None = None):
        inspection = graph_repo.inspection(experiment_id)
        paths = {item.path_id: item for item in inspection['paths']}
        answer_paths = [path_id for answer in inspection['answers'] for path_id in answer.path_ids]
        selected_id = path_id if path_id in paths else next(
            (item for item in answer_paths if item in paths), next(iter(paths), None))
        selected = paths.get(selected_id)
        nodes = {item.node_id: item for item in inspection['nodes']}
        edges = {item.edge_id: item for item in inspection['edges']}
        inspection.update({
            'selected_path': selected,
            'node_lookup': nodes,
            'edge_lookup': edges,
            'path_lookup': paths,
            'path_for_node': {node_id: next((path.path_id for path in paths.values()
                                              if node_id in path.node_ids), None)
                              for node_id in nodes},
            'path_for_edge': {edge_id: next((path.path_id for path in paths.values()
                                              if edge_id in path.edge_ids), None)
                              for edge_id in edges},
        })
        return inspection

    @app.get('/v3/experiments')
    def graph_experiments(request: Request):
        return templates.TemplateResponse(request=request, name='v3_experiments.html', context={
            'experiments': graph_repo.experiments(),
            'rubric_reports': graph_repo.rubric_reports(),
            'development_ledger_reports': graph_repo.development_ledger_reports(),
        })

    @app.get('/v3/comparisons/{cohort_id}')
    def graph_comparison(request: Request, cohort_id: str):
        try:
            report = graph_repo.rubric_report(cohort_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 comparison cohort not found') from None
        return templates.TemplateResponse(request=request, name='v3_comparison.html', context={'report': report})

    @app.get('/v3/development-ledgers/{cohort_id}')
    def graph_development_ledger(request: Request, cohort_id: str):
        try:
            report = graph_repo.development_ledger_report(cohort_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 development ledger not found') from None
        return templates.TemplateResponse(request=request, name='v3_development_ledger.html', context={'report': report})

    @app.get('/v3/experiments/{experiment_id}')
    def graph_experiment(request: Request, experiment_id: str, path_id: str | None = None):
        try:
            context = graph_context(experiment_id, path_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 graph experiment not found') from None
        return templates.TemplateResponse(request=request, name='v3_experiment.html', context=context)

    @app.get('/v3/experiments/{experiment_id}/source')
    def graph_source(request: Request, experiment_id: str, line: int = 1):
        try:
            inspection = graph_repo.inspection(experiment_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 graph experiment not found') from None
        document = inspection['document']
        line = min(max(1, line), document.ref.line_count)
        start, end = max(1, line - 12), min(document.ref.line_count, line + 12)
        cited = {(source.start_line, source.end_line)
                 for item in [*inspection['nodes'], *inspection['edges']]
                 for source in item.evidence_ranges}
        return templates.TemplateResponse(request=request, name='v3_source.html', context={
            'experiment_id': experiment_id, 'document': document, 'focus_line': line,
            'lines': document.lines[start - 1:end], 'cited': cited,
        })

    @app.get('/v2/benchmark')
    def benchmark_overview(request: Request, version: str | None = None):
        return templates.TemplateResponse(
            request=request, name='v2_benchmark.html',
            context={'scorecard': cross_run_scorecard(pipeline.repo, version_id=version)},
        )

    @app.post('/v2/benchmark/regenerate')
    def regenerate_benchmarks():
        for run in pipeline.repo.recent(100):
            if pipeline.repo.stage(run.run_id, 'evaluate').status == 'completed':
                RetrievalBenchmarkService(pipeline.repo, settings).evaluate_automatic(run.run_id)
        return RedirectResponse('/v2/benchmark', status_code=303)

    @app.post('/v2/runs')
    async def create(request: Request):
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode())
        try:
            run = pipeline.create(fields.get('ticker', [''])[0])
            start(run.run_id)
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                context=home_context(error=settings.redactor().text(str(error))))
        return RedirectResponse(f'/v2/runs/{run.run_id}', status_code=303)

    @app.post('/v2/ticker-picker')
    async def pick_ticker(request: Request):
        picker = new_picker()
        selection = await asyncio.to_thread(picker.pick)
        if selection.ticker:
            try:
                run = pipeline.create(selection.ticker)
                start(run.run_id)
            except ValueError as error:
                return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                    context=home_context(error=settings.redactor().text(str(error))))
            return RedirectResponse(f'/v2/runs/{run.run_id}', status_code=303)
        return templates.TemplateResponse(request=request, name='home.html', status_code=503,
                                          context=home_context(error=selection.message))

    @app.post('/v2/batches')
    async def create_batch(request: Request):
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode())
        try:
            batch = batch_service.create(int(fields.get('count', [''])[0]))
            start_batch(batch.batch_id)
        except (TypeError, ValueError) as error:
            return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                context=home_context(error=settings.redactor().text(str(error))))
        return RedirectResponse(f'/v2/batches/{batch.batch_id}', status_code=303)

    @app.get('/v2/batches/{batch_id}')
    def batch_detail(request: Request, batch_id: str):
        try:
            batch = pipeline.repo.report_batch(batch_id)
            items = pipeline.repo.report_batch_items(batch_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 batch not found') from None
        counts = {outcome: sum(item.outcome == outcome for item in items)
                  for outcome in ('completed', 'failed', 'cancelled', 'skipped')}
        return templates.TemplateResponse(request=request, name='v2_batch.html', context={
            'batch': batch, 'items': items, 'counts': counts,
            'run_lookup': {run.run_id: run for run in pipeline.repo.runs()},
            'active_count': sum(item.outcome is None for item in items)})

    @app.post('/v2/batches/{batch_id}/cancel')
    def cancel_batch(batch_id: str):
        try:
            batch_service.cancel(batch_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(400, str(error)) from None
        return RedirectResponse(f'/v2/batches/{batch_id}', status_code=303)

    @app.post('/v2/batches/{batch_id}/resume')
    def resume_batch(batch_id: str):
        try:
            batch_service.resume(batch_id)
            start_batch(batch_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(400, str(error)) from None
        return RedirectResponse(f'/v2/batches/{batch_id}', status_code=303)

    def context(run_id, stage, page):
        if stage not in STAGE_NAMES:
            raise ValueError('Unknown V2 stage')
        state = pipeline.repo.state(run_id)
        selected = next(item for item in state['stages'] if item.stage == stage)
        page = max(1, page)
        data_stages = {'outline', 'section_score', 'chunk', 'chunk_score', 'findings', 'facts', 'evaluate'}
        outline = ([item.model_copy(update={
            'parent_topic_hint': item.parent_topic_hint or 'Filing overview'})
            for item in pipeline.repo.outline_sections(run_id, page=page)]
            if stage in data_stages else [])
        chunks = pipeline.repo.chunks(run_id, page=page) if stage in {'chunk', 'chunk_score', 'findings'} else []
        findings = pipeline.repo.findings(run_id, page=page) if stage in {'findings', 'evaluate'} else []
        finding_scores = pipeline.repo.scores_for_items(
            run_id, 'chunk_score', [item.source_chunk_id for item in findings if item.source_chunk_id])
        finding_score_lookup = {}
        finding_types = {'annual_profit', 'diluted_eps', 'diluted_shares'}
        for score in finding_scores:
            candidates = [(value, label) for label, value in score.target_scores.items()
                          if label in finding_types]
            if candidates:
                value, label = max(candidates, key=lambda item: (item[0], item[1]))
                finding_score_lookup[score.item_id] = {'label': label, 'score': value}
        # T39 decisions are diagnostics beside flat chunk retention. Keep the
        # exploration surface bounded to the chunks/findings currently displayed.
        displayed_ranges = [item.core_range for item in chunks]
        displayed_ranges.extend(item.source_range for item in findings)

        def overlaps_displayed(source_range):
            return any(
                source_range.document_id == item.document_id and
                source_range.source_hash == item.source_hash and
                source_range.start_line <= item.end_line and item.start_line <= source_range.end_line
                for item in displayed_ranges)

        source_context_decisions = (
            [item for item in pipeline.repo.source_context_decisions(run_id)
             if overlaps_displayed(item.core_range)]
            if stage in {'chunk', 'chunk_score', 'findings'} else [])
        result = {**state, 'selected': selected, 'page': page, 'canonical_refs': pipeline.repo.canonical_refs(run_id),
                  'outline_sections': outline, 'section_lookup': {x.section_id: x for x in outline},
                  'section_scores': pipeline.repo.scores(run_id, 'section_score', page=page) if stage == 'section_score' else [],
                  'section_actions': [], 'chunks': chunks,
                  'chunk_scores': pipeline.repo.scores(run_id, 'chunk_score', page=page) if stage == 'chunk_score' else [],
                  'chunk_score_summary': pipeline.repo.chunk_score_summary(run_id) if stage == 'chunk_score' else None,
                  'chunk_actions': [], 'findings': findings, 'finding_score_lookup': finding_score_lookup,
                  'source_context_decisions': source_context_decisions,
                  'source_replay': (SourceReplayService(pipeline.repo).inspect(run_id)
                                    if stage in {'findings', 'evaluate'} else None),
                  'finding_summary': pipeline.repo.finding_summary(run_id) if stage == 'findings' else None,
                  'finding_actions': [], 'structured_facts': pipeline.repo.structured_facts(run_id, page=page) if stage in {'facts', 'evaluate'} else [],
                  'fact_summary': pipeline.repo.fact_summary(run_id) if stage == 'facts' else None,
                  'comparisons': pipeline.repo.comparisons(run_id, page=page) if stage == 'evaluate' else [],
                  'comparison_summary': pipeline.repo.comparison_summary(run_id) if stage == 'evaluate' else None,
                  'evaluation_cards': []}
        if stage == 'evaluate':
            # A comparison page is bounded, but its cards need the linked inputs even
            # when the finding or fact sorts onto a different storage page.
            all_findings = {item.finding_id: item for item in pipeline.repo.findings(run_id)}
            all_facts = {item.fact_id: item for item in pipeline.repo.structured_facts(run_id)}
            chunks = {item.chunk_id: item for item in pipeline.repo.chunks(run_id)}
            documents = {}

            def visible_context(finding):
                chunk = chunks.get(finding.source_chunk_id)
                if not chunk:
                    return []
                document = documents.setdefault(
                    chunk.core_range.document_id,
                    pipeline.repo.canonical_document(run_id, chunk.core_range.document_id))
                ranges = [chunk.core_range, *chunk.context_ranges]
                lines = []
                for source_range in ranges:
                    for line in document.lines[source_range.start_line - 1:source_range.end_line]:
                        lines.append({'number': line.line_number, 'text': line.text[:280]})
                        if len(lines) == 6:
                            return lines
                return lines

            labels = {
                'exact_match': ('Exact match', 'exact'),
                'scale_aware_equivalent': ('Confirmed scale-aware equivalent', 'confirmed'),
                'jev_rejected': ('Rejected by Jev', 'rejected'),
                'jev_inconclusive': ('Unresolved by Jev', 'unresolved'),
                'structured_fact_missed': ('Missing visible finding', 'missing'),
                'additional_visible_value': ('Additional visible finding', 'additional'),
                'value_match_period_unresolved': ('Value match; period unresolved', 'unresolved'),
                'period_match_value_mismatch': ('Period match; value mismatch', 'rejected'),
                'period_match_unit_mismatch': ('Period match; unit mismatch', 'rejected'),
                'unsupported': ('Unsupported visible finding', 'unresolved'),
                'ambiguous_duplicate': ('Ambiguous structured facts', 'unresolved'),
            }
            for comparison in result['comparisons']:
                findings_for_card = [all_findings[item] for item in comparison.finding_ids if item in all_findings]
                fact = all_facts.get(comparison.fact_id)
                label, tone = labels[comparison.state]
                result['evaluation_cards'].append({
                    'comparison': comparison, 'fact': fact, 'findings': findings_for_card,
                    'label': label, 'tone': tone,
                    'kind': 'additional' if comparison.state == 'additional_visible_value' else 'expected',
                    'context': {item.finding_id: visible_context(item) for item in findings_for_card},
                    'diagnostic': comparison.model_dump(mode='json'),
                })
        result['has_next'] = max(len(result['outline_sections']), len(result['section_scores']), len(result['chunks']),
                                 len(result['chunk_scores']), len(result['findings']), len(result['structured_facts']), len(result['comparisons'])) == 100
        return result

    @app.get('/v2/runs/{run_id}')
    @app.get('/v2/runs/{run_id}/pipeline')
    @app.get('/v2/runs/{run_id}/pipeline/{stage}')
    def workspace(request: Request, run_id: str, stage: str = 'source', page: int = 1):
        started = monotonic()
        try:
            body = templates.TemplateResponse(request=request, name='v2_workspace.html', context=context(run_id, stage, page))
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'V2 run not found') from None
        pipeline.repo.record_route_measurement(run_id, route=f'pipeline:{stage}', latency_ms=(monotonic() - started) * 1000, payload_bytes=len(body.body))
        return body

    @app.get('/v2/runs/{run_id}/pipeline/{stage}/trace')
    def trace(request: Request, run_id: str, stage: str):
        if stage not in {'section_score', 'chunk_score', 'findings', 'evaluate'}:
            raise HTTPException(404, 'No provider trace for this stage')
        return templates.TemplateResponse(request=request, name='v2_trace.html', context={
            'run_id': run_id, 'stage': stage, 'actions': pipeline.repo.exploration_actions(run_id, stage, limit=100)})

    @app.get('/v2/runs/{run_id}/chunks/{chunk_id}')
    def chunk(request: Request, run_id: str, chunk_id: str):
        try:
            item = pipeline.repo.chunk(run_id, chunk_id)
            document = pipeline.repo.canonical_document(run_id, item.core_range.document_id)
            section = next(x for x in pipeline.repo.outline_sections(run_id) if x.section_id == item.section_id)
        except (FileNotFoundError, StopIteration):
            raise HTTPException(404, 'V2 chunk not found') from None
        return templates.TemplateResponse(request=request, name='v2_chunk.html', context={
            'run_id': run_id, 'chunk': item, 'section': section, 'document': document,
            'core_preview': document.slice(item.core_range)[:3000],
            'context_previews': [(r, document.slice(r)[:1200]) for r in item.context_ranges],
            'source_context_decisions': [decision for decision in pipeline.repo.source_context_decisions(run_id)
                                         if decision.core_range.document_id == item.core_range.document_id and
                                         decision.core_range.source_hash == item.core_range.source_hash and
                                         decision.core_range.start_line <= item.core_range.end_line and
                                         item.core_range.start_line <= decision.core_range.end_line],
        })

    @app.get('/v2/runs/{run_id}/state')
    def state(run_id: str):
        try:
            return pipeline.repo.state(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None

    @app.get('/v2/runs/{run_id}/source')
    def source(request: Request, run_id: str, document: str = '', page: int = 1):
        try:
            refs = pipeline.repo.canonical_refs(run_id)
            ref = next((x for x in refs if x.document_id == document), refs[0])
            canonical = pipeline.repo.canonical_document(run_id, ref.document_id)
        except (FileNotFoundError, IndexError):
            raise HTTPException(404, 'V2 canonical source not found') from None
        page, per_page = max(1, page), 100
        offset = (page - 1) * per_page
        if offset >= canonical.ref.line_count and offset:
            raise HTTPException(404, 'Source page not found')
        return templates.TemplateResponse(request=request, name='v2_source.html', context={
            'run_id': run_id, 'document': canonical, 'lines': canonical.lines[offset:offset + per_page],
            'page': page, 'has_previous': page > 1, 'has_next': offset + per_page < canonical.ref.line_count})

    @app.get('/v2/runs/{run_id}/source/{document_id}/html')
    def source_html(run_id: str, document_id: str):
        from fastapi.responses import HTMLResponse
        try:
            return HTMLResponse(pipeline.repo.visible_html(run_id, document_id))
        except FileNotFoundError:
            raise HTTPException(404, 'V2 canonical source not found') from None

    @app.get('/v2/runs/{run_id}/events')
    async def events(request: Request, run_id: str, after: int = 0):
        try:
            pipeline.repo.get_run(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None
        async def stream():
            cursor = max(after, 0)
            for _ in range(40):
                if await request.is_disconnected(): break
                updates = pipeline.repo.events(run_id, cursor)
                for update in updates:
                    cursor = update.sequence
                    yield f'id: {cursor}\nevent: pipeline\ndata: {update.model_dump_json()}\n\n'
                if pipeline.repo.get_run(run_id).status not in ('queued', 'running') and not updates: break
                if not updates: yield ': keepalive\n\n'
                await asyncio.sleep(.25)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.post('/v2/runs/{run_id}/cancel')
    def cancel(run_id: str):
        pipeline.cancel(run_id)
        return RedirectResponse(f'/v2/runs/{run_id}', status_code=303)

    @app.post('/v2/runs/{run_id}/resume')
    async def resume(run_id: str):
        try:
            pipeline.resume(run_id); start(run_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'V2 run cannot be resumed') from None
        return RedirectResponse(f'/v2/runs/{run_id}', status_code=303)

    @app.post('/v2/runs/{run_id}/benchmark')
    def benchmark(run_id: str):
        try:
            run = pipeline.repo.get_run(run_id)
            filing = pipeline.repo.filing(run_id)
            document = pipeline.repo.canonical_document(run_id, filing['document_id'])
            dataset = benchmark_dataset or load_dataset()
            case = dataset.case_for(ticker=run.ticker, accession=filing.get('accession'),
                                    source_hash=document.ref.source_hash)
            if not case:
                raise ValueError('No immutable reviewed benchmark case matches this company, accession, and source hash.')
            RetrievalBenchmarkService(pipeline.repo, settings).evaluate(
                run_id, case, provider_identity='replayed persisted provider output')
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(400, str(error)) from None
        return RedirectResponse(f'/v2/runs/{run_id}/pipeline?stage=evaluate', status_code=303)

    @app.post('/v2/runs/{run_id}/remove')
    def remove(run_id: str):
        task = tasks.pop(run_id, None)
        if task and not task.done():
            task.cancel()
        try:
            pipeline.repo.remove_run(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None
        return RedirectResponse('/', status_code=303)

    @app.post('/v2/cache/clear')
    def clear_cache():
        pipeline.repo.clear_shared_caches()
        return RedirectResponse('/', status_code=303)

    return app
