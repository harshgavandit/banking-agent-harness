"""In-memory pending-transfer state.

A single pending slot is enough for this single-session demo — no database
or workflow engine needed. Requiring `confirm_transfer` to execute against
this real state (instead of exposing a tool parameter like
`skip_confirmation`) is what makes confirmation deterministic: the model can
be asked to skip it, but there is no code path that lets it.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import time


@dataclass
class PendingTransfer:
    beneficiary_id: str
    beneficiary_name: str
    account_last4: str
    amount: float
    invocation_id: str = ""
    created_at: float = 0


_pending: PendingTransfer | None = None


def set_pending(transfer: PendingTransfer, state=None) -> None:
    global _pending
    transfer.created_at = time.time()
    if state is None:
        _pending = transfer
    else:
        state["harness:pending_transfer"] = asdict(transfer)


def get_pending(state=None) -> PendingTransfer | None:
    if state is None:
        return _pending
    value = state.get("harness:pending_transfer")
    return PendingTransfer(**value) if value else None


def clear_pending(state=None) -> None:
    global _pending
    if state is None:
        _pending = None
    else:
        state["harness:pending_transfer"] = None
