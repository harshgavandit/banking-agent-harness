"""Deterministic transfer validation.

The LLM may request any transfer it likes; whether it actually happens is
decided entirely here, in plain Python — never by the system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app import mock_data


@dataclass
class TransferValidation:
    status: str  # "APPROVED" | "NEEDS_CLARIFICATION" | "REJECTED"
    beneficiary: dict[str, str] | None = None
    candidates: list[dict[str, str]] = field(default_factory=list)
    reason: str | None = None


def validate_transfer(beneficiary_query: str, amount: float) -> TransferValidation:
    try:
        money = Decimal(str(amount))
        if not money.is_finite() or money <= 0 or money != money.quantize(Decimal("0.01")):
            return TransferValidation(status="REJECTED", reason="Amount must be positive, finite, and have at most two decimal places.")
    except (InvalidOperation, ValueError):
        return TransferValidation(status="REJECTED", reason="Invalid transfer amount.")
    matches = mock_data.resolve_beneficiaries(beneficiary_query)

    if not matches:
        return TransferValidation(
            status="REJECTED", reason=f"No beneficiary matches '{beneficiary_query}'."
        )
    if len(matches) > 1:
        return TransferValidation(status="NEEDS_CLARIFICATION", candidates=matches)

    beneficiary = matches[0]

    if amount <= 0:
        return TransferValidation(
            status="REJECTED", reason="Transfer amount must be greater than zero."
        )

    account = mock_data.current_accounts()[mock_data.ACCOUNT_ID]
    if account["status"] != "ACTIVE":
        return TransferValidation(status="REJECTED", reason="Your account is not active.")

    if beneficiary["status"] != "ACTIVE":
        return TransferValidation(
            status="REJECTED",
            reason=f"Beneficiary '{beneficiary['name']}' is blocked and cannot receive transfers.",
        )

    if money > Decimal(str(account["balance"])):
        return TransferValidation(status="REJECTED", reason="Insufficient account balance.")

    if Decimal(str(account["daily_used"])) + money > Decimal(str(account["daily_limit"])):
        remaining = account["daily_limit"] - account["daily_used"]
        return TransferValidation(
            status="REJECTED",
            reason=f"Daily transfer limit exceeded. Only {remaining} remains today.",
        )

    return TransferValidation(status="APPROVED", beneficiary=beneficiary)
