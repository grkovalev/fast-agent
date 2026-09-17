"""Ticker resolution and annual-period selection independent of CLI/web handlers."""
import re
import threading
from datetime import UTC, date, datetime
from urllib.parse import quote
from uuid import uuid4

from profitlab.contracts.base import CompanyIdentity, RunManifest
from profitlab.contracts.sources import FilingRecord
from profitlab.sec.client import SECClient, SECError
from profitlab.sec.contracts import DiscoveryResult
from profitlab.sec.fixtures import FixtureLimiter, fixture_transport
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder

_live_lock = threading.Lock()


def normalize_ticker(ticker):
    # SEC class symbols use hyphens; accept a dot as the sole punctuation alias.
    value = ticker.strip().upper().replace('.', '-')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,19}', value):
        raise ValueError('Ticker must contain 1–20 letters/digits and optional class hyphen.')
    return value


def select_filings(rows, cik, years, synthetic=False):
    records = {}
    for row in rows:
        if row['form'] not in ('10-K', '10-K/A'):
            continue
        accession = row['accessionNumber']
        document = row['primaryDocument']
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) or not re.fullmatch(
                r'[A-Za-z0-9_.-]+', document) or document in ('.', '..'):
            raise SECError('invalid_response', 'Invalid SEC accession or document name.')
        identifier = 'filing-' + accession.replace('-', '')
        try:
            record = FilingRecord(
                filing_id=identifier, cik=cik, accession=accession, form=row['form'],
                report_date=row['reportDate'], filing_date=row['filingDate'],
                primary_document_url=(f'synthetic:{document}' if synthetic else
                    f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/'
                    f'{accession.replace("-", "")}/{quote(document)}'))
        except ValueError:
            raise SECError('invalid_response', 'Invalid dates/identity in annual filing.') from None
        if identifier in records and records[identifier] != record:
            raise SECError('invalid_response', 'Conflicting metadata for one SEC accession.')
        records[identifier] = record
    originals = {}
    for record in sorted(records.values(), key=lambda r: (r.filing_date, r.accession)):
        if record.form == '10-K':
            originals.setdefault(record.report_date, record)
    periods = sorted(originals, reverse=True)[:years]
    selected = [originals[period] for period in periods]
    for record in sorted(records.values(), key=lambda r: (r.filing_date, r.accession)):
        if record.form == '10-K/A' and record.report_date in periods:
            selected.append(record.model_copy(update={
                'amendment_of': originals[record.report_date].filing_id}))
    return selected, periods


class DiscoveryService:
    def __init__(self, settings, *, transport=None, limiter=None):
        self.settings, self.transport, self.limiter = settings, transport, limiter

    def create(self, ticker, years=4, mode='live', run_id=None, scenario='normal'):
        ticker = normalize_ticker(ticker)
        if years not in range(1, 5) or mode not in ('demo', 'live'):
            raise ValueError('Use 1–4 years and mode demo or live.')
        if scenario not in ('normal', 'two-years', 'conflict', 'restatement', 'split-adjusted', 'losses'):
            raise ValueError('Supported scenarios: normal, two-years, conflict, restatement, split-adjusted, losses.')
        if mode == 'live' and not self.settings.sec_contact_ready():
            raise ValueError('Configure SEC_USER_AGENT with a real contact email before live discovery.')
        if mode == 'live' and not _live_lock.acquire(blocking=False):
            raise ValueError('A live discovery is already active; wait before starting another.')
        try:
            return self._create(ticker, years, mode, run_id, scenario)
        finally:
            if mode == 'live':
                _live_lock.release()

    def _create(self, ticker, years, mode, run_id, scenario):
        now = datetime.now(UTC)
        run_id = run_id or 'discover-' + uuid4().hex[:12]
        initial = RunManifest(run_id=run_id, ticker=ticker, mode=mode, created_at=now,
                              updated_at=now, requested_years=years, stage='lookup',
                              status='running', configuration={'through': 'T04',
                              'scenario': scenario}, limitation='Discovery only; no financial extraction.')
        repo = Repository(self.settings.data_dir)
        repo.create_run(initial)
        repo.put(run_id, 'summary', initial.model_dump_json().encode())
        trace = TraceRecorder(repo, run_id, self.settings.redactor())
        client = SECClient(self.settings, trace, transport=self.transport or (
            fixture_transport(scenario, ticker) if mode == 'demo' else None),
            fixture=mode == 'demo', limiter=self.limiter or (
                FixtureLimiter() if mode == 'demo' else None))
        # Fixture timeouts remain instantaneous and deterministic.
        if mode == 'demo':
            client.settings = self.settings.model_copy(update={'sec_retries': 0})
        try:
            result = self.discover(client, ticker, years, synthetic=mode == 'demo')
        except SECError as error:
            result = DiscoveryResult(outcome='service_error', ticker=ticker,
                error_code=error.code, message=self.settings.redactor().text(str(error)),
                history_complete=False)
        finally:
            client.close()
        # The typed result is persisted independently of trace payloads, so it must
        # pass through the same redactor (including successful echoed responses).
        try:
            result = DiscoveryResult.model_validate(trace.redact(result))
        except ValueError:
            result = DiscoveryResult(outcome='service_error', ticker=ticker,
                error_code='redaction_validation', history_complete=False,
                message='SEC response cannot be safely persisted with valid identifiers.')
        # Originals precede amendments so repository-boundary references validate.
        for filing in result.filings:
            repo.save_contract(run_id, filing.filing_id, filing)
        repo.save_contract(run_id, 'discovery', result)
        status = 'completed' if result.outcome == 'found' else 'failed'
        if result.outcome == 'found' and len(result.report_periods) < years:
            status = 'partial'
        final = initial.model_copy(update={'company': result.company,
            'covered_years': sorted({period.year for period in result.report_periods}),
            'status': status, 'stage': 'discover', 'updated_at': datetime.now(UTC),
            'artifact_ids': ['discovery'] + [r.filing_id for r in result.filings],
            'limitation': result.message + ' This run stopped at discovery; financial extraction has not run.'})
        repo.save_contract(run_id, 'manifest-discovery', final)
        return final

    def discover(self, client, ticker, years, synthetic=False):
        with client.trace.operation('Resolve ticker', {'ticker': ticker}, stage='lookup') as output:
            mapping = client.tickers()
            if not mapping:
                raise SECError('invalid_response', 'SEC ticker mapping is empty.')
            try:
                matches = [entry for entry in mapping.values()
                           if normalize_ticker(entry.ticker) == ticker]
            except ValueError:
                raise SECError('invalid_response', 'Invalid ticker in SEC mapping.') from None
            identities = {entry.cik_str for entry in matches}
            if not matches:
                result = DiscoveryResult(outcome='not_found', ticker=ticker,
                                         message=('Ticker not found in the synthetic fixture mapping. Use DEMO for synthetic data or select Live SEC for real tickers such as MSFT.' if synthetic else 'Ticker not found in SEC mapping.'))
                output.update(result.model_dump(mode='json'))
                return result
            if len(identities) > 1:
                result = DiscoveryResult(outcome='ambiguous', ticker=ticker,
                                         message='Ticker maps to multiple companies; no silent choice.')
                output.update(result.model_dump(mode='json'))
                return result
            entry = matches[0]
            cik = f'{entry.cik_str:010d}'
            company = CompanyIdentity(ticker=ticker, cik=cik, name=entry.title,
                lookup_source='synthetic fixture' if synthetic else 'SEC company_tickers.json',
                lookup_at=datetime.now(UTC), other_tickers=sorted({e.ticker for e in
                    mapping.values() if e.cik_str == entry.cik_str and e.ticker != entry.ticker}))
            output['company'] = company.model_dump(mode='json')
        with client.trace.operation('Discover annual filings', {'cik': cik, 'years': years},
                                    stage='discover') as output:
            submissions = client.submissions(cik)
            if submissions.cik != int(cik):
                raise SECError('invalid_response', 'SEC submissions CIK does not match company.')
            rows = submissions.filings.recent.rows()
            visited = set()
            for history in sorted(submissions.filings.files,
                                  key=lambda f: f.filingTo or date.max, reverse=True):
                _, periods = select_filings(rows, cik, years, synthetic)
                if len(periods) == years and history.filingTo and history.filingTo < min(periods):
                    continue  # Cannot contain an original or amendment for a selected period.
                if history.name in visited:
                    continue
                if not history.name.startswith(f'CIK{cik}-'):
                    raise SECError('invalid_response', 'SEC history file belongs to another CIK.')
                if len(visited) >= self.settings.sec_max_history_files:
                    raise SECError('history_limit', 'SEC history limit reached; coverage is incomplete.')
                visited.add(history.name)
                rows.extend(client.history(history.name).rows())
            filings, periods = select_filings(rows, cik, years, synthetic)
            result = DiscoveryResult(outcome='found' if periods else 'unsupported',
                ticker=ticker, company=company, filings=filings, report_periods=periods,
                message=(f'{len(periods)} of {years} requested annual report periods available.'
                         if periods else 'Company has no supported 10-K annual reports.'))
            output.update(result.model_dump(mode='json'))
            return result
