"""Execution budgets stored in ADK session state."""
from app.config import positive_int

MAX_TOOL_CALLS = positive_int("MAX_TOOL_CALLS", 20)
MAX_TRANSFER_ATTEMPTS = positive_int("MAX_TRANSFER_ATTEMPTS", 5)
MAX_IDENTICAL_FAILURES = positive_int("MAX_IDENTICAL_FAILURES", 3)
_local_state = {}

def _increment(state, key, maximum):
    state = _local_state if state is None else state
    state[key] = state.get(key, 0) + 1
    return state[key] <= maximum

def register_tool_call(state=None):
    return _increment(state, "harness:tool_calls", MAX_TOOL_CALLS)

def register_transfer_attempt(state=None):
    return _increment(state, "harness:transfer_attempts", MAX_TRANSFER_ATTEMPTS)

def record_transfer_outcome(is_rejection, signature=None, state=None):
    state = _local_state if state is None else state
    key = "harness:failure_streak"
    if not is_rejection:
        state[key], state["harness:last_failure"] = 0, None
        return True
    state[key] = state.get(key, 0) + 1 if signature == state.get("harness:last_failure") else 1
    state["harness:last_failure"] = signature
    return state[key] <= MAX_IDENTICAL_FAILURES
