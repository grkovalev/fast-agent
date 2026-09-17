"""Durable JSONL journal with process-safe, run-scoped sequence allocation."""
import contextvars
import fcntl
import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from profitlab.contracts.trace import TraceEvent
from profitlab.storage import Repository
from profitlab.trace.redaction import Redactor

_parent = contextvars.ContextVar('trace_parent', default=None)


class TraceRecorder:
    def __init__(self, repository: Repository, run_id: str, redactor: Redactor | None = None):
        repository.manifest(run_id)  # Validate ID and require an existing run.
        self.repo = repository
        self.run_id = run_id
        self.redact = redactor or Redactor()
        self.path = repository.root / 'runs' / run_id / 'events.jsonl'
        self.lock_path = self.path.with_suffix('.lock')

    @contextmanager
    def _lock(self):
        with self.lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self):
        events, warnings = [], []
        if self.path.exists():
            for number, line in enumerate(self.path.read_bytes().splitlines(), 1):
                try:
                    events.append(TraceEvent.model_validate_json(line))
                except ValueError:
                    warnings.append(f'Incomplete or invalid journal line {number}; retained on disk.')
        return events, warnings

    def history(self):
        with self._lock():
            return self._read()

    def payload(self, value):
        content = json.dumps(self.redact(value), ensure_ascii=False, sort_keys=True,
                             allow_nan=False).encode()
        identifier = 'payload-' + hashlib.sha256(content).hexdigest()
        self.repo.put(self.run_id, identifier, content)
        return identifier

    def emit(self, *, kind, span_id, actor='pipeline', stage='setup', status='completed',
             summary='', parent_id=None, call_id=None, tool=None, provider=None, attempt=1,
             duration=None, request=None, result=None, error=None):
        request_id = self.payload(request) if request is not None else None
        result_id = self.payload(result) if result is not None else None
        with self._lock():
            events, _ = self._read()
            event = TraceEvent(
                event_id='event-' + uuid4().hex, sequence=max(
                    (event.sequence for event in events), default=0) + 1,
                run_id=self.run_id, span_id=span_id, parent_id=parent_id,
                kind=self.redact.text(kind), actor=self.redact.text(actor),
                stage=self.redact.text(stage), tool=self.redact(tool),
                provider=self.redact(provider), call_id=call_id,
                timestamp=datetime.now(UTC), duration=duration, attempt=attempt, status=status,
                summary=self.redact.text(summary), error=self.redact(error),
                request_artifact_id=request_id, result_artifact_id=result_id,
            )
            # Separate any incomplete tail before appending; preserve prior bytes for diagnostics.
            needs_newline = self.path.exists() and self.path.stat().st_size > 0
            if needs_newline:
                with self.path.open('rb') as stream:
                    stream.seek(-1, os.SEEK_END)
                    needs_newline = stream.read(1) != b'\n'
            with self.path.open('ab') as stream:
                if needs_newline:
                    stream.write(b'\n')
                stream.write(event.model_dump_json().encode() + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            return event

    @contextmanager
    def operation(self, name, arguments=None, *, actor='pipeline', stage='setup', attempt=1,
                  call_id=None, provider=None):
        """Wrap synchronous or asynchronous work using `with`; BaseException closes cancellation."""
        span = 'span-' + uuid4().hex
        call = call_id or 'call-' + uuid4().hex
        parent = _parent.get()
        parent_id = parent[1] if parent and parent[0] == self.run_id else None
        options = {'span_id': span, 'parent_id': parent_id, 'call_id': call, 'tool': name,
                   'actor': actor, 'provider': provider, 'stage': stage, 'attempt': attempt}
        self.emit(kind='start', status='running', summary=name, request=arguments, **options)
        token = _parent.set((self.run_id, span))
        start = time.monotonic()
        output = {}
        try:
            yield output
        except BaseException as error:
            interrupted = not isinstance(error, Exception)
            self.emit(kind='end', status='interrupted' if interrupted else 'failed',
                      summary=name, error={'type': type(error).__name__, 'message': str(error)},
                      duration=time.monotonic() - start, **options)
            raise
        else:
            self.emit(kind='end', status='completed', summary=name, result=output,
                      duration=time.monotonic() - start, **options)
        finally:
            _parent.reset(token)

    def recover_interrupted(self):
        """Call only on restart after workers have stopped, never from read-only UI requests."""
        with self._lock():
            events, _ = self._read()
        closed = {event.span_id for event in events if event.kind == 'end'}
        for event in events:
            if event.kind == 'start' and event.span_id not in closed:
                self.emit(kind='end', span_id=event.span_id, parent_id=event.parent_id,
                          call_id=event.call_id, actor=event.actor, stage=event.stage,
                          tool=event.tool, provider=event.provider, attempt=event.attempt, status='interrupted',
                          summary='Interrupted before completion; remote completion is unknown.')
                closed.add(event.span_id)

    def export(self, output: Path):
        events, warnings = self.history()
        # Resolve everything before publishing; damaged/missing payloads fail explicitly.
        payloads = {identifier: self.redact(json.loads(self.repo.read(self.run_id, identifier)))
                    for event in events for identifier in
                    (event.request_artifact_id, event.result_artifact_id) if identifier}
        output.mkdir(parents=True, exist_ok=False)
        (output / 'payloads').mkdir()
        for identifier, payload in payloads.items():
            (output / 'payloads' / f'{identifier}.json').write_text(
                json.dumps(payload, ensure_ascii=False, indent=2))
        records = [self.redact(event) for event in events]
        (output / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in records))
        (output / 'trace.json').write_text(json.dumps({
            'run_id': self.run_id, 'events': records, 'warnings': warnings,
            'scope': 'Redacted observable trace only; report export is not implemented yet.',
        }, indent=2))
