"""Atomic Redis fixed-window limits. Backend outages block execution."""
import hashlib
from dataclasses import dataclass
import httpx

_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then redis.call('EXPIRE', KEYS[1], ARGV[1]); ttl = tonumber(ARGV[1]) end
return {count, ttl}
"""

@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after: int = 0
    unavailable: bool = False

class RedisRateLimiter:
    def __init__(self, url, token, *, client=None):
        self.url, self.token, self.client = url, token, client

    async def check(self, scope, limit, window):
        key = "banking-harness:rate:" + hashlib.sha256(scope.encode()).hexdigest()
        async def send(client):
            response = await client.post(self.url, headers={"Authorization": "Bearer " + self.token},
                json=["EVAL", _SCRIPT, "1", key, str(window)], timeout=5)
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise ValueError("Redis command failed")
            count, ttl = payload["result"]
            return RateDecision(int(count) <= limit, max(1, int(ttl)))
        try:
            if self.client is not None:
                return await send(self.client)
            async with httpx.AsyncClient() as client:
                return await send(client)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return RateDecision(False, 5, True)
