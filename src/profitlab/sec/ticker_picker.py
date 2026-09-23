"""Bounded, auditable selection of a live-SEC eligible ticker."""
import hashlib
import random
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from profitlab.sec.client import SECClient, SECError
from profitlab.sec.service import DiscoveryService, normalize_ticker


@dataclass(frozen=True)
class TickerSelection:
    ticker: str | None
    selected_at: datetime
    directory_provenance: str
    directory_version: str
    cache_status: str
    eligibility: str
    message: str


class _PickerTrace:
    def __init__(self, redactor):
        self.redact = redactor
        self.operations = []

    @contextmanager
    def operation(self, name, _request, **_metadata):
        output = {}
        yield output
        self.operations.append((name, output))


class RandomEligibleTickerPicker:
    def __init__(self, settings, repository, *, chooser=None, client_factory=None,
                 discovery_service=None):
        self.settings, self.repo = settings, repository
        self.chooser = chooser or random.choice
        self.client_factory = client_factory
        self.discovery_service = discovery_service or DiscoveryService(settings)

    @staticmethod
    def _directory_version(mapping):
        rows = sorted((normalize_ticker(entry.ticker), str(entry.cik_str), entry.title)
                      for entry in mapping.values())
        return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]

    def _audit(self, selection):
        self.repo.record_ticker_selection(selection)
        return selection

    def pick(self):
        selected_at = datetime.now(UTC)
        if not self.settings.sec_contact_ready():
            return self._audit(TickerSelection(None, selected_at, 'SEC company_tickers.json',
                'unavailable', 'unavailable', 'unavailable',
                'Configure SEC_USER_AGENT with a real contact email before selecting a live ticker.'))
        trace = _PickerTrace(self.settings.redactor())
        client = self.client_factory(trace) if self.client_factory else SECClient(self.settings, trace)
        try:
            try:
                mapping = client.tickers()
            except SECError as error:
                return self._audit(TickerSelection(None, selected_at, 'SEC company_tickers.json',
                    'unavailable', 'unavailable', 'unavailable',
                    f'Could not load the SEC ticker directory: {error}. Check SEC contact and connectivity.'))
            cache_status = 'hit' if any(name == 'SEC cache hit' for name, _ in trace.operations) else 'miss'
            try:
                candidates = sorted({normalize_ticker(entry.ticker) for entry in mapping.values()})
                directory_version = self._directory_version(mapping)
            except ValueError:
                return self._audit(TickerSelection(None, selected_at, 'SEC company_tickers.json',
                    'invalid', cache_status, 'unavailable',
                    'The SEC ticker directory contained an invalid ticker; try again after its cache refreshes.'))
            unseen = [ticker for ticker in candidates if ticker not in self.repo.processed_tickers()]
            candidates = unseen or candidates
            for _ in range(min(self.settings.random_ticker_attempts, len(candidates))):
                ticker = self.chooser(candidates)
                candidates.remove(ticker)
                try:
                    result = self.discovery_service.discover(client, ticker, years=1, synthetic=False)
                except SECError:
                    continue
                if result.outcome == 'found' and any(filing.form == '10-K' for filing in result.filings):
                    return self._audit(TickerSelection(ticker, selected_at, 'SEC company_tickers.json',
                        directory_version, cache_status, 'eligible',
                        'Eligible recent 10-K confirmed; create the run when ready.'))
            return self._audit(TickerSelection(None, selected_at, 'SEC company_tickers.json',
                directory_version, cache_status, 'exhausted',
                'No eligible 10-K ticker was found within the bounded retry limit. Keep your manual ticker or try again.'))
        finally:
            client.close()
