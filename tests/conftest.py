"""Offline test settings: never depend on a developer's real credentials."""
import os

os.environ.update({
    "OPENAI_API_KEY": "test-only-not-a-real-api-key",
    "LLM_MODEL": "openai/gpt-4o-mini",
    "LLM_TIMEOUT_SECONDS": "30",
    "RATE_LIMIT_ENABLED": "false",
    "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "test-only-not-a-real-redis-token",
    "RATE_LIMIT_REQUESTS": "10",
    "RATE_LIMIT_WINDOW_SECONDS": "60",
    "LLM_RATE_LIMIT_REQUESTS": "60",
    "APPROVAL_TURNAROUND_HOURS": "24",
    "MAX_TOOL_CALLS": "20",
    "MAX_TRANSFER_ATTEMPTS": "5",
    "MAX_IDENTICAL_FAILURES": "3",
    "MOCK_TRANSACTION_OUTCOME": "SUCCESS",
})
