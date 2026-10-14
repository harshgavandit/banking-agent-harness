"""Check the running dev UI, HTTP agent flow, and live Redis request gate."""
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import settings
from app.rate_limit import RedisRateLimiter


async def verify():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
    report = {"base_url": base, "checks": {}}
    user = "http-verify-" + uuid.uuid4().hex
    async with httpx.AsyncClient(base_url=base, timeout=90) as client:
        ui = await client.get("/dev-ui/")
        report["checks"]["ui_served"] = ui.status_code == 200 and "<html" in ui.text.lower()
        apps = await client.get("/list-apps")
        apps.raise_for_status()
        report["checks"]["agent_discovered"] = "app" in apps.json()
        session_response = await client.post(f"/apps/app/users/{user}/sessions", json={})
        session_response.raise_for_status()
        session = session_response.json()["id"]
        body = {"appName": "app", "userId": user, "sessionId": session,
            "newMessage": {"role": "user", "parts": [{"text": "What is my balance? Use get_balance."}]}}
        response = await client.post("/run", json=body)
        response.raise_for_status()
        events = response.json()
        report["checks"]["http_balance_tool"] = any(part.get("functionResponse", {}).get("name") == "get_balance" for event in events for part in event.get("content", {}).get("parts", []))
        if settings.rate_enabled:
            # This disposable user's quota is filled without paid model calls.
            limiter = RedisRateLimiter(settings.redis_url, settings.redis_token)
            for _ in range(settings.request_limit):
                await limiter.check(f"request:app:{user}", settings.request_limit, settings.window)
            blocked = await client.post("/run", json=body)
            blocked.raise_for_status()
            blocked_events = blocked.json()
            parts = [p for e in blocked_events for p in e.get("content", {}).get("parts", [])]
            report["checks"]["http_request_rate_block"] = any("Rate limit reached" in p.get("text", "") for p in parts) and not any("functionCall" in p or "functionResponse" in p for p in parts)
    report["passed"] = all(report["checks"].values())
    return report


if __name__ == "__main__":
    try:
        result = asyncio.run(verify())
    except Exception as exc:
        result = {"passed": False, "error_type": type(exc).__name__}
    output = Path(__file__).resolve().parents[1] / "verification/http-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
