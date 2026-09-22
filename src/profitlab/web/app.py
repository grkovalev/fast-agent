import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from profitlab.demo import DemoService
from profitlab.pipeline import JobManager, PipelineService
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder
from profitlab.v2 import STAGE_NAMES, V2PipelineService

WEB_DIR = Path(__file__).parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    service = DemoService(settings.data_dir)
    pipeline = PipelineService(settings)
    jobs = JobManager(pipeline)
    v2_pipeline = V2PipelineService(settings)
    v2_tasks = {}

    def start_v2(run_id):
        task = v2_tasks.get(run_id)
        if task and not task.done():
            raise ValueError('V2 run is already active.')
        task = asyncio.create_task(v2_pipeline.run(run_id, delay=.05, implement_source=True))
        task.add_done_callback(lambda completed: completed.exception()
                               if not completed.cancelled() else None)
        v2_tasks[run_id] = task

    def resume_v2(run_id):
        v2_pipeline.resume(run_id)
        start_v2(run_id)

    @asynccontextmanager
    async def lifespan(app):
        pipeline.recover()
        v2_pipeline.recover()
        repo = Repository(settings.data_dir)
        for run in repo.recent():
            if not pipeline.state(run.run_id):
                TraceRecorder(repo, run.run_id, settings.redactor()).recover_interrupted()
        yield
        await jobs.close()
        for task in v2_tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*v2_tasks.values(), return_exceptions=True)

    app = FastAPI(title="ProfitLab", lifespan=lifespan)
    templates = Jinja2Templates(directory=WEB_DIR / "templates")

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def home(request: Request):
        return templates.TemplateResponse(
            request=request, name="home.html",
            context={"runs": service.recent(), "v2_runs": v2_pipeline.repo.recent(),
                     "readiness": settings.readiness()},
        )

    @app.post('/v2/runs')
    async def create_v2(request: Request):
        from urllib.parse import parse_qs

        fields = parse_qs((await request.body()).decode())
        try:
            run = v2_pipeline.create(fields.get('ticker', ['DEMO'])[0],
                                     mode=fields.get('mode', ['offline'])[0])
            start_v2(run.run_id)
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                context={'runs': service.recent(), 'v2_runs': v2_pipeline.repo.recent(),
                         'readiness': settings.readiness(),
                         'error': settings.redactor().text(str(error))})
        return RedirectResponse(f'/v2/runs/{run.run_id}', status_code=303)

    def v2_context(run_id: str, stage: str, page: int = 1):
        """Return one bounded page of stage data for the reader-facing workspace."""
        if stage not in STAGE_NAMES:
            raise ValueError('Unknown V2 stage')
        state = v2_pipeline.repo.state(run_id)
        selected = next(item for item in state['stages'] if item.stage == stage)
        page = max(page, 1)
        data_stages = {'outline', 'section_score', 'chunk', 'chunk_score', 'findings', 'facts', 'evaluate'}
        outline_sections = (v2_pipeline.repo.outline_sections(run_id, page=page)
                            if stage in data_stages else [])
        chunks = (v2_pipeline.repo.chunks(run_id, page=page)
                  if stage in {'chunk', 'chunk_score', 'findings'} else [])
        context = {
            **state, 'selected': selected, 'page': page,
            'has_next': False,
            'canonical_refs': v2_pipeline.repo.canonical_refs(run_id),
            'outline_sections': outline_sections,
            'section_lookup': {item.section_id: item for item in outline_sections},
            'section_scores': (v2_pipeline.repo.scores(run_id, 'section_score', page=page)
                               if stage == 'section_score' else []),
            'section_actions': [],
            'chunks': chunks,
            'chunk_scores': (v2_pipeline.repo.scores(run_id, 'chunk_score', page=page)
                             if stage == 'chunk_score' else []),
            'chunk_score_summary': v2_pipeline.repo.chunk_score_summary(run_id) if stage == 'chunk_score' else None,
            'chunk_actions': [],
            'findings': (v2_pipeline.repo.findings(run_id, page=page)
                         if stage in {'findings', 'evaluate'} else []),
            'finding_summary': v2_pipeline.repo.finding_summary(run_id) if stage == 'findings' else None,
            'finding_actions': [],
            'structured_facts': (v2_pipeline.repo.structured_facts(run_id, page=page)
                                 if stage in {'facts', 'evaluate'} else []),
            'fact_summary': v2_pipeline.repo.fact_summary(run_id) if stage == 'facts' else None,
            'comparisons': (v2_pipeline.repo.comparisons(run_id, page=page)
                            if stage == 'evaluate' else []),
            'comparison_summary': v2_pipeline.repo.comparison_summary(run_id) if stage == 'evaluate' else None,
        }
        repeated = max(len(context['outline_sections']), len(context['section_scores']),
                       len(context['chunks']), len(context['chunk_scores']),
                       len(context['findings']), len(context['structured_facts']),
                       len(context['comparisons']))
        context['has_next'] = repeated == 100
        return context

    @app.get('/v2/runs/{run_id}')
    @app.get('/v2/runs/{run_id}/pipeline')
    def v2_workspace(request: Request, run_id: str, stage: str = 'source', page: int = 1):
        started = monotonic()
        try:
            context = v2_context(run_id, stage, page)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'V2 run not found') from None
        response = templates.TemplateResponse(request=request, name='v2_workspace.html', context=context)
        v2_pipeline.repo.record_route_measurement(
            run_id, route=f'pipeline:{stage}', latency_ms=(monotonic() - started) * 1000,
            payload_bytes=len(response.body))
        return response

    @app.get('/v2/runs/{run_id}/pipeline/{stage}/trace')
    def v2_stage_trace(request: Request, run_id: str, stage: str):
        if stage not in {'section_score', 'chunk_score', 'findings'}:
            raise HTTPException(404, 'No provider trace for this stage')
        try:
            actions = v2_pipeline.repo.exploration_actions(run_id, stage, limit=100)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None
        return templates.TemplateResponse(request=request, name='v2_trace.html',
                                          context={'run_id': run_id, 'stage': stage, 'actions': actions})

    @app.get('/v2/runs/{run_id}/chunks/{chunk_id}')
    def v2_chunk_inspector(request: Request, run_id: str, chunk_id: str):
        try:
            item = v2_pipeline.repo.chunk(run_id, chunk_id)
            document = v2_pipeline.repo.canonical_document(run_id, item.core_range.document_id)
            section = next(section for section in v2_pipeline.repo.outline_sections(run_id)
                           if section.section_id == item.section_id)
        except (FileNotFoundError, StopIteration):
            raise HTTPException(404, 'V2 chunk not found') from None
        return templates.TemplateResponse(request=request, name='v2_chunk.html', context={
            'run_id': run_id, 'chunk': item, 'section': section, 'document': document,
            'core_preview': document.slice(item.core_range)[:3000],
            'context_previews': [(source_range, document.slice(source_range)[:1200])
                                 for source_range in item.context_ranges],
        })

    @app.get('/v2/runs/{run_id}/state')
    def v2_state(run_id: str):
        try:
            return v2_pipeline.repo.state(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None

    @app.get('/v2/runs/{run_id}/source')
    def v2_source_lines(request: Request, run_id: str, document: str = '', page: int = 1):
        try:
            refs = v2_pipeline.repo.canonical_refs(run_id)
            if not refs:
                raise FileNotFoundError(run_id)
            ref = next((item for item in refs if item.document_id == document), refs[0])
            canonical = v2_pipeline.repo.canonical_document(run_id, ref.document_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 canonical source not found') from None
        page = max(1, page)
        per_page = 100
        start = (page - 1) * per_page
        if start >= canonical.ref.line_count and start:
            raise HTTPException(404, 'Source page not found')
        return templates.TemplateResponse(request=request, name='v2_source.html', context={
            'run_id': run_id, 'document': canonical, 'lines': canonical.lines[start:start + per_page],
            'page': page, 'has_previous': page > 1,
            'has_next': start + per_page < canonical.ref.line_count,
        })

    @app.get('/v2/runs/{run_id}/source/{document_id}/html')
    def v2_source_html(run_id: str, document_id: str):
        from fastapi.responses import HTMLResponse
        try:
            content = v2_pipeline.repo.visible_html(run_id, document_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 canonical source not found') from None
        return HTMLResponse(content)

    @app.get('/v2/runs/{run_id}/events')
    async def v2_events(request: Request, run_id: str, after: int = 0):
        try:
            v2_pipeline.repo.get_run(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None

        async def stream():
            cursor = max(after, 0)
            for _ in range(40):
                if await request.is_disconnected():
                    break
                events = v2_pipeline.repo.events(run_id, cursor)
                for event in events:
                    cursor = event.sequence
                    yield f'id: {cursor}\nevent: pipeline\ndata: {event.model_dump_json()}\n\n'
                run = v2_pipeline.repo.get_run(run_id)
                if run.status not in ('queued', 'running') and not events:
                    break
                if not events:
                    yield ': keepalive\n\n'
                await asyncio.sleep(.25)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={
            'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
        })

    @app.post('/v2/runs/{run_id}/cancel')
    def cancel_v2(run_id: str):
        try:
            v2_pipeline.cancel(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None
        return RedirectResponse(f'/v2/runs/{run_id}', status_code=303)

    @app.post('/v2/runs/{run_id}/resume')
    def resume_v2_run(run_id: str):
        try:
            resume_v2(run_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'V2 run cannot be resumed') from None
        return RedirectResponse(f'/v2/runs/{run_id}', status_code=303)

    @app.get("/runs/{run_id}")
    def overview(request: Request, run_id: str):
        try:
            run = service.get(run_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Run not found") from None
        from profitlab.sec.contracts import DiscoveryResult

        try:
            discovery = DiscoveryResult.model_validate_json(
                Repository(settings.data_dir).read(run_id, 'discovery'))
        except FileNotFoundError:
            discovery = None
        return templates.TemplateResponse(
            request=request, name="run.html", context={
                "run": run, "artifacts": Repository(settings.data_dir).artifacts(run_id),
                'discovery': discovery, 'workflow': pipeline.state(run_id),
            },
        )

    @app.post('/analyze')
    async def analyze(request: Request):
        from urllib.parse import parse_qs

        fields = parse_qs((await request.body()).decode())
        try:
            run = pipeline.create(fields.get('ticker', [''])[0],
                int(fields.get('years', ['4'])[0]), fields.get('mode', ['demo'])[0],
                scenario=fields.get('scenario', ['normal'])[0])
            jobs.start(run.run_id)
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                context={'runs': service.recent(), 'v2_runs': v2_pipeline.repo.recent(),
                         'readiness': settings.readiness(),
                         'error': settings.redactor().text(str(error))})
        return RedirectResponse(f'/runs/{run.run_id}', status_code=303)

    @app.get('/runs/{run_id}/progress')
    def progress(run_id: str, detail: bool = False):
        try:
            state = pipeline.state(run_id)
            if not state:
                raise ValueError('No workflow')
            if state.run.status == 'running' and state.started_at:
                from datetime import UTC, datetime

                state = state.model_copy(update={'elapsed_seconds': state.elapsed_seconds +
                    (datetime.now(UTC) - state.started_at).total_seconds()})
            data = settings.redactor()(state)
            if not detail:
                for stage in data['stages']:
                    stage['output_count'] = len(stage.pop('output_ids'))
            return data
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Managed workflow not found') from None

    @app.post('/runs/{run_id}/cancel')
    async def cancel(run_id: str):
        try:
            jobs.cancel(run_id)
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(400, settings.redactor().text(str(error))) from None
        return RedirectResponse(f'/runs/{run_id}', status_code=303)

    @app.post('/runs/{run_id}/resume')
    async def resume(run_id: str):
        try:
            state = pipeline.state(run_id)
            if not state or state.run.status in ('queued', 'running'):
                raise ValueError('Workflow is unavailable or already active.')
            jobs.start(run_id)
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(400, settings.redactor().text(str(error))) from None
        return RedirectResponse(f'/runs/{run_id}', status_code=303)

    @app.post('/discover')
    async def discover(request: Request):
        from urllib.parse import parse_qs

        from profitlab.sec.service import DiscoveryService

        fields = parse_qs((await request.body()).decode())
        try:
            run = await run_in_threadpool(DiscoveryService(settings).create,
                fields.get('ticker', [''])[0], int(fields.get('years', ['4'])[0]),
                fields.get('mode', ['demo'])[0])
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='home.html', status_code=400,
                context={'runs': service.recent(), 'v2_runs': v2_pipeline.repo.recent(),
                         'readiness': settings.readiness(),
                         'error': settings.redactor().text(str(error))})
        return RedirectResponse(f'/runs/{run.run_id}', status_code=303)

    @app.get('/runs/{run_id}/artifacts/{artifact_id}')
    def artifact(request: Request, run_id: str, artifact_id: str):
        try:
            content = Repository(settings.data_dir).read(run_id, artifact_id).decode()
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Artifact not found or damaged') from None
        return templates.TemplateResponse(
            request=request, name='artifact.html',
            context={'run_id': run_id, 'artifact_id': artifact_id,
                     'content': settings.redactor().text(content)},
        )

    def trace_data(run_id, filters):
        try:
            run = service.get(run_id)
            recorder = TraceRecorder(Repository(settings.data_dir), run_id, settings.redactor())
            events, warnings = recorder.history()
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'Run not found') from None
        selected = []
        for event in events:
            data = settings.redactor()(event)
            if any(filters.get(key) and data.get(key) != filters[key]
                   for key in ('stage', 'actor', 'kind', 'provider', 'tool')):
                continue
            if filters.get('error_only') and event.status not in ('failed', 'interrupted'):
                continue
            if event.sequence <= int(filters.get('after_sequence', 0)):
                continue
            query = filters.get('q', '').lower()
            search = event.model_dump_json()
            if query:
                for identifier in (event.request_artifact_id, event.result_artifact_id):
                    if identifier:
                        search += recorder.repo.read(run_id, identifier).decode()
                if query not in search.lower():
                    continue
            selected.append(data)
        return run, selected, warnings

    @app.get('/runs/{run_id}/trace/events')
    def trace_events(request: Request, run_id: str, after_sequence: int = 0):
        filters = dict(request.query_params)
        filters['after_sequence'] = after_sequence
        _, events, warnings = trace_data(run_id, filters)
        return {'events': events, 'warnings': warnings}

    @app.get('/runs/{run_id}/trace')
    def trace_page(request: Request, run_id: str):
        filters = dict(request.query_params)
        # The incremental cursor belongs to the JSON endpoint only.
        filters.pop('after_sequence', None)
        run, events, warnings = trace_data(run_id, filters)
        return templates.TemplateResponse(request=request, name='trace.html', context={
            'run': run, 'events': events, 'warnings': warnings, 'filters': filters,
            'has_model_calls': any(e.actor == 'model' for e in TraceRecorder(Repository(settings.data_dir), run_id).history()[0]),
        })

    @app.get('/runs/{run_id}/trace/payloads/{artifact_id}')
    def trace_payload(run_id: str, artifact_id: str):
        try:
            recorder = TraceRecorder(Repository(settings.data_dir), run_id, settings.redactor())
            events, _ = recorder.history()
            allowed = {identifier for event in events for identifier in
                       (event.request_artifact_id, event.result_artifact_id) if identifier}
            if artifact_id not in allowed:
                raise ValueError('Unknown trace payload')
            import json

            return settings.redactor()(json.loads(recorder.repo.read(run_id, artifact_id)))
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'Trace payload not found or damaged') from None

    @app.get('/runs/{run_id}/sources')
    def sources(request: Request, run_id: str):
        from profitlab.documents.service import SourceService

        try:
            run, items = SourceService(settings).sources(run_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Sources not found or damaged') from None
        return templates.TemplateResponse(request=request, name='sources.html',
            context={'run': run, 'items': items})

    @app.get('/runs/{run_id}/sources/{filing_id}')
    def source(request: Request, run_id: str, filing_id: str,
               cell: str = '', row: str = '', column: str = ''):
        from profitlab.documents.service import SourceService

        try:
            run, item = SourceService(settings).document(run_id, filing_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Source not found or damaged') from None
        cells = item['cells']
        if (cell and cell not in cells or row and row not in {c.row_id for c in cells.values()}
                or column and column not in {c.column_id for c in cells.values()}):
            raise HTTPException(400, 'Unknown highlight coordinate')
        row_cells, column_cells = set(), set()
        for table_id, table in item['index']['tables'].items():
            for rendered_row in table['rows']:
                for coordinate in rendered_row:
                    c = cells[coordinate['cell_id']]
                    if row and row.startswith(table_id + '-r'):
                        target = int(row.rsplit('-r', 1)[1])
                        if coordinate['row'] <= target < coordinate['row'] + c.row_span:
                            row_cells.add(c.cell_id)
                    if column and column.startswith(table_id + '-c'):
                        target = int(column.rsplit('-c', 1)[1])
                        if coordinate['column'] <= target < coordinate['column'] + c.column_span:
                            column_cells.add(c.cell_id)
        return templates.TemplateResponse(request=request, name='source.html',
            context={'run': run, 'item': item, 'cell': cell,
                     'row_cells': row_cells, 'column_cells': column_cells})

    @app.get('/runs/{run_id}/chunks')
    def chunks(request: Request, run_id: str, filing: str = '', heading: str = '',
               min_tokens: int = 0, max_tokens: int | None = None):
        from profitlab.documents.chunk_service import ChunkService

        try:
            run, all_chunks = ChunkService(settings).list(run_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Chunks not found or damaged') from None
        from profitlab.providers.screening import ScreeningService

        screening, decisions = ScreeningService(settings).latest(run_id)
        items = []
        for i, chunk in enumerate(all_chunks):
            if (filing and chunk.filing_id != filing or
                    heading.lower() not in ' / '.join(chunk.heading_path).lower() or
                    chunk.token_estimate < min_tokens or
                    max_tokens is not None and chunk.token_estimate > max_tokens):
                continue
            previous = all_chunks[i-1] if i and all_chunks[i-1].filing_id == chunk.filing_id else None
            following = all_chunks[i+1] if i+1 < len(all_chunks) and all_chunks[i+1].filing_id == chunk.filing_id else None
            items.append({'chunk': chunk, 'previous': previous, 'following': following,
                          'screen': decisions.get(chunk.chunk_id)})
        return templates.TemplateResponse(request=request, name='chunks.html', context={
            'run': run, 'items': items, 'filings': sorted({c.filing_id for c in all_chunks}),
            'filing': filing, 'heading': heading, 'min_tokens': min_tokens,
            'max_tokens': max_tokens, 'screening': screening})

    @app.get('/runs/{run_id}/candidates')
    def candidates(request: Request, run_id: str):
        from profitlab.analysis.reconciliation import ReconciliationService
        from profitlab.providers.extraction import ExtractionService

        try:
            run = service.get(run_id)
            index, attempts = ExtractionService(settings).latest(run_id)
            reconciliation, groups, observations = ReconciliationService(settings).latest(run_id)
            stale_selection = bool(reconciliation and index and
                                   reconciliation['extraction_created_at'] != index['created_at'])
            if stale_selection:
                reconciliation, groups, observations = None, [], []
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Candidates not found or damaged') from None
        import json

        repo = Repository(settings.data_dir)
        evidence_ids = {a.evidence_id for a in attempts if a.evidence_id}
        evidence_ids.update(eid for a in attempts if a.candidate for eid in a.candidate.evidence_ids)
        evidence = {eid: json.loads(repo.read(run_id, eid)) for eid in evidence_ids}
        cells = {cid: json.loads(repo.read(run_id, cid)) for e in evidence.values() for cid in e['cell_ids']}
        return templates.TemplateResponse(request=request, name='candidates.html',
            context={'run': run, 'index': index, 'attempts': attempts, 'evidence': evidence, 'cells': cells,
                     'reconciliation': reconciliation, 'groups': groups, 'observations': observations,
                     'stale_selection': stale_selection,
                     'facts': {a.candidate.candidate_id: a.candidate for a in attempts if a.candidate},
                     'names': {'eps_diluted': 'Diluted EPS', 'weighted_average_shares_diluted': 'Diluted shares',
                               'net_income_common': 'Net income · common shareholders',
                               'net_income_parent': 'Net income · parent',
                               'net_income_consolidated': 'Net income · consolidated'}})

    @app.get('/runs/{run_id}/calculations')
    @app.get('/runs/{run_id}/report')
    def calculations(request: Request, run_id: str):
        from profitlab.analysis.calculations import CalculationService, display

        try:
            run = service.get(run_id)
            index, items, observations, facts = CalculationService(settings).latest(run_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Run not found or damaged') from None
        from profitlab.analysis.reporting import ReportingService

        written, narrative, rendered = ReportingService(settings).latest(run_id)
        return templates.TemplateResponse(request=request, name='calculations.html', context={
            'run': run, 'index': index, 'items': items, 'observations': observations,
            'evidence': {eid: json.loads(Repository(settings.data_dir).read(run_id, eid)) for eid in narrative.source_index} if narrative else {},
            'written': written, 'narrative': narrative, 'rendered': rendered,
            'facts': facts, 'display': display, 'report': request.url.path.endswith('/report')})

    @app.get('/runs/{run_id}/checks')
    def checks(request: Request, run_id: str):
        try:
            run = service.get(run_id)
            repo = Repository(settings.data_dir)
            items = [json.loads(repo.read(run_id, a['artifact_id'])) for a in repo.artifacts(run_id) if a['artifact_id'].startswith('checks-report-')]
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Run not found or damaged') from None
        return templates.TemplateResponse(request=request, name='checks.html', context={'run': run, 'items': items})

    return app
