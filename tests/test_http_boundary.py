"""Request-size checks precede parsing, storage, and paid agent work."""
import asyncio

import httpx
import pytest


def boundary_request(chunks, headers=(), *, method='POST'):
    """Exercise the ASGI boundary without JSON parsing or a test client's framing."""
    from app.web import RequestBoundary
    calls, sent = [], []
    async def downstream(scope, receive, send):
        message = await receive()
        calls.append(message['body'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': message['body']})
    scope = {'type': 'http', 'method': method, 'path': '/api/chat', 'headers': list(headers)}
    messages = iter({'type': 'http.request', 'body': body, 'more_body': index < len(chunks) - 1}
        for index, body in enumerate(chunks))
    async def receive():
        return next(messages, {'type': 'http.disconnect'})
    async def send(message):
        sent.append(message)
    asyncio.run(RequestBoundary(downstream)(scope, receive, send))
    return calls, sent


@pytest.mark.parametrize('length', ['invalid', '-1'])
def test_malformed_content_length_is_client_error_without_storage(monkeypatch, length):
    from app import web
    class NoStorage:
        async def get(self, sid):
            pytest.fail('Malformed request reached storage')
    monkeypatch.setattr(web, 'store', NoStorage())
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url='https://test.local') as client:
            response = await client.post('/api/session', content=b'{}', headers={'content-length': length})
            assert response.status_code == 400
    asyncio.run(run())


def test_streamed_body_without_length_is_bounded_before_parsing():
    from app import web
    async def body():
        yield b'{"message":"'
        yield b'x' * 12001
        yield b'"}'
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url='https://test.local') as client:
            response = await client.post('/api/chat', content=body(), headers={'content-type': 'application/json'})
            assert response.status_code == 413
            assert response.headers['cache-control'] == 'no-store'
    asyncio.run(run())


def test_falsely_small_content_length_does_not_bypass_actual_limit():
    from app import web
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url='https://test.local') as client:
            response = await client.post('/api/chat', content=b'x' * 12001, headers={'content-length': '2'})
            assert response.status_code == 413
    asyncio.run(run())


@pytest.mark.parametrize('headers', [[], [(b'content-length', b'2')],
    [(b'transfer-encoding', b'chunked')]])
def test_actual_limit_blocks_before_downstream_handler(headers):
    calls, sent = boundary_request([b'a' * 6000, b'b' * 6001], headers)
    assert calls == []
    assert sent[0]['status'] == 413
    response_headers = dict(sent[0]['headers'])
    assert response_headers[b'cache-control'] == b'no-store'
    assert response_headers[b'x-content-type-options'] == b'nosniff'
    assert b"frame-ancestors 'none'" in response_headers[b'content-security-policy']


def test_exact_limit_replays_original_bytes_once_to_handler():
    payload = b'a' * 6000 + b'b' * 6000
    calls, sent = boundary_request([payload[:6000], b'', payload[6000:]])
    assert calls == [payload]
    assert sent[0]['status'] == 200
    assert sent[1]['body'] == payload


@pytest.mark.parametrize('length', [b'', b'-1', b'+2', b'1.0', b'1, 1', b'9' * 5000])
def test_malformed_or_huge_length_cannot_reach_handler(length):
    calls, sent = boundary_request([b'{}'], [(b'content-length', length)])
    assert calls == []
    assert sent[0]['status'] == (413 if length.isdigit() else 400)


def test_zero_prefixed_length_does_not_trigger_unbounded_integer_conversion():
    calls, sent = boundary_request([b'{}'], [(b'content-length', b'0' * 5000 + b'2')])
    assert calls == [b'{}']
    assert sent[0]['status'] == 200


def test_duplicate_length_is_rejected_before_handler():
    calls, sent = boundary_request([b'{}'], [(b'content-length', b'2'), (b'content-length', b'2')])
    assert calls == []
    assert sent[0]['status'] == 400
