import importlib
import math
from types import SimpleNamespace

import pytest

from app import limits, mock_data
from app.services import transfer_service
from app.tools import banking_tools as tools


def context(text="Transfer 1000 to Aaron", invocation="turn-1"):
    return SimpleNamespace(state={}, invocation_id=invocation,
        user_content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    mock_data.reset_state()
    importlib.reload(limits)
    importlib.reload(transfer_service)
    monkeypatch.setenv("MOCK_TRANSACTION_OUTCOME", "SUCCESS")


def test_confirmation_requires_later_explicit_user_turn():
    ctx = context()
    assert tools.initiate_transfer("Aaron", 1000, tool_context=ctx)["status"] == "PENDING_CONFIRMATION"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "CONFIRMATION_REQUIRED"
    assert mock_data.accounts["savings"]["balance"] == 200000
    ctx.invocation_id = "turn-2"
    ctx.user_content.parts[0].text = "confirm"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "SUCCESS"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "NO_PENDING_TRANSFER"


def test_session_cannot_confirm_another_sessions_transfer():
    tools.initiate_transfer("Aaron", 1000, tool_context=context())
    assert tools.confirm_transfer(tool_context=context("confirm", "turn-2"))["status"] == "NO_PENDING_TRANSFER"


def test_tool_limits_do_not_leak_across_sessions():
    a, b = {}, {}
    for _ in range(limits.MAX_TOOL_CALLS):
        assert limits.register_tool_call(a)
    assert not limits.register_tool_call(a)
    assert limits.register_tool_call(b)


@pytest.mark.parametrize("amount", [math.nan, math.inf, -math.inf, 0, -1, 0.001])
def test_invalid_money_is_rejected(amount):
    assert tools.initiate_transfer("Aaron", amount)["status"] == "REJECTED"
    assert mock_data.accounts["savings"]["balance"] == 200000


@pytest.mark.parametrize("outcome, balance", [("SUCCESS", 199000), ("PENDING", 199000), ("FAILED", 200000)])
def test_actual_outcome_is_recorded(monkeypatch, outcome, balance):
    monkeypatch.setenv("MOCK_TRANSACTION_OUTCOME", outcome)
    ctx = context()
    tools.initiate_transfer("Aaron", 1000, tool_context=ctx)
    ctx.invocation_id = "turn-2"
    ctx.user_content.parts[0].text = "confirm"
    result = tools.confirm_transfer(tool_context=ctx)
    assert result["status"] == outcome
    assert tools.get_transaction_status(result["transaction_id"])["status"] == outcome
    assert mock_data.accounts["savings"]["balance"] == balance


@pytest.mark.parametrize("beneficiary, amount, status", [("John", 1000, "NEEDS_CLARIFICATION"), ("Nick", 1000, "REJECTED"), ("Unknown", 1000, "REJECTED"), ("Aaron", 500000, "REJECTED"), ("Aaron", 76000, "REJECTED")])
def test_policy_paths(beneficiary, amount, status):
    assert tools.initiate_transfer(beneficiary, amount)["status"] == status
    assert transfer_service.get_pending() is None


def test_confirmation_revalidates_current_balance():
    ctx = context()
    tools.initiate_transfer("Aaron", 1000, tool_context=ctx)
    mock_data.accounts["savings"]["balance"] = 500
    ctx.invocation_id = "turn-2"
    ctx.user_content.parts[0].text = "confirm"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "REJECTED"
    assert mock_data.accounts["savings"]["balance"] == 500


def test_audit_redacts_user_supplied_secrets():
    from app import audit
    audit.log("USER_REQUEST", text="OPENAI_API_KEY=sk-test-sensitive-value account 1234567890123456")
    assert "sk-test-sensitive-value" not in str(audit.events()[-1])
    assert "1234567890123456" not in str(audit.events()[-1])


def test_rejected_new_request_clears_previous_pending():
    ctx = context()
    tools.initiate_transfer("Aaron", 1000, tool_context=ctx)
    tools.initiate_transfer("Nick", 1000, tool_context=ctx)
    ctx.invocation_id = "turn-2"
    ctx.user_content.parts[0].text = "confirm"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "NO_PENDING_TRANSFER"


def test_expired_confirmation_is_rejected():
    from app.config import settings
    ctx = context()
    tools.initiate_transfer("Aaron", 1000, tool_context=ctx)
    ctx.state["harness:pending_transfer"]["created_at"] -= settings.approval_hours * 3600 + 1
    ctx.invocation_id = "turn-2"
    ctx.user_content.parts[0].text = "confirm"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "REJECTED"
    assert mock_data.accounts["savings"]["balance"] == 200000


def test_unrelated_turn_cannot_confirm():
    ctx = context()
    tools.initiate_transfer("Aaron", 1000, tool_context=ctx)
    ctx.invocation_id = "turn-2"
    ctx.user_content.parts[0].text = "what is my balance?"
    assert tools.confirm_transfer(tool_context=ctx)["status"] == "CONFIRMATION_REQUIRED"


def test_transfer_attempt_limit_is_session_local():
    a, b = context(), context()
    for _ in range(limits.MAX_TRANSFER_ATTEMPTS):
        assert tools.initiate_transfer("Aaron", 1000, tool_context=a)["status"] == "PENDING_CONFIRMATION"
    assert tools.initiate_transfer("Aaron", 1000, tool_context=a)["status"] == "BLOCKED"
    assert tools.initiate_transfer("Aaron", 1000, tool_context=b)["status"] == "PENDING_CONFIRMATION"


def test_repeated_failures_block_only_the_affected_session():
    a, b = context(), context()
    for _ in range(limits.MAX_IDENTICAL_FAILURES):
        assert tools.initiate_transfer("Nick", 1000, tool_context=a)["status"] == "REJECTED"
    assert tools.initiate_transfer("Nick", 1000, tool_context=a)["status"] == "BLOCKED"
    assert tools.initiate_transfer("Nick", 1000, tool_context=b)["status"] == "REJECTED"
