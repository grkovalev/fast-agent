"""Bounded SEC JSON requests, shared disk limiter, validated cache and traced retries."""
import fcntl
import hashlib
import json
import os
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

    def get(self, url, schema, *, stage):
        if url != TICKERS and not url.startswith(SUBMISSIONS):
            raise SECError('invalid_url', 'Only official SEC discovery URLs are allowed.')
        adapter = TypeAdapter(schema)
        call = 'call-' + uuid4().hex
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f'{key}.json'
        if not self.fixture and path.exists():
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
                    with self.client.stream('GET', url, timeout=min(self.settings.sec_timeout,
                            max(.01, self.deadline - time.monotonic()))) as response:
                        body = bytearray()
                        for part in response.iter_bytes():
                            body.extend(part)
                            if len(body) > self.settings.sec_max_response_bytes:
                                raise SECError('response_limit', 'SEC JSON exceeds byte limit.')
                            if time.monotonic() >= self.deadline:
                                raise SECError('time_limit', 'SEC discovery time limit reached.')
                        out.update(status=response.status_code, response_headers=dict(
                            response.headers), sha256=hashlib.sha256(body).hexdigest(),
                            response_text=body.decode(errors='replace'))
                        status = response.status_code
                        if status == 429 or status in (500, 502, 503, 504):
                            delay = max(delay, retry_after(response.headers.get('Retry-After')))
                            raise SECError('retryable_http', f'SEC returned HTTP {status}.')
                        if status != 200:
                            raise SECError(f'http_{status}', f'SEC returned HTTP {status}.')
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
