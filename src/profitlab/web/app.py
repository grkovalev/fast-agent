"""The bounded reader UI for fresh V2 runs."""
import asyncio
import hashlib
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from profitlab.sec.ticker_picker import RandomEligibleTickerPicker
from profitlab.settings import Settings
from profitlab.v2 import STAGE_NAMES, SequentialReportBatchService, V2PipelineService
from profitlab.v2.benchmark import RetrievalBenchmarkService, load_dataset
from profitlab.v2.contracts import SourceRange
from profitlab.v2.evaluation_service import cross_run_scorecard
from profitlab.v2.source_replay import SourceReplayService
from profitlab.v3.campaign_review import CampaignReviewService
from profitlab.v3.contracts import (
    CampaignReview,
    CampaignRun,
    DevelopmentCampaign,
    V3ReportBatch,
    V3ReportBatchItem,
)
from profitlab.v3.repository import V3Repository
from profitlab.v3.service import V3ExplorationIncomplete, V3GraphService

WEB_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)
V3_V2_METRIC_QUESTION = (
    'What exact annual net income or profit, diluted earnings per share, and diluted '
    'weighted-average shares does this filing visibly report?'
)
V3_WORKSPACE_STAGES = (
    ('source', 'Source'), ('explore', 'Explore'), ('evidence_paths', 'Evidence paths'),
    ('findings', 'Findings'), ('ground_truth', 'Ground truth'), ('evaluate', 'Evaluate'),
)


def create_app(settings: Settings | None = None, *, ticker_picker_factory=None,
               benchmark_dataset=None, graph_service_factory=None, v3_ticker_picker_factory=None) -> FastAPI:
    settings = settings or Settings()
    pipeline, tasks, batch_tasks, campaign_tasks, v3_batch_tasks = V2PipelineService(settings), {}, {}, {}, {}
    graph_repo = V3Repository(settings.data_dir)

    def new_graph_service():
        return (graph_service_factory(settings, graph_repo) if graph_service_factory
                else V3GraphService(settings, graph_repo))

    def new_picker():
        return (ticker_picker_factory(pipeline.repo) if ticker_picker_factory
                else RandomEligibleTickerPicker(settings, pipeline.repo))

    def new_v3_picker():
        return (v3_ticker_picker_factory(graph_repo) if v3_ticker_picker_factory
                else RandomEligibleTickerPicker(settings, graph_repo))

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

    async def execute_campaign_run(run: CampaignRun):
        graph_repo.update_campaign_run(run.model_copy(update={'status': 'running', 'started_at': datetime.now(UTC)}))
        try:
            result = await new_graph_service().answer_live_campaign(graph_repo.campaign(run.campaign_id), run.ticker)
        except asyncio.CancelledError:
            raise
        except V3ExplorationIncomplete as error:
            # A partial/exhausted frontier was already persisted by the graph
            # service. It is a truthful terminal experiment, not a worker fault.
            current = graph_repo.campaign_run(run.run_id)
            completed = current.model_copy(update={
                'status': 'sealed', 'experiment_id': error.experiment_id,
                'finished_at': datetime.now(UTC),
                'error': f'Terminal {error.frontier_state} frontier; no answer was synthesized.',
            })
            graph_repo.update_campaign_run(completed)
            return completed
        except Exception as error:  # Persist only a redacted, actionable lifecycle failure.
            logger.exception('V3 campaign worker failed for %s', run.run_id)
            current = graph_repo.campaign_run(run.run_id)
            graph_repo.update_campaign_run(current.model_copy(update={
                'status': 'failed', 'finished_at': datetime.now(UTC),
                'error': settings.redactor().text(str(error)) or error.__class__.__name__,
            }))
            return graph_repo.campaign_run(run.run_id)
        current = graph_repo.campaign_run(run.run_id)
        completed = current.model_copy(update={
            'status': 'sealed', 'experiment_id': result.manifest.experiment_id,
            'finished_at': datetime.now(UTC),
        })
        graph_repo.update_campaign_run(completed)
        return completed

    def start_campaign_run(run: CampaignRun):
        if (task := campaign_tasks.get(run.run_id)) and not task.done():
            raise ValueError('V3 campaign run is already active.')

        async def guarded_run():
            await execute_campaign_run(run)

        campaign_tasks[run.run_id] = asyncio.create_task(guarded_run())

    def start_v3_batch(batch_id: str):
        if (task := v3_batch_tasks.get(batch_id)) and not task.done():
            raise ValueError('V3 batch is already active.')

        async def guarded_batch():
            batch = graph_repo.v3_report_batch(batch_id)
            graph_repo.update_v3_report_batch(batch.model_copy(update={
                'status': 'running', 'summary': 'Selecting and running reports one at a time.',
            }))
            campaign = graph_repo.campaign(batch.campaign_id)
            excluded = {'FGN', 'CRVL', 'SPRO', 'WOR', 'MSFT'}
            for sequence in range(1, batch.requested_count + 1):
                item = V3ReportBatchItem(batch_id=batch_id, sequence=sequence, status='selecting',
                                         created_at=datetime.now(UTC))
                graph_repo.save_v3_report_batch_item(item)
                selection = await asyncio.to_thread(new_v3_picker().pick, exclude_tickers=excluded)
                if not selection.ticker:
                    graph_repo.save_v3_report_batch_item(item.model_copy(update={
                        'status': 'skipped', 'reason': selection.message, 'finished_at': datetime.now(UTC),
                    }))
                    continue
                try:
                    ticker = new_graph_service().validate_campaign_launch(campaign, selection.ticker)
                    run = CampaignRun(run_id='campaign-run-' + uuid4().hex[:16], campaign_id=campaign.campaign_id,
                                      ticker=ticker, status='queued', created_at=datetime.now(UTC))
                    graph_repo.create_campaign_run(run)
                    graph_repo.save_v3_report_batch_item(item.model_copy(update={
                        'ticker': ticker, 'campaign_run_id': run.run_id, 'status': 'running',
                    }))
                    completed = await execute_campaign_run(run)
                    graph_repo.save_v3_report_batch_item(item.model_copy(update={
                        'ticker': ticker, 'campaign_run_id': run.run_id,
                        'status': 'sealed' if completed.status == 'sealed' else 'failed',
                        'reason': completed.error, 'finished_at': datetime.now(UTC),
                    }))
                except ValueError as error:
                    graph_repo.save_v3_report_batch_item(item.model_copy(update={
                        'ticker': selection.ticker, 'status': 'skipped',
                        'reason': settings.redactor().text(str(error)), 'finished_at': datetime.now(UTC),
                    }))
            items = graph_repo.v3_report_batch_items(batch_id)
            sealed = sum(item.status == 'sealed' for item in items)
            graph_repo.update_v3_report_batch(graph_repo.v3_report_batch(batch_id).model_copy(update={
                'status': 'completed', 'finished_at': datetime.now(UTC),
                'summary': f'{sealed} sealed; {len(items) - sealed} failed or skipped. Reports ran sequentially.',
            }))

        v3_batch_tasks[batch_id] = asyncio.create_task(guarded_batch())

    @asynccontextmanager
    async def lifespan(_app):
        pipeline.recover()
        graph_repo.interrupt_active_campaign_runs()
        graph_repo.interrupt_active_v3_batches()
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
        for task in campaign_tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*campaign_tasks.values(), return_exceptions=True)
        for task in v3_batch_tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*v3_batch_tasks.values(), return_exceptions=True)
        graph_repo.interrupt_active_campaign_runs()
        graph_repo.interrupt_active_v3_batches()

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

    def v3_workspace_stages(run: CampaignRun, inspection):
        """Present persisted graph lifecycle truth without inventing later V3 work."""
        pending = 'waiting' if run.status in {'queued', 'running'} else 'unavailable'
        terminal = run.status == 'sealed'
        manifest = inspection['manifest'] if inspection else None
        answer = inspection['answers'][0] if inspection and inspection['answers'] else None
        return [
            {'stage': 'source', 'label': 'Source', 'status': 'available' if inspection else pending,
             'summary': ('Immutable canonical visible filing source is ready.' if inspection else
                         'Filing acquisition has not produced a persisted canonical source yet.')},
            {'stage': 'explore', 'label': 'Explore',
             'status': (manifest.frontier_state if manifest else pending).replace('_', ' '),
             'summary': ('Bounded graph actions are terminal and inspectable.' if terminal else
                         'Bounded source-window exploration is not terminal yet.')},
            {'stage': 'evidence_paths', 'label': 'Evidence paths',
             'status': 'available' if terminal else pending,
             'summary': ('Accepted, uncertain, and rejected graph provenance is available.' if terminal else
                         'Paths become available only after persisted exploration output exists.')},
            {'stage': 'findings', 'label': 'Findings',
             'status': answer.status if answer else ('unresolved' if terminal else pending),
             'summary': ('Only source-cited graph answer claims are shown.' if answer else
                         'No source-cited graph answer claim was persisted; no finding is fabricated.')},
            {'stage': 'ground_truth', 'label': 'Ground truth', 'status': 'not implemented',
             'summary': 'V3-local Company Facts retrieval is a later post-seal slice; it is not available to graph requests.'},
            {'stage': 'evaluate', 'label': 'Evaluate', 'status': 'not implemented',
             'summary': 'Per-report comparison waits for V3-local ground truth and never changes graph findings.'},
        ]

    def v3_development_scorecard(campaign: DevelopmentCampaign):
        """Read-only G6b.3 aggregation for exactly one sealed campaign.

        Reviews and their one-case ledgers are post-seal records.  Keeping this
        assembly in the web boundary prevents a scorecard refresh from becoming
        another graph, SEC, or provider workflow.
        """
        rows = []
        configuration_id = CampaignReviewService._configuration_id(campaign)
        for run in graph_repo.campaign_runs(campaign.campaign_id):
            review = ledger = rubric = None
            disposition, reason = 'excluded', run.error or run.status
            if run.status in {'queued', 'running'}:
                disposition, reason = 'running', run.status
            elif run.status == 'sealed':
                try:
                    review = graph_repo.campaign_review(run.run_id)
                    ledger = graph_repo.development_ledger_report(CampaignReviewService.cohort_id(review))
                    if (ledger.cohort.configuration_id != configuration_id or
                            ledger.cohort.cases[0].experiment_id != run.experiment_id):
                        reason = 'review ledger does not match this sealed campaign configuration'
                    else:
                        rubric, disposition, reason = ledger.cases[0], 'included', 'reviewed post-seal'
                except FileNotFoundError:
                    disposition, reason = 'terminal awaiting review', 'no immutable post-seal review'
            rows.append({'run': run, 'review': review, 'rubric': rubric,
                         'disposition': disposition, 'reason': reason})

        included = [row['rubric'] for row in rows if row['rubric']]
        ground_truth_ranges = sum(len(row['review'].ground_truth_ranges)
                                  for row in rows if row['review'] and row['rubric'])
        covered_ranges = sum(round(row.ground_truth_coverage * len(item['review'].ground_truth_ranges))
                             for item in rows if (row := item['rubric']))
        token_values = [getattr(row, field) for row in included for field in
                        ('provider_input_tokens', 'provider_output_tokens')]
        summary = {
            'all_campaign_cases': len(rows),
            'included_reviewed_cases': len(included),
            'reviewed_ground_truth_coverage': f'{covered_ranges} / {ground_truth_ranges}' if ground_truth_ranges else 'unavailable',
            'exact_citation_valid_cases': f"{sum(row.exact_citations_valid for row in included)} / {len(included)}" if included else 'unavailable',
            'provider_calls': sum(row.provider_calls for row in included),
            'provider_tokens': sum(token_values) if token_values and all(value is not None for value in token_values) else 'unavailable',
            'latency_seconds': sum(row.latency_seconds for row in included)
                if included and all(row.latency_seconds is not None for row in included) else 'unavailable',
        }
        return {'campaign': campaign, 'configuration_id': configuration_id, 'rows': rows,
                'summary': summary,
                'support_counts': {key: sum(row.answer_support == key for row in included)
                                   for key in ('supported', 'partial', 'unsupported', 'unresolved')},
                'ambiguity_counts': {key: sum(row.ambiguity_handling == key for row in included)
                                     for key in ('handled', 'disclosed', 'forced', 'not_applicable')},
                'frontier_counts': {key: sum(row.terminal_frontier_state == key for row in included)
                                    for key in ('answered', 'partial', 'exhausted', 'budget_exhausted')},
                'action_count': sum(row.action_count for row in included),
                'continuation_count': sum(row.continuation_count for row in included)}

    def fixed_metric_campaign():
        """Server-owned campaign for the sole V2-comparison experiment question."""
        service = new_graph_service()
        configuration = service.campaign_configuration()
        for campaign in graph_repo.campaigns():
            if campaign.question == V3_V2_METRIC_QUESTION and campaign.configuration == configuration:
                return campaign
        identity = json.dumps({'question': V3_V2_METRIC_QUESTION,
                               'configuration': configuration.model_dump(mode='json')}, sort_keys=True)
        campaign = DevelopmentCampaign(
            campaign_id='campaign-' + hashlib.sha256(identity.encode()).hexdigest()[:16],
            question=V3_V2_METRIC_QUESTION, configuration=configuration, created_at=datetime.now(UTC))
        try:
            graph_repo.save_campaign(campaign)
        except sqlite3.IntegrityError:  # A second local request may have persisted the same identity.
            return graph_repo.campaign(campaign.campaign_id)
        return campaign

    @app.get('/v3/experiments')
    def graph_experiments(request: Request):
        return templates.TemplateResponse(request=request, name='v3_experiments.html', context={
            'experiments': graph_repo.experiments(),
            'campaigns': graph_repo.campaigns(),
            'campaign_runs': graph_repo.campaign_runs(),
            'rubric_reports': graph_repo.rubric_reports(),
            'development_ledger_reports': graph_repo.development_ledger_reports(),
            'fixed_question': V3_V2_METRIC_QUESTION,
            'batches': graph_repo.v3_report_batches(), 'batch_maximum': settings.random_batch_max_reports,
        })

    def v3_reports_context(**extra):
        return {
            'experiments': graph_repo.experiments(), 'campaigns': graph_repo.campaigns(),
            'campaign_runs': graph_repo.campaign_runs(), 'rubric_reports': graph_repo.rubric_reports(),
            'development_ledger_reports': graph_repo.development_ledger_reports(),
            'fixed_question': V3_V2_METRIC_QUESTION, 'batches': graph_repo.v3_report_batches(),
            'batch_maximum': settings.random_batch_max_reports, **extra,
        }

    @app.post('/v3/reports')
    async def launch_fixed_metric_report(request: Request):
        from urllib.parse import parse_qs

        fields = parse_qs((await request.body()).decode())
        try:
            campaign = fixed_metric_campaign()
            ticker = new_graph_service().validate_campaign_launch(campaign, fields.get('ticker', [''])[0])
            run = CampaignRun(run_id='campaign-run-' + uuid4().hex[:16], campaign_id=campaign.campaign_id,
                              ticker=ticker, status='queued', created_at=datetime.now(UTC))
            graph_repo.create_campaign_run(run)
            start_campaign_run(run)
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='v3_experiments.html', status_code=400,
                                              context=v3_reports_context(error=settings.redactor().text(str(error))))
        return RedirectResponse(f'/v3/campaign-runs/{run.run_id}', status_code=303)

    @app.post('/v3/ticker-picker')
    async def pick_v3_ticker(request: Request):
        selection = await asyncio.to_thread(new_v3_picker().pick,
                                            exclude_tickers={'FGN', 'CRVL', 'SPRO', 'WOR', 'MSFT'})
        if not selection.ticker:
            return templates.TemplateResponse(request=request, name='v3_experiments.html', status_code=503,
                                              context=v3_reports_context(error=selection.message))
        try:
            campaign = fixed_metric_campaign()
            ticker = new_graph_service().validate_campaign_launch(campaign, selection.ticker)
            run = CampaignRun(run_id='campaign-run-' + uuid4().hex[:16], campaign_id=campaign.campaign_id,
                              ticker=ticker, status='queued', created_at=datetime.now(UTC))
            graph_repo.create_campaign_run(run)
            start_campaign_run(run)
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='v3_experiments.html', status_code=400,
                                              context=v3_reports_context(error=settings.redactor().text(str(error))))
        return RedirectResponse(f'/v3/campaign-runs/{run.run_id}', status_code=303)

    @app.post('/v3/batches')
    async def create_v3_batch(request: Request):
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode())
        try:
            count = int(fields.get('count', [''])[0])
            if not 1 <= count <= settings.random_batch_max_reports:
                raise ValueError(f'Choose between 1 and {settings.random_batch_max_reports} reports.')
            campaign = fixed_metric_campaign()
            batch = V3ReportBatch(batch_id='v3-batch-' + uuid4().hex[:16], campaign_id=campaign.campaign_id,
                                  requested_count=count, status='queued', summary='Queued for sequential V3 selection.',
                                  created_at=datetime.now(UTC))
            graph_repo.create_v3_report_batch(batch)
            start_v3_batch(batch.batch_id)
        except (TypeError, ValueError) as error:
            return templates.TemplateResponse(request=request, name='v3_experiments.html', status_code=400,
                                              context=v3_reports_context(error=settings.redactor().text(str(error))))
        return RedirectResponse(f'/v3/batches/{batch.batch_id}', status_code=303)

    @app.get('/v3/batches/{batch_id}')
    def v3_batch_detail(request: Request, batch_id: str):
        try:
            batch = graph_repo.v3_report_batch(batch_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 batch not found') from None
        return templates.TemplateResponse(request=request, name='v3_batch.html', context={
            'batch': batch, 'items': graph_repo.v3_report_batch_items(batch_id),
        })

    @app.post('/v3/campaigns')
    async def create_campaign(request: Request):
        from urllib.parse import parse_qs

        fields = parse_qs((await request.body()).decode())
        question = fields.get('question', [''])[0].strip()
        try:
            if not question:
                raise ValueError('A campaign question is required.')
            service = new_graph_service()
            campaign = DevelopmentCampaign(campaign_id='campaign-' + uuid4().hex[:16], question=question,
                                            configuration=service.campaign_configuration(), created_at=datetime.now(UTC))
            graph_repo.save_campaign(campaign)
        except ValueError as error:
            return templates.TemplateResponse(request=request, name='v3_experiments.html', status_code=400, context={
                'experiments': graph_repo.experiments(), 'campaigns': graph_repo.campaigns(),
                'campaign_runs': graph_repo.campaign_runs(), 'rubric_reports': graph_repo.rubric_reports(),
                'development_ledger_reports': graph_repo.development_ledger_reports(),
                'error': settings.redactor().text(str(error)),
            })
        return RedirectResponse(f'/v3/campaigns/{campaign.campaign_id}', status_code=303)

    @app.get('/v3/campaigns/{campaign_id}')
    def campaign_workspace(request: Request, campaign_id: str):
        try:
            campaign = graph_repo.campaign(campaign_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 campaign not found') from None
        return templates.TemplateResponse(request=request, name='v3_campaign.html', context={
            'campaign': campaign, 'runs': graph_repo.campaign_runs(campaign_id), 'readiness': settings.readiness(),
        })

    @app.get('/v3/campaigns/{campaign_id}/development-scorecard')
    def campaign_development_scorecard(request: Request, campaign_id: str):
        try:
            campaign = graph_repo.campaign(campaign_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 campaign not found') from None
        return templates.TemplateResponse(request=request, name='v3_development_scorecard.html',
                                          context=v3_development_scorecard(campaign))

    @app.post('/v3/campaigns/{campaign_id}/runs')
    async def launch_campaign_run(request: Request, campaign_id: str):
        from urllib.parse import parse_qs

        fields = parse_qs((await request.body()).decode())
        try:
            campaign = graph_repo.campaign(campaign_id)
            ticker = new_graph_service().validate_campaign_launch(campaign, fields.get('ticker', [''])[0])
            run = CampaignRun(run_id='campaign-run-' + uuid4().hex[:16], campaign_id=campaign_id, ticker=ticker,
                              status='queued', created_at=datetime.now(UTC))
            graph_repo.create_campaign_run(run)
            start_campaign_run(run)
        except (FileNotFoundError, ValueError) as error:
            if isinstance(error, FileNotFoundError):
                raise HTTPException(404, 'V3 campaign not found') from None
            campaign = graph_repo.campaign(campaign_id)
            return templates.TemplateResponse(request=request, name='v3_campaign.html', status_code=400, context={
                'campaign': campaign, 'runs': graph_repo.campaign_runs(campaign_id), 'readiness': settings.readiness(),
                'error': settings.redactor().text(str(error)),
            })
        return RedirectResponse(f'/v3/campaign-runs/{run.run_id}', status_code=303)

    @app.get('/v3/campaign-runs/{run_id}')
    def campaign_run(request: Request, run_id: str, stage: str | None = None):
        try:
            run = graph_repo.campaign_run(run_id)
            campaign = graph_repo.campaign(run.campaign_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 campaign run not found') from None
        try:
            review = graph_repo.campaign_review(run_id)
            review_report = graph_repo.development_ledger_report(CampaignReviewService.cohort_id(review))
        except FileNotFoundError:
            review, review_report = None, None
        try:
            inspection = graph_context(run.experiment_id) if run.experiment_id else None
        except FileNotFoundError:
            inspection = None
        stages = v3_workspace_stages(run, inspection)
        selected_stage = stage if stage in {item['stage'] for item in stages} else 'source'
        selected = next(item for item in stages if item['stage'] == selected_stage)
        return templates.TemplateResponse(request=request, name='v3_campaign_run.html', context={
            'run': run, 'campaign': campaign, 'review': review, 'review_report': review_report,
            'show_review_form': False, 'stages': stages, 'selected': selected,
            'inspection': inspection,
        })

    @app.get('/v3/campaign-runs/{run_id}/review')
    def campaign_review_form(request: Request, run_id: str):
        try:
            run = graph_repo.campaign_run(run_id)
            campaign = graph_repo.campaign(run.campaign_id)
        except FileNotFoundError:
            raise HTTPException(404, 'V3 campaign run not found') from None
        try:
            inspection = graph_context(run.experiment_id) if run.experiment_id else None
        except FileNotFoundError:
            inspection = None
        stages = v3_workspace_stages(run, inspection)
        return templates.TemplateResponse(request=request, name='v3_campaign_run.html', context={
            'run': run, 'campaign': campaign, 'review': None, 'review_report': None,
            'show_review_form': True, 'stages': stages, 'selected': stages[0], 'inspection': inspection,
        })

    @app.post('/v3/campaign-runs/{run_id}/review')
    async def review_campaign_run(request: Request, run_id: str):
        from urllib.parse import parse_qs

        fields = parse_qs((await request.body()).decode())
        try:
            run = graph_repo.campaign_run(run_id)
            campaign = graph_repo.campaign(run.campaign_id)
            inspection = graph_repo.inspection(run.experiment_id) if run.experiment_id else None
            if not inspection:
                raise ValueError('A sealed experiment is required before review.')
            document = inspection['document']
            start, end = int(fields.get('start_line', [''])[0]), int(fields.get('end_line', [''])[0])
            source = SourceRange(
                document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                start_line=start, end_line=end)
            review = CampaignReview(review_id='campaign-review-' + uuid4().hex[:16], campaign_id=campaign.campaign_id,
                campaign_run_id=run_id, experiment_id=run.experiment_id, question=campaign.question,
                ground_truth_ranges=[source], answer_support=fields.get('answer_support', [''])[0],
                ambiguity_handling=fields.get('ambiguity_handling', [''])[0],
                notes=fields.get('notes', [None])[0] or None, created_at=datetime.now(UTC))
            report = CampaignReviewService.submit(review, graph_repo)
        except (FileNotFoundError, ValueError) as error:
            if isinstance(error, FileNotFoundError):
                raise HTTPException(404, 'V3 campaign run not found') from None
            run = graph_repo.campaign_run(run_id)
            campaign = graph_repo.campaign(run.campaign_id)
            try:
                inspection = graph_context(run.experiment_id) if run.experiment_id else None
            except FileNotFoundError:
                inspection = None
            stages = v3_workspace_stages(run, inspection)
            return templates.TemplateResponse(request=request, name='v3_campaign_run.html', status_code=400, context={
                'run': run, 'campaign': campaign, 'review': None, 'review_report': None,
                'show_review_form': True, 'stages': stages, 'selected': stages[0], 'inspection': inspection,
                'error': settings.redactor().text(str(error)),
            })
        return RedirectResponse(f'/v3/development-ledgers/{report.cohort.cohort_id}', status_code=303)

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
