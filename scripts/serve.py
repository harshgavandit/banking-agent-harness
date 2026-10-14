"""Launch the ADK web UI with bounded runs and matching in-memory storage."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # Validate configuration before opening the server.
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    web_app = get_fast_api_app(agents_dir=str(ROOT), web=True,
        session_service_uri="memory://", artifact_service_uri="memory://",
        bind_host="127.0.0.1", port=args.port, max_llm_calls=16)
    uvicorn.run(web_app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
