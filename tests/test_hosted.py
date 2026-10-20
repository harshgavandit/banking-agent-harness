import asyncio
import copy
from types import SimpleNamespace

import httpx

from app import mock_data
from app.tools import banking_tools as tools


def test_hosted_ledgers_isolate_visitors_and_survive_new_context():
    first = mock_data.new_ledger()
    second = mock_data.new_ledger()
    ctx = SimpleNamespace(state={}, invocation_id="one", user_content=SimpleNamespace(parts=[]))
    with mock_data.use_ledger(first):
        tools.initiate_transfer("Aaron", 1000, tool_context=ctx)
        ctx.invocation_id = "two"
        ctx.user_content.parts = [SimpleNamespace(text="confirm")]
        assert tools.confirm_transfer(tool_context=ctx)["status"] == "SUCCESS"
        assert tools.get_balance()["balance"] == 199000
    with mock_data.use_ledger(second):
        assert tools.get_balance()["balance"] == 200000
        assert tools.get_transaction_status("TXN001")["status"] == "ERROR"
    restored = copy.deepcopy(first)
    with mock_data.use_ledger(restored):
        assert tools.get_balance()["balance"] == 199000
        assert tools.get_transaction_status("TXN001")["status"] == "SUCCESS"


class MemoryStore:
    def __init__(self):
        self.values = {}
        self.locks = {}

    async def get(self, sid):
        return copy.deepcopy(self.values.get(sid))

    async def acquire(self, sid, owner):
        if sid in self.locks:
            return False
        self.locks[sid] = owner
        return True

    async def commit(self, sid, owner, value):
        if self.locks.get(sid) != owner:
            return False
        self.values[sid] = copy.deepcopy(value)
        del self.locks[sid]
        return True

    async def release(self, sid, owner):
        if self.locks.get(sid) == owner:
            del self.locks[sid]


def test_public_api_session_cookie_and_private_routes(monkeypatch):
    from app import web
    monkeypatch.setattr(web, "store", MemoryStore())
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="https://test.local") as client:
            assert (await client.get("/")).status_code == 200
            assert (await client.get("/api/health")).json()["status"] == "ok"
            assert (await client.post("/api/chat", json={"message": "hello"})).status_code == 401
            response = await client.post("/api/session")
            assert response.status_code == 200
            assert response.json()["account"]["balance"] == 200000
            assert "HttpOnly" in response.headers["set-cookie"]
            assert "Secure" in response.headers["set-cookie"]
            assert (await client.get("/api/session")).json()["account"]["balance"] == 200000
            assert (await client.post("/api/chat", json={"message": "x" * 2001})).status_code == 422
            assert (await client.post("/api/session", headers={"Origin": "https://evil.example"})).status_code == 403
            assert (await client.get("/dev-ui/")).status_code == 404
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/app/.env")).status_code == 404
            client.cookies.clear()
            client.cookies.set(web.COOKIE_NAME, "forged-cookie")
            assert (await client.get("/api/session")).status_code == 401
    asyncio.run(run())


def test_session_lock_rejects_overlapping_turns(monkeypatch):
    from app import web
    storage = MemoryStore()
    monkeypatch.setattr(web, "store", storage)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="https://test.local") as client:
            await client.post("/api/session")
            sid = next(iter(storage.values))
            storage.locks[sid] = "another-request"
            response = await client.post("/api/chat", json={"message": "confirm"})
            assert response.status_code == 409
            assert storage.values[sid]["ledger"]["accounts"]["savings"]["balance"] == 200000
    asyncio.run(run())
