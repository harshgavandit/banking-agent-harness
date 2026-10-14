"""Credential-safe live verification through the real ADK runner."""
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import root_agent
from app.config import settings
from app.rate_limit import RedisRateLimiter
from app import mock_data
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


async def verify():
    report = {"model": settings.model, "timeout_seconds": settings.timeout, "checks": {}}
    scope = "verification:" + uuid.uuid4().hex
    limiter = RedisRateLimiter(settings.redis_url, settings.redis_token)
    if settings.rate_enabled:
        decisions = [await limiter.check(scope, 1, 2) for _ in range(2)]
        report["checks"]["redis_boundary"] = decisions[0].allowed and not decisions[1].allowed and not decisions[1].unavailable
        await asyncio.sleep(2.1)
        report["checks"]["redis_expiry"] = (await limiter.check(scope, 1, 2)).allowed
    sessions = InMemorySessionService()
    user = "verify-" + uuid.uuid4().hex
    session = await sessions.create_session(app_name="app", user_id=user)
    runner = Runner(agent=root_agent, app_name="app", session_service=sessions)
    tool_results = []

    async def turn(text):
        responses = []
        async for event in runner.run_async(user_id=user, session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text=text)])):
            if event.content:
                for part in event.content.parts or []:
                    if part.function_response:
                        tool_results.append({"tool": part.function_response.name, "response": part.function_response.response})
                    if part.text:
                        responses.append(part.text)
        return responses

    await turn("What is my savings account balance? Use get_balance.")
    report["checks"]["live_balance_tool"] = any(x["tool"] == "get_balance" and x["response"].get("balance") == 200000 for x in tool_results)
    before = mock_data.accounts["savings"]["balance"]
    await turn("Transfer 1000 rupees to Aaron. Stage it using initiate_transfer and ask me to confirm.")
    report["checks"]["stage_without_debit"] = any(x["response"].get("status") == "PENDING_CONFIRMATION" for x in tool_results) and mock_data.accounts["savings"]["balance"] == before
    await turn("confirm")
    confirmed = [x["response"] for x in tool_results if x["tool"] == "confirm_transfer"]
    report["checks"]["confirmed_transfer"] = bool(confirmed) and confirmed[-1].get("status") == "SUCCESS" and mock_data.accounts["savings"]["balance"] == before - 1000
    if confirmed and confirmed[-1].get("transaction_id"):
        tx = confirmed[-1]["transaction_id"]
        await turn(f"Use get_transaction_status to check {tx}.")
        report["checks"]["transaction_lookup"] = any(x["tool"] == "get_transaction_status" and x["response"].get("status") == "SUCCESS" for x in tool_results)
    await turn("Transfer 1000 rupees to Nick. Use initiate_transfer to check the policy.")
    report["checks"]["blocked_beneficiary"] = any(x["response"].get("status") == "REJECTED" and "blocked" in x["response"].get("reason", "") for x in tool_results)
    await turn("Transfer 1000 rupees to John. Use initiate_transfer to validate.")
    report["checks"]["ambiguous_beneficiary"] = any(x["response"].get("status") == "NEEDS_CLARIFICATION" for x in tool_results)
    report["tool_results"] = tool_results
    report["passed"] = all(report["checks"].values())
    return report


if __name__ == "__main__":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    try:
        result = asyncio.run(verify())
    except Exception as exc:
        result = {"passed": False, "error_type": type(exc).__name__}
    output = Path(__file__).resolve().parents[1] / "verification" / "live-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
