"""Centralized audit logging.

Every event is appended to an in-memory list and printed to stdout — the
terminal running `adk web` — so the harness's decisions are visible during
a demo. Never log API keys, secrets, chain-of-thought, or full account
numbers; only structured banking events.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

_logger = logging.getLogger("banking_agent.audit")
if not _logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[AUDIT] %(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False

_events: list[dict[str, Any]] = []

def _redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if any(x in k.lower() for x in ("token", "secret", "api_key", "password")) else _redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        for name in ("OPENAI_API_KEY", "UPSTASH_REDIS_REST_TOKEN"):
            secret = os.getenv(name)
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"\bsk-[\w-]+", "[REDACTED]", value)
        value = re.sub(r"(?i)((?:token|api_key|password|secret)\s*[=:]\s*)\S+", r"\1[REDACTED]", value)
        return re.sub(r"\b\d{12,19}\b", "[MASKED_ACCOUNT]", value)
    return value


def log(event_type: str, **details: Any) -> None:
    details = _redact(details)
    entry = {"event": event_type, **details}
    _events.append(entry)
    del _events[:-1000]
    detail_str = " ".join(f"{k}={v!r}" for k, v in details.items())
    _logger.info("%s %s", event_type, detail_str)


def events() -> list[dict[str, Any]]:
    """All audit events recorded so far, oldest first."""
    return list(_events)
