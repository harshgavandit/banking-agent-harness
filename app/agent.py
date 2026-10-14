"""Defines the single ADK banking agent used throughout this project.

Discoverable by the `adk web` / `adk run` CLI: this module exposes a
module-level `root_agent`, and `app/__init__.py` imports this module.
"""

from __future__ import annotations

from typing import Any

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.base_tool import BaseTool
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from app.config import settings
from app.rate_limit import RedisRateLimiter

from app import audit, limits
from app.prompts import SYSTEM_PROMPT
from app.tools.banking_tools import (
    confirm_transfer,
    find_beneficiaries,
    get_balance,
    get_transaction_status,
    initiate_transfer,
)

AGENT_NAME = "banking_agent"
rate_limiter = RedisRateLimiter(settings.redis_url, settings.redis_token)

def _message(text):
    return types.Content(role="model", parts=[types.Part(text=text)])

def _rate_message(decision):
    if decision.unavailable:
        return "Rate-limit service is unavailable. Execution paused. Check the current transfer status before resubmitting an action. Please try again later."
    return f"Rate limit reached. Please retry in {decision.retry_after} seconds. Check transfer status before resubmitting an action."


async def _log_user_request(callback_context: Context):
    """One USER_REQUEST audit event per user turn.

    This is cross-cutting lifecycle logging that applies regardless of what
    the user asked for, so it belongs in ADK's callback layer rather than
    in any individual tool. ADK invokes this with `callback_context=...`.
    """
    text = None
    if callback_context.user_content and callback_context.user_content.parts:
        text = callback_context.user_content.parts[0].text
    audit.log("USER_REQUEST", text=text)
    if settings.rate_enabled:
        session = callback_context.session
        decision = await rate_limiter.check(f"request:{session.app_name}:{session.user_id}", settings.request_limit, settings.window)
        if not decision.allowed:
            audit.log("LIMIT_EXCEEDED", limit="USER_REQUESTS", unavailable=decision.unavailable)
            return _message(_rate_message(decision))
    return None

async def _enforce_model_limits(callback_context: Context, llm_request):
    if settings.rate_enabled:
        decision = await rate_limiter.check("llm:" + settings.model, settings.llm_limit, settings.window)
        if not decision.allowed:
            audit.log("LIMIT_EXCEEDED", limit="LLM_REQUESTS", unavailable=decision.unavailable)
            return LlmResponse(content=_message(_rate_message(decision)))
    return None

def _model_error(callback_context: Context, llm_request, error):
    audit.log("MODEL_ERROR", error_type=type(error).__name__)
    return LlmResponse(content=_message("The model service could not complete this request. Please retry later and check the current transfer status before resubmitting an action."))


def _enforce_tool_limits(
    tool: BaseTool, args: dict[str, Any], tool_context: Context
) -> dict[str, Any] | None:
    """MAX_TOOL_CALLS gate + TOOL_REQUESTED audit event, for every tool call.

    The limit itself and the counting live in app/limits.py; this callback
    only triggers the check. Transfer-specific limits (attempts, repeated
    identical failures) are banking business rules, so they live with the
    transfer logic in app/tools/banking_tools.py instead of here. ADK
    invokes this with `tool=...`, `args=...`, `tool_context=...`.
    """
    if not limits.register_tool_call(tool_context.state):
        audit.log("LIMIT_EXCEEDED", limit="MAX_TOOL_CALLS", tool=tool.name)
        return {
            "status": "BLOCKED",
            "reason": "Maximum tool calls reached for this session.",
        }
    audit.log("TOOL_REQUESTED", tool=tool.name, args=args)
    return None


root_agent = Agent(
    name=AGENT_NAME,
    model=LiteLlm(model=settings.model, timeout=settings.timeout, num_retries=0),
    description=(
        "Banking assistant for checking balance, finding beneficiaries, "
        "transferring money, and checking transaction status."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[get_balance, find_beneficiaries, initiate_transfer, confirm_transfer, get_transaction_status],
    before_agent_callback=_log_user_request,
    before_tool_callback=_enforce_tool_limits,
    before_model_callback=_enforce_model_limits,
    on_model_error_callback=_model_error,
)
