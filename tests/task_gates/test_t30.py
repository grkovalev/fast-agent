"""T30 keeps random live-ticker selection bounded, auditable, and separate from runs."""
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from profitlab.sec.contracts import TickerEntry
from profitlab.sec.ticker_picker import RandomEligibleTickerPicker, TickerSelection
from profitlab.settings import Settings
from profitlab.v2.contracts import V2Run
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


class FakeClient:
    def __init__(self, mapping):
        self.mapping = mapping
        self.closed = False

    def tickers(self):
        return self.mapping

    def close(self):
        self.closed = True


class FakeDiscovery:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def discover(self, _client, ticker, years, synthetic):
        self.calls.append((ticker, years, synthetic))
        return self.outcomes[ticker]


def result(outcome, forms=()):
    return SimpleNamespace(outcome=outcome,
                           filings=[SimpleNamespace(form=form) for form in forms])


def picker(tmp_path, mapping, outcomes, choices, attempts=5):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_user_agent='tester@example.org',
                        random_ticker_attempts=attempts, _env_file=None)
    client = FakeClient(mapping)
    discovery = FakeDiscovery(outcomes)
    service = RandomEligibleTickerPicker(
        settings, V2Repository(tmp_path), chooser=lambda candidates: choices.pop(0),
        client_factory=lambda _trace: client, discovery_service=discovery)
    return service, client, discovery


def test_picker_deduplicates_candidates_retries_and_records_only_selection(tmp_path):
    mapping = {
        'a': TickerEntry(cik_str=1, ticker='NOPE', title='No filing'),
        'b': TickerEntry(cik_str=1, ticker='NOPE', title='No filing duplicate'),
        'c': TickerEntry(cik_str=2, ticker='GOOD', title='Eligible'),
    }
    service, client, discovery = picker(tmp_path, mapping, {
        'NOPE': result('unsupported'), 'GOOD': result('found', ('10-K',)),
    }, ['NOPE', 'GOOD'])

    selection = service.pick()

    assert selection.ticker == 'GOOD' and selection.eligibility == 'eligible'
    assert discovery.calls == [('NOPE', 1, False), ('GOOD', 1, False)]
    assert client.closed
    with V2Repository(tmp_path).connect() as db:
        row = db.execute('SELECT ticker, eligibility, directory_version FROM ticker_selections').fetchone()
        assert tuple(row)[:2] == ('GOOD', 'eligible') and len(row['directory_version']) == 16


def test_picker_exhaustion_shows_an_error_and_creates_no_run(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    selection = TickerSelection(None, datetime.now(UTC), 'SEC company_tickers.json', 'unavailable',
                                'unavailable', 'unavailable', 'Configure SEC_USER_AGENT first.')

    class UnavailablePicker:
        def pick(self):
            return selection

    with TestClient(create_app(settings, ticker_picker_factory=lambda _repo: UnavailablePicker())) as client:
        response = client.post('/v2/ticker-picker', data={'ticker': 'MANUAL'})
        home = client.get('/')

    assert response.status_code == 503
    assert 'Configure SEC_USER_AGENT first.' in response.text
    assert 'Source mode' not in response.text
    assert 'name="mode" value="live"' in response.text
    assert 'No V2 runs yet.' in home.text


def test_picker_control_starts_a_live_run_without_rendering_audit_details(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    selection = TickerSelection('GOOD', datetime.now(UTC), 'SEC company_tickers.json', 'directory-v1',
                                'hit', 'eligible', 'Eligible recent 10-K confirmed; create the run when ready.')

    class EligiblePicker:
        def pick(self):
            return selection

    with TestClient(create_app(settings, ticker_picker_factory=lambda _repo: EligiblePicker())) as client:
        response = client.post('/v2/ticker-picker', data={'ticker': 'MANUAL'}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers['location'].startswith('/v2/runs/')
    assert 'Random selection audit' not in response.text


def test_picker_bounds_ineligible_attempts(tmp_path):
    mapping = {'a': TickerEntry(cik_str=1, ticker='ONE', title='One'),
               'b': TickerEntry(cik_str=2, ticker='TWO', title='Two')}
    service, _client, discovery = picker(tmp_path, mapping, {
        'ONE': result('unsupported'), 'TWO': result('not_found'),
    }, ['ONE', 'TWO'], attempts=2)

    selection = service.pick()

    assert selection.ticker is None and selection.eligibility == 'exhausted'
    assert [call[0] for call in discovery.calls] == ['ONE', 'TWO']


def test_picker_prefers_a_ticker_not_already_processed(tmp_path):
    mapping = {'a': TickerEntry(cik_str=1, ticker='OLD', title='Old'),
               'b': TickerEntry(cik_str=2, ticker='NEW', title='New')}
    service, _client, discovery = picker(tmp_path, mapping, {
        'OLD': result('found', ('10-K',)), 'NEW': result('found', ('10-K',)),
    }, ['NEW'])
    service.repo.create_run(V2Run(
        run_id='old-run', ticker='OLD', mode='live', status='queued', selected_stage='source',
        cancellation_requested=False, created_at=datetime.now(UTC), updated_at=datetime.now(UTC), summary='old'))

    selection = service.pick()

    assert selection.ticker == 'NEW'
    assert [call[0] for call in discovery.calls] == ['NEW']
