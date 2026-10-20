"""Expiring Redis snapshots with a lease and atomic commit for each visitor."""
import json

import httpx

from app.config import settings

TTL = 86400
PREFIX = "banking-harness:hosted:v1:"
_COMMIT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('DEL', KEYS[1])
return 1
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
 return redis.call('DEL', KEYS[1])
end
return 0
"""


class StoreUnavailable(Exception):
    pass


class RedisStore:
    async def command(self, *args):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(settings.redis_url,
                    headers={"Authorization": "Bearer " + settings.redis_token}, json=list(args))
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    raise StoreUnavailable()
                return data["result"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise StoreUnavailable() from None

    async def get(self, sid):
        value = await self.command("GET", PREFIX + sid)
        return json.loads(value) if value else None

    async def acquire(self, sid, owner):
        result = await self.command("SET", PREFIX + sid + ":lock", owner, "NX", "EX", "120")
        return result == "OK"

    async def commit(self, sid, owner, value):
        return await self.command("EVAL", _COMMIT, "2", PREFIX + sid + ":lock", PREFIX + sid,
            owner, json.dumps(value, allow_nan=False), str(TTL)) == 1

    async def release(self, sid, owner):
        await self.command("EVAL", _RELEASE, "1", PREFIX + sid + ":lock", owner)
