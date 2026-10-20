# Vercel deployment verification — 20 October 2026

Public URL: https://banking-agent-harness.vercel.app

## Deployment

- Vercel project: `banking-agent-harness` in the owner's existing account.
- Runtime: Python 3.12, FastAPI, Google ADK, LiteLLM.
- Public entrypoint: `index.py` → `app.web:app`.
- Source and deployment secrets are separate. OpenAI and Upstash credentials
  are sensitive server-side environment variables. A dedicated random signing
  secret authenticates the anonymous session cookie. No secret values are in
  this report, browser assets, or Git history.
- The original local ADK launcher remains available; its debug/admin surface
  is not mounted on the hosted application.

## Verification performed

`scripts/verify_hosted.py` exercised the deployed HTTPS URL with independent
cookie jars and separate HTTP connections. All 14 recorded checks passed:

1. Public page served.
2. Health endpoint responded.
3. Initial mock balance was ₹200,000.
4. Session cookie was HTTP-only.
5. Staging a ₹1,000 transfer did not debit funds.
6. The actual initiation tool returned `PENDING_CONFIRMATION`.
7. A separate connection restored the pending proposal.
8. A later confirmation consumed the proposal and debited exactly once.
9. The confirmation tool reported `SUCCESS`.
10. A later balance-tool request returned ₹199,000.
11. Another visitor retained a fresh ₹200,000 account and empty history.
12. The ADK developer UI returned 404.
13. The private environment-file path returned 404.
14. API documentation/debug routes returned 404.

See `hosted-production-results.json`; `hosted-local-results.json` records
the same live workflow against the local public-app preview. The expanded
offline suite passed 37 tests, including context-scoped ledger isolation,
signed-cookie rejection, cross-origin rejection, payload validation, and
overlapping-turn rejection. JavaScript and Python syntax checks passed.

## Persistence and boundaries

Redis stores one expiring snapshot per visitor: ADK conversation state,
pending proposal, mock account, transactions, and displayed messages. A
120-second lease and atomic compare-owner commit serialize updates. The
application bounds each run to 75 seconds and eight model calls. Storage
inactivity expires a snapshot after 24 hours; the browser cookie has a
24-hour lifetime. No real accounts, payment rails, or settlement are connected.
The daily transfer allowance is a demo-session budget, without a midnight reset.

Public traffic can consume the configured model quota, subject to the user
and shared model rate limits. This is a demonstration with anonymous sessions,
not identity-verified financial access. Provider uptime, sustained load, and
production banking requirements are outside these checks.

Vercel's FastAPI runtime and deployment configuration were checked against
[Vercel's FastAPI documentation](https://vercel.com/docs/frameworks/backend/fastapi).
