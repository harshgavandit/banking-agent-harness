# End-to-end verification — 14 October 2026

Scope: the Banking Agent Harness project, tested locally on Windows/Python 3.12.

## Findings and changes

The supplied OpenAI/Upstash credentials were present. Originally, Redis rate
settings, model timeout, and approval turnaround were unused. Execution counters
and the pending transfer slot were module-global. The two-step tool flow allowed
the model to call both tools in one turn without explicit human confirmation.
Non-finite/sub-paise amounts and audit redaction also needed enforcement.

The current implementation loads/validates configuration before initialization,
normalizes the bare OpenAI model name, applies the timeout, integrates atomic
Redis fixed-window quotas in ADK callbacks, and blocks on Redis failure.
Session state owns pending proposals and execution budgets. Confirmation requires
an explicit later user turn, checks expiry, revalidates policy, and consumes the
proposal once. New initiation requests clear stale proposals. Audit entries redact
configured credential values and full contiguous account numbers.

## Evidence

| Proof | Result | Artifact |
| --- | --- | --- |
| Automated regression suite | 34 tests passed in the verified run | `../tests/`; generated JUnit XML remains local |
| Dependency consistency | `pip check`: no broken requirements | `requirements.lock.txt` |
| Live Redis authentication/atomic quota | First request allowed, second blocked, request allowed after expiry | `live-results.json` |
| Live OpenAI/ADK tool execution | Balance read, staged transfer without debit, later confirmed success, transaction lookup, blocked beneficiary, ambiguity | `live-results.json` |
| Running HTTP service | UI served, app discovered, balance tool invoked, exhausted user quota blocked before tool execution | `http-results.json` |
| Browser balance | Displayed ₹200,000, ACTIVE, daily limit ₹100,000, daily usage ₹25,000 | Browser observation |
| Browser skip-confirmation request | Returned pending confirmation with Aaron Johnson, account ending 5678, ₹1,000, and requested a separate confirm turn | Browser observation |
| Browser explicit confirmation | Later `confirm` invoked the tool, reported success and new balance ₹199,000 | `browser-confirmed-transfer.jpg` |
| Browser beneficiary lookup | `find_beneficiaries("Aaron")` returned Aaron Johnson, ACTIVE, account ending 5678 | `browser-beneficiary-lookup.jpg` |
| Python syntax | `compileall` completed successfully for app, scripts, and tests | Final verification command |

Live verification used the existing configured `openai/gpt-4o-mini` model with a
30-second timeout. Redis used the supplied HTTPS REST credentials. Credential
values were not printed or copied into this report. Live requests consume provider
quota; Redis test keys expire naturally.

The Redis command format and callback wiring were checked against the official
[Upstash REST API documentation](https://upstash.com/docs/redis/features/restapi)
and [Google ADK callback documentation](https://github.com/google/adk-docs/blob/main/docs/callbacks/types-of-callbacks.md),
as well as the installed ADK source and live behavior.

## Runtime and practical limits

The app runs at `http://127.0.0.1:8010/dev-ui/?app=app`. Port 8000 was occupied by
an unrelated service and was preserved. The launcher uses memory sessions/artifacts
and a 16-model-call ceiling per run. A fresh server process starts with the initial
mock ledger. A new chat resets session execution budgets, but the per-user Redis
request quota remains shared across that user's chats within the window.

This verifies a local POC. Accounts and transactions are shared in-memory mock
data, not a real payment integration or durable/distributed ledger. The ADK dev UI
has no production authentication; its user IDs are not trusted identities. Audit
redaction covers the harness log, not every upstream developer trace or chat store.
ADK emits experimental feature warnings and an OpenAPI duplicate-operation-ID
warning for its evaluation routes; the tested chat routes work. Provider outages,
model quality on arbitrary prompts, sustained load, and production deployment have
not been exhaustively evaluated.

Generated JUnit XML, local evidence manifests, server logs, and process IDs are
excluded from version control. The published JSON results and screenshots contain
only the demo's mock data and safe configuration metadata.
