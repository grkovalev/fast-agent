"""Single transport retry owner, shared by Jev and the OpenAI SDK."""
import asyncio
import json
from uuid import uuid4

import httpx


class ProviderFailure(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f'{code}: {message}')


class TracedTransport(httpx.AsyncBaseTransport):
    def __init__(self, recorder, settings, provider, inner=None, stage='probe'):
        self.recorder = recorder
        self.stage = stage
        self.settings = settings
        self.provider = provider
        self.inner = inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        call_id = 'http-' + uuid4().hex
        for attempt in range(1, self.settings.max_http_attempts + 1):
            retry = False
            try:
                with self.recorder.operation(
                    'provider.http', {'method': request.method, 'url': str(request.url),
                                     'body': json.loads(request.content)},
                    stage=self.stage, provider=self.provider, attempt=attempt, call_id=call_id,
                    actor='model' if self.provider == 'llm' else 'pipeline',
                ) as output:
                    response = await self.inner.handle_async_request(request)
                    try:
                        content = bytearray()
                        async for piece in response.aiter_bytes():
                            content.extend(piece)
                            if len(content) > self.settings.provider_max_response_bytes:
                                raise ProviderFailure('response_size', 'Provider response too large.')
                    finally:
                        await response.aclose()
                    try:
                        body = json.loads(content)
                    except ValueError:
                        body = content.decode(errors='replace')
                    output.update(status=response.status_code, body=body,
                                  headers=dict(response.headers))
                    self.recorder.emit(kind='http_response', span_id=call_id, call_id=call_id,
                                       provider=self.provider, stage=self.stage, attempt=attempt,
                                       summary=f'HTTP {response.status_code}', result=output)
                    if (self.provider == 'llm' and response.status_code == 429
                            and isinstance(body, dict) and isinstance(body.get('error'), dict)
                            and body['error'].get('type') == 'insufficient_quota'):
                        raise ProviderFailure('quota', 'Provider account credits are exhausted.')
                    if response.status_code in (429, 529, 500, 502, 503, 504):
                        retry = True
                        raise ProviderFailure('overloaded', f'HTTP {response.status_code}')
                    if response.status_code in (401, 403):
                        raise ProviderFailure('authentication', f'HTTP {response.status_code}')
                    if response.status_code >= 400:
                        raise ProviderFailure('request_validation', f'HTTP {response.status_code}')
                    # aiter_bytes() decoded the wire representation; do not ask the
                    # SDK/client to decompress it again or reuse its compressed byte length.
                    headers = {key: value for key, value in response.headers.items()
                               if key.lower() not in ('content-encoding', 'content-length')}
                    return httpx.Response(response.status_code, headers=headers,
                                          content=bytes(content), request=request)
            except httpx.TransportError as error:
                retry = True
                failure = ProviderFailure('transport', type(error).__name__)
            except ProviderFailure as error:
                failure = error
            if not retry or attempt == self.settings.max_http_attempts:
                raise failure
            self.recorder.emit(kind='retry', span_id=call_id, call_id=call_id,
                               provider=self.provider, stage=self.stage, attempt=attempt + 1,
                               summary='Transport retry with bounded exponential backoff.')
            await asyncio.sleep(min(8, 0.5 * 2 ** (attempt - 1)))
        raise AssertionError('Unreachable')

    async def aclose(self):
        await self.inner.aclose()
