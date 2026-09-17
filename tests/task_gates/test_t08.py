import asyncio
import socket

from fastapi.testclient import TestClient

from profitlab.demo import DemoService
from profitlab.documents.chunk_service import ChunkService
from profitlab.providers.jev import JevResponse
from profitlab.providers.screening import ScreeningService
from profitlab.settings import Settings
from profitlab.web.app import create_app


class ControlledClient:
    def __init__(self, score=0.01, malformed=False, failure=False):
        self.score, self.malformed, self.failure = score, malformed, failure
        self.requests = []

    async def evaluate(self, request):
        self.requests.append(request)
        if self.failure:
            raise ValueError('secret-screen-key echoed in error')
        keys = list(request.questions)[:1] if self.malformed else request.questions
        return JevResponse.model_validate({'model': 'controlled-1',
            'answers': {k: {'type': 'noul', 'noul': self.score} for k in keys},
            'usage': {'input_tokens': 13, 'output_tokens': 5}})


def test_offline_screen_ui_cache_restart_and_unique_coverage(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError('Offline demo attempted network')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    run = DemoService(tmp_path).create('screen-test', 'T08')
    assert run.stage == 'screen' and run.status == 'completed'
    service = ScreeningService(settings)
    index, decisions = service.latest(run.run_id)
    assert {d.decision for d in decisions.values()} == {'keep', 'uncertain', 'drop'}
    overrides = [d for d in decisions.values() if d.structural_override]
    assert overrides and all(max(d.probabilities.values()) < 0.20 for d in overrides)
    assert all(d.synthetic and len(d.probabilities) == 5 for d in decisions.values())
    _, chunks = ChunkService(settings).list(run.run_id)
    retained = [c for c in chunks if decisions[c.chunk_id].decision != 'drop']
    assert index['unique_primary_blocks'] == len({(c.filing_id, b) for c in retained
                                                 for b in c.primary_block_ids})
    assert index['unique_primary_cells'] == len({cid for c in retained for cid in c.primary_cell_ids})
    assert all(all(row['metrics'].values()) for row in index['coverage'].values())
    client = ControlledClient(failure=True)
    asyncio.run(service.screen(run.run_id, client=client))
    assert not client.requests
    index, again = ScreeningService(settings).latest(run.run_id)
    assert index['requests'] == 0 and index['cache_hits'] == len(chunks)
    assert {d.decision_id for d in again.values()} == {d.decision_id for d in decisions.values()}
    with TestClient(create_app(settings)) as web:
        page = web.get('/runs/screen-test/chunks')
        assert page.status_code == 200
        for text in ('Experimental screening', 'Fixture results', 'Structural override', 'uncertain',
                     'comparability', 'unique primary cells'):
            assert text in page.text
        d = overrides[0]
        trace = web.get('/runs/screen-test/trace', params={'q': d.provider_call_id})
        assert trace.status_code == 200 and 'Screen chunk' in trace.text
        assert 'screen · completed' in web.get('/runs/screen-test').text


def test_recovery_failed_unknown_thresholds_and_config_cache(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        screen_recovery_max_chunks=3, typesafe_api_key='secret-screen-key')
    DemoService(tmp_path).create('recover-test', 'T06')
    run, all_chunks = ChunkService(settings).list('recover-test')
    # Controlled input is a genuine saved annual table with its structural tag absent,
    # exercising label recovery rather than the table safeguard.
    chunk = next(c for c in all_chunks if c.table_id and 'Net income' in c.text)
    controlled = chunk.model_copy(update={'table_id': None})
    monkeypatch.setattr(ChunkService, 'list', lambda self, rid:
                        (run.model_copy(update={'mode': 'live'}), [controlled]))
    service = ScreeningService(settings)
    low = ControlledClient()
    asyncio.run(service.screen(run.run_id, client=low))
    index, results = service.latest(run.run_id)
    d = results[chunk.chunk_id]
    assert d.decision == 'uncertain' and d.recovery_for
    assert max(d.probabilities.values()) == 0.01
    assert index['recovery'] and not all(index['coverage_before_recovery'][chunk.filing_id]['metrics'].values())
    assert all(index['coverage'][chunk.filing_id]['metrics'][m] for m in ('income', 'eps'))
    assert len(low.requests) == 1
    request = low.requests[0]
    assert len(request.questions) == 5 and isinstance(request.state, dict)
    assert request.state['metadata']['report_date']
    asyncio.run(service.screen(run.run_id, client=low))
    assert len(low.requests) == 1
    assert service.latest(run.run_id)[1][chunk.chunk_id].alias_uncertainty
    settings.typesafe_model = 'jev-pinned-new'
    high = ControlledClient(score=0.65)
    asyncio.run(service.screen(run.run_id, client=high))
    assert len(high.requests) == 1
    assert service.latest(run.run_id)[1][chunk.chunk_id].decision == 'keep'
    settings.screen_keep_threshold = 0.70
    asyncio.run(service.screen(run.run_id, client=high))
    assert len(high.requests) == 2
    assert service.latest(run.run_id)[1][chunk.chunk_id].decision == 'uncertain'
    # Changing prompt contents invalidates the cache even if the version label is unchanged.
    from profitlab.providers import screening

    prompt = tmp_path / 'prompt.json'
    prompt.write_text(screening.PROMPT.read_text().replace('numeric annual earnings', 'reported annual income'))
    monkeypatch.setattr(screening, 'PROMPT', prompt)
    asyncio.run(service.screen(run.run_id, client=high))
    assert len(high.requests) == 3
    from profitlab.documents.service import SourceService

    original_document = SourceService.document

    def changed_source(self, rid, fid):
        r, doc = original_document(self, rid, fid)
        doc['index']['source_hash'] = 'a' * 64
        return r, doc

    monkeypatch.setattr(SourceService, 'document', changed_source)
    asyncio.run(service.screen(run.run_id, client=high))
    assert len(high.requests) == 4
    settings.typesafe_base_url = 'https://changed.example'
    asyncio.run(service.screen(run.run_id, client=high))
    assert len(high.requests) == 5
    settings.typesafe_model = 'bad-schema'
    bad = ControlledClient(malformed=True)
    asyncio.run(service.screen(run.run_id, client=bad))
    d = service.latest(run.run_id)[1][chunk.chunk_id]
    assert d.decision == 'uncertain' and not d.probabilities and d.error
    assert service.latest(run.run_id)[0]['incomplete']
    asyncio.run(service.screen(run.run_id, client=bad))
    assert len(bad.requests) == 2  # Failed answers are not successful cache entries.
    settings.typesafe_model = 'failed'
    asyncio.run(service.screen(run.run_id, client=ControlledClient(failure=True)))
    d = service.latest(run.run_id)[1][chunk.chunk_id]
    assert d.decision == 'uncertain' and 'secret-screen-key' not in d.error
    assert all(b'secret-screen-key' not in p.read_bytes() for p in tmp_path.rglob('*')
               if p.is_file())


def test_limits_subset_and_uncertain_boundary(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        screen_max_requests=1, screen_recovery_max_chunks=0)
    DemoService(tmp_path).create('limit-test', 'T06')
    service = ScreeningService(settings)
    client = ControlledClient(score=0.20)
    run = asyncio.run(service.screen('limit-test', max_chunks=3, client=client))
    index, decisions = service.latest('limit-test')
    assert run.status == 'partial' and index['incomplete'] and len(client.requests) == 1
    assert all(d.decision != 'drop' for d in decisions.values())
    assert any(d.error for d in decisions.values())
    assert len(decisions) == 3 and index['input_chunks'] > 3
