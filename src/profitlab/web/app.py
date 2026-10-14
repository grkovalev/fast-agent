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
from profitlab.v2.chunk_scoring import ChunkScoringService
from profitlab.v2.chunking import SourceRangeChunker
from profitlab.v2.contracts import (
    CanonicalDocumentRef,
    FactComparison,
    Finding,
    OutlineSection,
    ScoredItem,
    SourceRange,
    StructuredFact,
    TextChunk,
)
from profitlab.v2.evaluation_service import EvaluationService, cross_run_scorecard
from profitlab.v2.facts_service import CompanyFactsService
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.inspection import contract_envelopes
from profitlab.v2.outline_service import OutlineService
from profitlab.v2.section_scoring import SectionScoringService
from profitlab.v2.source_service import V2SourceService
from profitlab.web.fact_provenance import presentation_preview, source_preview
from profitlab.web.findings_results import findings_step_results

WEB_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, ticker_picker_factory=None,
               benchmark_dataset=None) -> FastAPI:
    settings = settings or Settings()
    pipeline, tasks, batch_tasks = V2PipelineService(settings), {}, {}

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
                'batch_maximum': settings.random_batch_max_reports, 'readiness': settings.readiness(), **extra}

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/')
    def home(request: Request):
        return templates.TemplateResponse(request=request, name='home.html', context=home_context())

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

    stage_presentation = {
        'source': ('⌁', 'Source', 'Visible filing'),
        'outline': ('☷', 'Outline', 'Map topics'),
        'section_score': ('⌕', 'Sections', 'Find sections'),
        'chunk': ('▤', 'Chunks', 'Bound text'),
        'chunk_score': ('◆', 'Evidence', 'Keep evidence'),
        'findings': ('❝', 'Findings', 'Quote claims'),
        'facts': ('▦', 'Facts', 'SEC data'),
        'evaluate': ('⇄', 'Evaluate', 'Compare'),
    }
    stage_status_presentation = {
        'completed': ('✓', 'Complete'),
        'running': ('●', 'Running'),
        'queued': ('○', 'Queued'),
        'partial': ('◐', 'Partial'),
        'failed': ('!', 'Failed'),
        'cancelled': ('×', 'Cancelled'),
        'interrupted': ('!', 'Interrupted'),
    }

    def context(run_id, stage, page):
        if stage is not None and stage not in STAGE_NAMES:
            raise ValueError('Unknown V2 stage')
        state = pipeline.repo.state(run_id)
        try:
            filing = pipeline.repo.filing(run_id)
        except FileNotFoundError:
            filing = {}
        report_date = filing.get('report_date', '')
        company_name_from_facts = pipeline.repo.company_fact_entity_name(run_id)
        report_identity = {
            'company_name': (filing.get('company_name')
                             or company_name_from_facts
                             or 'Not available'),
            'report_year': report_date[:4] or 'Not available',
            'created_on': state['run'].created_at.strftime('%Y-%m-%d'),
        }
        canonical_refs = pipeline.repo.canonical_refs(run_id)
        source_ref = canonical_refs[0] if canonical_refs else None
        if filing and source_ref:
            source_content = {
                'request': 'SEC primary filing',
                'received': (f"Primary filing HTML · {filing.get('form', 'filing')} · "
                             f"report date {filing.get('report_date', 'not available')}"),
                'stored': f'{source_ref.line_count:,} canonical visible lines',
            }
        elif filing:
            source_content = {
                'request': 'SEC primary filing',
                'received': (f"Primary filing HTML · {filing.get('form', 'filing')} · "
                             'preparing visible lines'),
                'stored': 'Canonical visible lines pending',
            }
        else:
            source_content = {
                'request': 'SEC primary filing',
                'received': 'Awaiting SEC response',
                'stored': 'Canonical visible lines pending',
            }
        source_content['inspection'] = V2SourceService.inspection_view(**source_content)
        source_content['document_ref'] = source_ref
        source_content['filing_id'] = filing.get('filing_id') if filing else None
        outline_stage = next(item for item in state['stages'] if item.stage == 'outline')
        outline_summary = pipeline.repo.outline_summary(run_id)
        outline_content = {
            'prompt': OutlineService.prompt_view(),
            'system_prompt': OutlineService.system_prompt,
            'response_contract': OutlineService.response_contract_view(),
            'inspection': OutlineService.inspection_view(settings),
            'model': settings.outline_model,
            'prompt_version': settings.outline_prompt_version,
            'window_lines': settings.outline_window_lines,
            'overlap_lines': settings.outline_overlap_lines,
            'window_step_lines': max(1, settings.outline_window_lines - settings.outline_overlap_lines),
            'prior_context_limit': OutlineService.continuation_limit,
            'accounting': outline_summary.model_dump() if outline_summary else None,
            # The stage summary remains useful for an in-flight or failed pass, but
            # detailed accounting is only rendered after its durable save.
            'outcome': outline_stage.summary if outline_summary is None else None,
        }
        totals = pipeline.repo.inspection_totals(run_id)
        section_content = {
            'model': settings.typesafe_model,
            'preview_limit': 600,
            'batch_size': settings.section_score_batch_size,
            'keep_threshold': settings.section_score_keep_threshold,
            'uncertain_threshold': settings.section_score_uncertain_threshold,
            'max_selected': settings.section_score_max_selected,
            'max_uncertain': settings.section_score_max_uncertain,
            'inspection': SectionScoringService.inspection_view(
                settings, decisions=totals['decisions']['section_score']),
        }
        chunk_content = {
            'inspection': SourceRangeChunker.inspection_view(
                settings, selected_sections=totals['decisions']['section_score'].get('selected', 0),
                chunks=pipeline.repo.chunks(run_id, page=1, per_page=3),
                totals=totals['chunks']),
        }
        evidence_content = {
            'inspection': ChunkScoringService.inspection_view(
                settings, totals=totals['chunks'],
                decisions=totals['decisions']['chunk_score'],
                summary=pipeline.repo.chunk_score_summary(run_id)),
        }
        findings_content = {
            'inspection': FindingsService.inspection_view(
                settings, summary=pipeline.repo.finding_summary(run_id),
                finding_count=totals['finding_count']),
        }
        finding_results = findings_step_results(
            pipeline.repo, run_id, pipeline.repo.finding_summary(run_id),
            totals['finding_count'])
        for step, result in finding_results.items():
            findings_content['inspection'][step]['run_result'] = result
            findings_content['inspection'][step]['results_url'] = (
                f'/v2/runs/{run_id}/pipeline?stage=findings' if step == 'publish'
                else f'/v2/runs/{run_id}/pipeline/findings/trace')
        facts_content = {
            'inspection': CompanyFactsService.inspection_view(
                settings=settings,
                summary=pipeline.repo.fact_summary(run_id),
                finding_count=totals['finding_count']),
        }
        evaluation_content = {
            'inspection': EvaluationService.inspection_view(
                settings, summary=pipeline.repo.comparison_summary(run_id),
                finding_count=totals['finding_count']),
        }
        for station in ('enrich', 'store'):
            facts_content['inspection'][station]['saved_provenance_url'] = (
                f'/v2/runs/{run_id}/pipeline?stage=facts#fact-source-results')
        evaluation_content['inspection']['record']['saved_provenance_url'] = (
            f'/v2/runs/{run_id}/pipeline?stage=evaluate#evaluation-results')
        stage_cards = [item.model_dump() | {
            'icon': stage_presentation[item.stage][0],
            'label': stage_presentation[item.stage][1],
            'purpose': stage_presentation[item.stage][2],
            'status_symbol': stage_status_presentation[item.status][0],
            'status_label': stage_status_presentation[item.status][1],
            **(source_content if item.stage == 'source' else {}),
            **(outline_content if item.stage == 'outline' else {}),
            **(section_content if item.stage == 'section_score' else {}),
            **(chunk_content if item.stage == 'chunk' else {}),
            **(evidence_content if item.stage == 'chunk_score' else {}),
            **(findings_content if item.stage == 'findings' else {}),
            **(facts_content if item.stage == 'facts' else {}),
            **(evaluation_content if item.stage == 'evaluate' else {}),
        } for item in state['stages']]
        if stage is None:
            active = next((item for item in stage_cards if item['status'] == 'running'), None)
            current = active or next((item for item in stage_cards
                                      if item['stage'] == state['run'].selected_stage), None)
            return {**state, 'report_identity': report_identity, 'overview': True, 'stage_cards': stage_cards,
                    'run_status_symbol': stage_status_presentation[state['run'].status][0],
                    'run_status_label': stage_status_presentation[state['run'].status][1],
                    'map_progress': {
                        'completed': sum(item['status'] == 'completed' for item in stage_cards),
                        'current_label': ('None' if state['run'].status not in ('queued', 'running')
                                          else current['label'] if current else 'Waiting to start'),
                    }}
        selected = next(item for item in stage_cards if item['stage'] == stage)
        page = max(1, page)
        data_stages = {'outline', 'section_score', 'chunk', 'chunk_score', 'findings'}
        outline = pipeline.repo.outline_sections(run_id, page=page) if stage in data_stages else []
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
        result = {**state, 'report_identity': report_identity, 'map_progress': {'completed': sum(item['status'] == 'completed' for item in stage_cards)}, 'overview': False, 'stage_cards': stage_cards, 'selected': selected, 'page': page, 'canonical_refs': canonical_refs,
                  'run_status_label': stage_status_presentation[state['run'].status][1],
                  'outline_sections': outline, 'section_lookup': {x.section_id: x for x in outline},
                  'section_scores': pipeline.repo.scores(run_id, 'section_score', page=page) if stage == 'section_score' else [],
                  'section_actions': [], 'chunks': chunks,
                  'chunk_scores': pipeline.repo.scores(run_id, 'chunk_score', page=page) if stage == 'chunk_score' else [],
                  'chunk_score_summary': pipeline.repo.chunk_score_summary(run_id) if stage == 'chunk_score' else None,
                  'chunk_actions': [], 'findings': findings, 'finding_score_lookup': finding_score_lookup,
                  'finding_summary': pipeline.repo.finding_summary(run_id) if stage == 'findings' else None,
                  'finding_actions': [], 'structured_facts': pipeline.repo.structured_facts(run_id, page=page) if stage in {'facts', 'evaluate'} else [],
                  'fact_summary': pipeline.repo.fact_summary(run_id) if stage == 'facts' else None,
                  'comparisons': pipeline.repo.comparisons(run_id, page=page) if stage == 'evaluate' else [],
                  'comparison_summary': pipeline.repo.comparison_summary(run_id) if stage == 'evaluate' else None,
                  'evaluation_cards': []}
        presentations = pipeline.repo.fact_presentations_for_ids(
            run_id, [item.fact_id for item in result['structured_facts']]) if stage == 'facts' else []
        result['fact_presentations'] = {item.fact_id: presentation_preview(item)
                                      for item in presentations}
        sources = pipeline.repo.fact_sources_for_ids(
            run_id, [item.fact_id for item in result['structured_facts']]) if stage == 'facts' else []
        result['fact_sources'] = {item.fact_id: source_preview(item) for item in sources}
        examples = {}
        for model, items in (
            (CanonicalDocumentRef, canonical_refs), (OutlineSection, outline),
            (TextChunk, chunks), (Finding, findings),
            (ScoredItem, result['section_scores'] or result['chunk_scores']),
            (StructuredFact, result['structured_facts']),
            (FactComparison, result['comparisons']),
        ):
            if items:
                examples[model] = items[0]
        ranged = next((item.primary_range for item in outline), None)
        if ranged is None:
            ranged = next((item.core_range for item in chunks), None)
        if ranged is None:
            ranged = next((item.source_range for item in findings), None)
        if ranged is not None:
            examples[SourceRange] = ranged
        result['contract_envelopes'] = contract_envelopes(stage, examples)
        if stage == 'evaluate':
            # A comparison page is bounded, but its cards need the linked inputs even
            # when the finding or fact sorts onto a different storage page.
            linked_findings = pipeline.repo.findings_for_ids(run_id, [
                finding_id for comparison in result['comparisons']
                for finding_id in comparison.finding_ids])
            all_findings = {item.finding_id: item for item in linked_findings}
            all_facts = {item.fact_id: item for item in pipeline.repo.structured_facts_for_ids(
                run_id, [item.fact_id for item in result['comparisons'] if item.fact_id])}
            result['fact_sources'] = {item.fact_id: source_preview(item) for item in
                pipeline.repo.fact_sources_for_ids(run_id, list(all_facts))}
            result['fact_presentations'] = {item.fact_id: presentation_preview(item) for item in
                pipeline.repo.fact_presentations_for_ids(run_id, list(all_facts))}
            chunks = {item.chunk_id: item for item in pipeline.repo.chunks_for_ids(
                run_id, [item.source_chunk_id for item in linked_findings
                         if item.source_chunk_id])}
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
    def workspace(request: Request, run_id: str, stage: str | None = None, page: int = 1):
        started = monotonic()
        try:
            body = templates.TemplateResponse(request=request, name='v2_workspace.html', context=context(run_id, stage, page))
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, 'V2 run not found') from None
        pipeline.repo.record_route_measurement(run_id, route=f"pipeline:{stage or 'overview'}", latency_ms=(monotonic() - started) * 1000, payload_bytes=len(body.body))
        return body

    @app.get('/v2/runs/{run_id}/pipeline/facts/presentation')
    def fact_presentation_details(request: Request, run_id: str):
        try:
            pipeline.repo.get_run(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None
        return templates.TemplateResponse(request=request, name='v2_fact_presentation.html', context={
            'run_id': run_id, 'actions': pipeline.repo.exploration_actions(run_id, 'facts', limit=100)})

    @app.get('/v2/runs/{run_id}/pipeline/facts/source')
    def fact_source_details(request: Request, run_id: str, fact_id: str, page: int = 1):
        if page < 1:
            raise HTTPException(400, 'Page must be positive')
        try:
            pipeline.repo.get_run(run_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V2 run not found') from None
        mappings = pipeline.repo.fact_sources_for_ids(run_id, [fact_id])
        mapping = mappings[0] if mappings else None
        start = (page - 1) * 20
        return templates.TemplateResponse(request=request, name='v2_fact_source.html', context={
            'run_id': run_id, 'fact_id': fact_id, 'mapping': mapping,
            'locations': mapping.locations[start:start + 20] if mapping else [],
            'page': page, 'has_next': bool(mapping and start + 20 < len(mapping.locations))})

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
            'context_previews': [(r, document.slice(r)[:1200]) for r in item.context_ranges]})

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
