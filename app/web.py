"""Public demo API; ADK developer/admin routes are deliberately not mounted."""
import asyncio
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app import audit, mock_data
from app.agent import root_agent, rate_limiter
from app.config import settings
from app.hosted_store import RedisStore, StoreUnavailable

COOKIE_NAME = "banking_demo"
STATIC = Path(__file__).resolve().parent.parent / "web"
store = RedisStore()
app = FastAPI(title="Banking Agent Harness", docs_url=None, redoc_url=None, openapi_url=None)


def _secret():
    secret = os.getenv("DEMO_SESSION_SECRET", "")
    if not secret and not os.getenv("VERCEL"):
        # Local-only fallback; production requires a dedicated generated secret.
        secret = settings.redis_token
    if len(secret) < 24:
        raise HTTPException(503, "The demo session service is not configured.")
    return secret.encode()


def _signature(sid):
    return hmac.new(_secret(), sid.encode(), hashlib.sha256).hexdigest()


def _identity(request):
    cookie = request.cookies.get(COOKIE_NAME, "")
    if not re.fullmatch(r"[a-f0-9]{64}\.[a-f0-9]{64}", cookie):
        return None
    sid, signature = cookie.split(".")
    return sid if hmac.compare_digest(signature, _signature(sid)) else None


def _check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "This request must come from the demo website.")


def _public(snapshot):
    return {"account": snapshot["ledger"]["accounts"][mock_data.ACCOUNT_ID],
        "messages": snapshot["messages"], "transactions": list(snapshot["ledger"]["transactions"].values()),
        "pending": snapshot["session"]["state"].get("harness:pending_transfer"),
        "beneficiaries": [mock_data.public_beneficiary(x) for x in mock_data.beneficiaries]}


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method == "POST" and int(request.headers.get("content-length", "0")) > 12000:
        return JSONResponse({"detail": "Request is too large."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(StoreUnavailable)
async def storage_error(request, error):
    return JSONResponse({"detail": "Demo storage is temporarily unavailable. Please try again shortly."}, status_code=503)


@app.get("/")
async def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "mock-banking-demo", "storage": "redis", "version": "1"}


@app.get("/api/session")
async def get_session(request: Request):
    sid = _identity(request)
    snapshot = await store.get(sid) if sid else None
    if snapshot is None:
        raise HTTPException(401, "Start a demo session to continue.")
    return _public(snapshot)


@app.post("/api/session")
async def create_session(request: Request):
    _check_origin(request)
    sid = _identity(request)
    if sid:
        existing = await store.get(sid)
        if existing is not None:
            return _public(existing)
    if settings.rate_enabled:
        address = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
        decision = await rate_limiter.check("hosted-session:" + address, 20, 60)
        if not decision.allowed:
            raise HTTPException(503 if decision.unavailable else 429, "Please wait a minute before starting another demo.")
    sid = secrets.token_hex(32)
    owner = secrets.token_hex(16)
    if not await store.acquire(sid, owner):
        raise HTTPException(409, "Please try starting the demo again.")
    session = Session(app_name="app", user_id=sid, id=sid, state={})
    snapshot = {"session": session.model_dump(mode="json"), "ledger": mock_data.new_ledger(), "messages": []}
    if not await store.commit(sid, owner, snapshot):
        raise StoreUnavailable()
    response = JSONResponse(_public(snapshot))
    response.set_cookie(COOKIE_NAME, sid + "." + _signature(sid), max_age=86400,
        httponly=True, secure=request.url.scheme == "https", samesite="strict", path="/")
    return response


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)


@app.post("/api/chat")
async def chat(payload: ChatMessage, request: Request):
    _check_origin(request)
    sid = _identity(request)
    if not sid:
        raise HTTPException(401, "Start a demo session to continue.")
    message = payload.message.strip()
    if not message:
        raise HTTPException(422, "Enter a message first.")
    owner = secrets.token_hex(16)
    if not await store.acquire(sid, owner):
        raise HTTPException(409, "A response is already in progress. Please wait.")
    committed = False
    try:
        snapshot = await store.get(sid)
        if snapshot is None:
            raise HTTPException(401, "Your demo session expired. Start a new session.")
        if len(snapshot["messages"]) >= 80:
            raise HTTPException(429, "This demo session has reached its conversation limit.")
        saved = Session.model_validate(snapshot["session"])
        service = InMemorySessionService()
        service.sessions = {"app": {sid: {sid: saved}}}
        runner = Runner(agent=root_agent, app_name="app", session_service=service)
        responses, actions = [], []
        with mock_data.use_ledger(snapshot["ledger"]):
            try:
                async with asyncio.timeout(75):
                    async for event in runner.run_async(user_id=sid, session_id=sid,
                        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
                        run_config=RunConfig(max_llm_calls=8)):
                        for part in event.content.parts if event.content and event.content.parts else []:
                            if part.function_response:
                                actions.append({"tool": part.function_response.name, "result": part.function_response.response})
                            if event.is_final_response() and part.text:
                                responses.append(part.text)
            except Exception as error:
                audit.log("HOSTED_RUN_ERROR", error_type=type(error).__name__)
                responses.append("The response could not finish. Your latest demo account and transfer status are shown below. Check them before retrying.")
        session = await service.get_session(app_name="app", user_id=sid, session_id=sid)
        snapshot["session"] = session.model_dump(mode="json")
        reply = "\n".join(responses) or "Please check the recorded action below and try a short follow-up."
        snapshot["messages"].extend([{"role": "user", "text": message}, {"role": "assistant", "text": reply, "actions": actions}])
        if not await store.commit(sid, owner, snapshot):
            raise StoreUnavailable()
        committed = True
        return {"reply": reply, "actions": actions, **_public(snapshot)}
    finally:
        if not committed:
            await store.release(sid, owner)


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
