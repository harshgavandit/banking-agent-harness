"""Settings loaded before modules consume environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

def positive_int(name, default):
    try:
        value = int(os.getenv(name, str(default)))
        if value > 0:
            return value
    except ValueError:
        pass
    raise ValueError(f"{name} must be a positive integer")

@dataclass(frozen=True, repr=False)
class Settings:
    model: str
    timeout: int
    rate_enabled: bool
    request_limit: int
    llm_limit: int
    window: int
    redis_url: str
    redis_token: str
    approval_hours: int

def load_settings():
    model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini").strip()
    if not model:
        raise ValueError("LLM_MODEL must not be empty")
    if "/" not in model:
        model = "openai/" + model
    if model.startswith("openai/") and not os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("OPENAI_API_KEY is required")
    enabled = os.getenv("RATE_LIMIT_ENABLED", "false").strip().lower()
    if enabled not in {"true", "false", "1", "0"}:
        raise ValueError("RATE_LIMIT_ENABLED must be true or false")
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if enabled in {"true", "1"}:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise ValueError("UPSTASH_REDIS_REST_URL must be an HTTPS endpoint")
        if not token:
            raise ValueError("UPSTASH_REDIS_REST_TOKEN is required when rate limiting is enabled")
    return Settings(model, positive_int("LLM_TIMEOUT_SECONDS", 30), enabled in {"true", "1"},
        positive_int("RATE_LIMIT_REQUESTS", 10), positive_int("LLM_RATE_LIMIT_REQUESTS", 60),
        positive_int("RATE_LIMIT_WINDOW_SECONDS", 60), url, token, positive_int("APPROVAL_TURNAROUND_HOURS", 24))

settings = load_settings()
