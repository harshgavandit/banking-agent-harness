import asyncio

import httpx

from app.rate_limit import RedisRateLimiter


def test_redis_boundary_and_expiry():
    count = 0

    def server(request):
        nonlocal count
        assert request.headers["Authorization"] == "Bearer test-token"
        count += 1
        return httpx.Response(200, json={"result": [count, 12]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
            limiter = RedisRateLimiter("https://test.upstash.io", "test-token", client=client)
            first = await limiter.check("test", 1, 60)
            second = await limiter.check("test", 1, 60)
            assert first.allowed
            assert not second.allowed
            assert second.retry_after == 12
    asyncio.run(run())


def test_redis_outage_fails_closed_without_secret():
    async def run():
        def server(request):
            return httpx.Response(401, json={"error": "test-token"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
            limiter = RedisRateLimiter("https://test.upstash.io", "test-token", client=client)
            result = await limiter.check("test", 1, 60)
            assert not result.allowed
            assert result.unavailable
            assert "test-token" not in str(result)
    asyncio.run(run())
