"""Scripted service outcomes, recorded through real operation wrappers; no model calls."""
import asyncio

from .recorder import TraceRecorder


def record_demo(trace: TraceRecorder):
    with trace.operation('synthetic fixture processing', {'ticker': 'DEMO'}) as result:
        with trace.operation('fixture read', {'fixture': 'annual-2025'}) as read:
            read['text'] = 'Synthetic source payload. ' * 2000
        trace.emit(kind='cache_hit', span_id='fixture-cache',
                   summary='Synthetic fixture cache hit', result={'artifact_id': 'annual-2025'})
        call_id = 'fixture-retry-call'
        try:
            with trace.operation('fixture request', {'fixture': 'retry example'},
                                 attempt=1, call_id=call_id):
                raise RuntimeError('Synthetic temporary failure; retry permitted.')
        except RuntimeError:
            trace.emit(kind='retry', span_id='fixture-retry', call_id=call_id,
                       attempt=2, summary='Retrying scripted temporary failure')
        with trace.operation('fixture request', {'fixture': 'retry example'},
                             attempt=2, call_id=call_id) as retry:
            retry['status'] = 'synthetic success'
        try:
            with trace.operation('fixture interrupted request', {'synthetic': True}):
                raise asyncio.CancelledError('Scripted interruption; remote outcome unknown.')
        except asyncio.CancelledError:
            pass
        result['note'] = 'Deterministic pipeline operations; no agent/model conversation occurred.'
