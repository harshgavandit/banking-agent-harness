"""Session admission uses the transport peer unless Vercel supplies a valid IP."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest


def admission_scopes(monkeypatch, requests, *, vercel=False, peer="192.0.2.8"):
    from app import web
    scopes = []

    class DenyAdmission:
        async def check(self, scope, limit, window):
            scopes.append(scope)
            assert (limit, window) == (20, 60)
            return SimpleNamespace(allowed=False, unavailable=False)

    class NoStorage:
        async def acquire(self, *args):
            pytest.fail("Rejected admission must not create session state")

    if vercel:
        monkeypatch.setenv("VERCEL", "1")
    else:
        monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(web, "settings", replace(web.settings, rate_enabled=True))
    monkeypatch.setattr(web, "rate_limiter", DenyAdmission())
    monkeypatch.setattr(web, "store", NoStorage())

    async def run():
        transport = httpx.ASGITransport(app=web.app, client=(peer, 1234))
        async with httpx.AsyncClient(transport=transport, base_url="https://test.local") as client:
            for headers in requests:
                response = await client.post("/api/session", content=b"{}", headers=headers)
                assert response.status_code == 429
    asyncio.run(run())
    return scopes


def test_self_hosted_spoofed_forwarding_headers_do_not_change_session_bucket(monkeypatch):
    scopes = admission_scopes(monkeypatch, [
        {"x-forwarded-for": "198.51.100.1", "x-vercel-forwarded-for": "198.51.100.2"},
        {"x-forwarded-for": "203.0.113.3", "x-vercel-forwarded-for": "203.0.113.4"},
        {},
    ])
    assert scopes == ["hosted-session:192.0.2.8"] * 3


def test_vercel_uses_valid_platform_ip_instead_of_generic_forwarding_header(monkeypatch):
    scopes = admission_scopes(monkeypatch, [
        {"x-forwarded-for": "203.0.113.3", "x-vercel-forwarded-for": "198.51.100.2"},
        {"x-forwarded-for": "203.0.113.4", "x-vercel-forwarded-for": "198.51.100.2"},
    ], vercel=True)
    assert scopes == ["hosted-session:198.51.100.2"] * 2


def test_vercel_canonicalizes_equivalent_ip_addresses(monkeypatch):
    scopes = admission_scopes(monkeypatch, [
        {"x-vercel-forwarded-for": "2001:0db8:0:0:0:0:0:1"},
        {"x-vercel-forwarded-for": "2001:db8::1"},
        {"x-vercel-forwarded-for": "::ffff:198.51.100.2"},
        {"x-vercel-forwarded-for": "198.51.100.2"},
    ], vercel=True)
    assert scopes == ["hosted-session:2001:db8::1"] * 2 + ["hosted-session:198.51.100.2"] * 2


@pytest.mark.parametrize("platform", ["", "not-an-ip", "198.51.100.1, 203.0.113.2",
    "127.1", "2130706433", "fe80::1%eth0", "[2001:db8::1]", "198.51.100.2:80"])
def test_invalid_platform_value_falls_back_to_peer_not_generic_xff(monkeypatch, platform):
    scopes = admission_scopes(monkeypatch, [
        {"x-forwarded-for": "203.0.113.3", "x-vercel-forwarded-for": platform},
    ], vercel=True)
    assert scopes == ["hosted-session:192.0.2.8"]


def test_duplicate_or_missing_platform_header_falls_back_to_peer(monkeypatch):
    scopes = admission_scopes(monkeypatch, [
        [("x-vercel-forwarded-for", "198.51.100.1"),
         ("x-vercel-forwarded-for", "203.0.113.2")],
        {"x-forwarded-for": "203.0.113.3"},
    ], vercel=True)
    assert scopes == ["hosted-session:192.0.2.8"] * 2
