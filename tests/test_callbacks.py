import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from app import agent
from app.config import load_settings
from app.rate_limit import RedisRateLimiter


def test_redis_gates_agent_and_model_before_execution(monkeypatch):
    monkeypatch.setattr(agent, "settings", replace(agent.settings, rate_enabled=True, request_limit=1, llm_limit=1))
    counts = {}
    def server(request):
        import json
        command = json.loads(request.content)
        key = command[3]
        counts[key] = counts.get(key, 0) + 1
        return httpx.Response(200, json={"result": [counts[key], 30]})
    ctx = SimpleNamespace(session=SimpleNamespace(app_name="app", user_id="test"), user_content=None)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
            monkeypatch.setattr(agent, "rate_limiter", RedisRateLimiter("https://test.upstash.io", "test", client=client))
            assert await agent._log_user_request(ctx) is None
            blocked = await agent._log_user_request(ctx)
            assert "Rate limit reached" in blocked.parts[0].text
            assert await agent._enforce_model_limits(ctx, None) is None
            blocked_model = await agent._enforce_model_limits(ctx, None)
            assert "Rate limit reached" in blocked_model.content.parts[0].text
    asyncio.run(run())


def test_disabled_rate_limit_makes_no_redis_request(monkeypatch):
    monkeypatch.setattr(agent, "settings", replace(agent.settings, rate_enabled=False))
    async def run():
        assert await agent._log_user_request(SimpleNamespace(user_content=None)) is None
        assert await agent._enforce_model_limits(None, None) is None
    asyncio.run(run())


@pytest.mark.parametrize("name,value", [("RATE_LIMIT_REQUESTS", "0"), ("LLM_TIMEOUT_SECONDS", "oops"), ("RATE_LIMIT_ENABLED", "invalid"), ("UPSTASH_REDIS_REST_URL", "http://insecure.example"), ("UPSTASH_REDIS_REST_TOKEN", "")])
def test_invalid_settings_fail_without_exposing_values(monkeypatch, name, value):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        load_settings()


def test_model_failure_returns_actionable_message():
    result = agent._model_error(None, None, RuntimeError("secret-value"))
    assert "secret-value" not in result.content.parts[0].text
    assert "check the current transfer status" in result.content.parts[0].text
