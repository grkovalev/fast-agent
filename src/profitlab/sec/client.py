"""Bounded SEC JSON requests, shared disk limiter, validated cache and traced retries."""
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import TypeAdapter

from profitlab.sec.contracts import FilingArrays, Submissions, TickerEntry

TICKERS = 'https://www.sec.gov/files/company_tickers.json'
SUBMISSIONS = 'https://data.sec.gov/submissions/'
COMPANY_FACTS = 'https://data.sec.gov/api/xbrl/companyfacts/'


class SECError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class RateLimiter:
    """Every live attempt shares this lock across threads and local processes."""
    def __init__(self, path: Path, rate: float):
        self.path, self.interval = path, 1 / rate

    def wait(self, deadline):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            last = float(stream.read() or '0')
            delay = max(0, last + self.interval - time.time())
            if time.monotonic() + delay >= deadline:
                raise SECError('time_limit', 'SEC discovery time limit reached.')
            time.sleep(delay)
            stream.seek(0)
            stream.truncate()
            stream.write(str(time.time()))
            stream.flush()


def retry_after(value):
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


class SECClient:
    def __init__(self, settings, trace, *, transport=None, fixture=False, limiter=None):
        self.settings, self.trace, self.fixture = settings, trace, fixture
        self.cache = settings.data_dir / 'sec-cache'
        self.limiter = limiter or RateLimiter(
            settings.data_dir / 'sec-rate.lock', settings.sec_requests_per_second)
        self.deadline = time.monotonic() + settings.sec_total_timeout
        self.client = httpx.Client(
            transport=transport, timeout=settings.sec_timeout, follow_redirects=False,
            headers={'User-Agent': settings.sec_user_agent, 'Accept': 'application/json'})

    def close(self):
        self.client.close()

    def get(self, url, schema, *, stage, document=False, statement_archive=False):
        if statement_archive:
            if not re.fullmatch(r'https://www\.sec\.gov/files/dera/data/financial-statement-data-sets/\d{4}q[1-4]\.zip', url):
                raise SECError('invalid_url', 'Only official SEC statement archives are allowed.')
        elif document:
            if not re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]{18}/[A-Za-z0-9_.-]+', url):
                raise SECError('invalid_url', 'Only verified SEC archive URLs are allowed.')
        elif url != TICKERS and not url.startswith(SUBMISSIONS) and not re.fullmatch(
                r'https://data\.sec\.gov/api/xbrl/companyfacts/CIK\d{10}\.json', url) and not re.fullmatch(
                r'https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]{18}/index\.json', url):
            raise SECError('invalid_url', 'Only official SEC discovery URLs are allowed.')
        adapter = TypeAdapter(schema)
        call = 'call-' + uuid4().hex
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f'{key}.json'
        if not document and not statement_archive and not self.fixture and path.exists():
            try:
                cached = json.loads(path.read_bytes())
                if cached['url'] == url and time.time() - cached['retrieved_at'] < (
                        86400 if url == TICKERS else 3600):
                    raw = cached['response']
                    content = json.dumps(raw, sort_keys=True).encode()
                    if hashlib.sha256(content).hexdigest() != cached['sha256']:
                        raise ValueError('Cache hash mismatch')
                    value = adapter.validate_python(raw)
                    with self.trace.operation('SEC cache hit', {'url': url}, stage=stage,
                                              provider='sec', call_id=call) as output:
                        output.update(cache_status='hit', response=raw, metadata=cached)
                    return value
            except (ValueError, KeyError, OSError):
                pass  # Invalid cache never becomes a successful or not-found result.
        for attempt in range(1, self.settings.sec_retries + 2):
            delay = min(2 ** (attempt - 1), 8)
            try:
                with self.trace.operation('SEC JSON request', {'url': url, 'cache_status': 'miss',
                        'headers': dict(self.client.headers)}, provider='synthetic-sec' if
                        self.fixture else 'sec', stage=stage, attempt=attempt, call_id=call) as out:
                    if time.monotonic() >= self.deadline:
                        raise SECError('time_limit', 'SEC discovery time limit reached.')
                    self.limiter.wait(self.deadline)
                    accept = 'application/zip' if statement_archive else 'text/html' if document else 'application/json'
                    with self.client.stream('GET', url, headers={'Accept': accept}, timeout=min(self.settings.sec_timeout,
                            max(.01, self.deadline - time.monotonic()))) as response:
                        body = bytearray()
                        for part in response.iter_bytes():
                            body.extend(part)
                            limit = (self.settings.sec_statement_archive_bytes if statement_archive
                                     else self.settings.sec_max_response_bytes)
                            if len(body) > limit:
                                raise SECError('response_limit', 'SEC response exceeds byte limit.')
                            if time.monotonic() >= self.deadline:
                                raise SECError('time_limit', 'SEC discovery time limit reached.')
                        out.update(status=response.status_code, response_headers=dict(
                            response.headers), sha256=hashlib.sha256(body).hexdigest(),
                            response_text=None if statement_archive else body.decode(errors='replace'),
                            response_bytes=len(body))
                        status = response.status_code
                        if status == 429 or status in (500, 502, 503, 504):
                            delay = max(delay, retry_after(response.headers.get('Retry-After')))
                            raise SECError('retryable_http', f'SEC returned HTTP {status}.')
                        if status != 200:
                            raise SECError(f'http_{status}', f'SEC returned HTTP {status}.')
                        if statement_archive:
                            if not body.startswith(b'PK\x03\x04'):
                                raise SECError('unsupported_content', 'Expected SEC statement ZIP archive.')
                            return bytes(body)
                        if document:
                            if 'html' not in response.headers.get('content-type', '').lower():
                                raise SECError('unsupported_content', 'Expected HTML annual filing.')
                            if not re.search(br'</html\s*>', body, re.IGNORECASE):
                                raise SECError('incomplete_document', 'HTML document is empty or incomplete.')
                            return bytes(body), response.headers.get('content-type')
                        try:
                            value = adapter.validate_json(body)
                            raw = json.loads(body)
                        except ValueError:
                            raise SECError('invalid_response', 'SEC returned malformed JSON/schema.')
                        out['response'] = raw
                        if not self.fixture:
                            self._cache(path, url, raw)
                        return value
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                failure = SECError('timeout' if isinstance(error, httpx.TimeoutException)
                                   else 'network_error', 'SEC request timed out or failed to connect.')
            except SECError as error:
                if error.code != 'retryable_http':
                    raise
                failure = error
            except httpx.HTTPError:
                raise SECError('transport_error', 'SEC HTTP transport failed.') from None
            if attempt > self.settings.sec_retries:
                raise failure
            if time.monotonic() + delay >= self.deadline:
                raise SECError('time_limit', 'SEC retry wait exceeds discovery time limit.')
            time.sleep(delay)
        raise AssertionError('Unreachable')

    def _cache(self, path, url, raw):
        self.cache.mkdir(parents=True, exist_ok=True)
        raw = self.trace.redact(raw)
        content = json.dumps(raw, sort_keys=True).encode()
        metadata = {'url': url, 'retrieved_at': time.time(), 'response': raw,
                    'sha256': hashlib.sha256(content).hexdigest()}
        descriptor, temporary = tempfile.mkstemp(dir=self.cache)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(metadata, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def tickers(self):
        return self.get(TICKERS, dict[str, TickerEntry], stage='lookup')

    def submissions(self, cik):
        return self.get(f'{SUBMISSIONS}CIK{cik}.json', Submissions, stage='discover')

    def history(self, name):
        return self.get(SUBMISSIONS + name, FilingArrays, stage='discover')

    def company_facts(self, cik):
        """Retrieve one bounded SEC Company Facts dataset for a discovered company."""
        if not re.fullmatch(r'\d{10}', str(cik)):
            raise SECError('invalid_response', 'Invalid SEC CIK for Company Facts.')
        return self.get(f'{COMPANY_FACTS}CIK{cik}.json', dict, stage='facts')

    def statement_archive(self, quarter):
        """Cache bounded quarterly ZIP bytes, verifying their digest on every read."""
        if not re.fullmatch(r'\d{4}q[1-4]', quarter):
            raise SECError('invalid_url', 'Invalid submission quarter.')
        url = f'https://www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip'
        path = self.cache / f'statements-{quarter}.zip'
        metadata_path = path.with_suffix('.metadata.json')
        if path.exists() and metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_bytes())
                if (metadata['url'] == url and time.time() - metadata['timestamp'] < 86400
                        and path.stat().st_size <= self.settings.sec_statement_archive_bytes):
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() == metadata['sha256']:
                        return raw, metadata
            except (ValueError, KeyError, OSError):
                pass
        raw = self.get(url, bytes, stage='facts', statement_archive=True)
        metadata = {'url': url, 'timestamp': time.time(),
                    'retrieved_at': datetime.now(UTC).isoformat(),
                    'sha256': hashlib.sha256(raw).hexdigest()}
        self.cache.mkdir(parents=True, exist_ok=True)
        for target, content in ((path, raw), (metadata_path, json.dumps(metadata).encode())):
            descriptor, temporary = tempfile.mkstemp(dir=self.cache)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return raw, metadata

    def filing_index(self, cik, accession):
        if not str(cik).isdigit() or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession):
            raise SECError('invalid_url', 'Invalid filing identity for SEC index.')
        url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/index.json'
        return self.get(url, dict, stage='facts')
