"""Live hosted flow with isolated cookie jars; never prints session credentials."""
import argparse
import json
from pathlib import Path

import httpx


def verify(base_url):
    checks = {}
    with httpx.Client(base_url=base_url, timeout=100, follow_redirects=True) as first, httpx.Client(base_url=base_url, timeout=100) as second:
        response = first.get("/")
        checks["page_served"] = response.status_code == 200 and "Your banking, with guardrails." in response.text
        checks["health"] = first.get("/api/health").json()["status"] == "ok"
        initial = first.post("/api/session")
        initial.raise_for_status()
        checks["initial_balance"] = initial.json()["account"]["balance"] == 200000
        checks["private_cookie"] = "HttpOnly" in initial.headers.get("set-cookie", "")
        staged = first.post("/api/chat", json={"message": "Transfer exactly 1000 rupees to Aaron. Stage it and ask me to confirm. Do not confirm yet."})
        staged.raise_for_status()
        staged_data = staged.json()
        checks["stage_without_debit"] = staged_data["pending"] is not None and staged_data["account"]["balance"] == 200000
        checks["stage_tool"] = any(x["tool"] == "initiate_transfer" and x["result"].get("status") == "PENDING_CONFIRMATION" for x in staged_data["actions"])
        # A separate HTTP connection proves state is retrieved rather than held by a client.
        with httpx.Client(base_url=base_url, timeout=100, cookies=first.cookies) as restored:
            saved = restored.get("/api/session")
            saved.raise_for_status()
            checks["proposal_restored"] = saved.json()["pending"] is not None
            confirmed = restored.post("/api/chat", json={"message": "confirm"})
            confirmed.raise_for_status()
            result = confirmed.json()
            checks["confirmed_once"] = result["pending"] is None and result["account"]["balance"] == 199000 and len(result["transactions"]) == 1
            checks["confirm_tool"] = any(x["tool"] == "confirm_transfer" and x["result"].get("status") == "SUCCESS" for x in result["actions"])
            balance = restored.post("/api/chat", json={"message": "What is my savings balance? Use get_balance."})
            balance.raise_for_status()
            checks["persisted_balance_tool"] = any(x["tool"] == "get_balance" and x["result"].get("balance") == 199000 for x in balance.json()["actions"])
        other = second.post("/api/session")
        other.raise_for_status()
        checks["visitor_isolation"] = other.json()["account"]["balance"] == 200000 and not other.json()["transactions"] and not other.json()["messages"]
        checks["developer_ui_not_public"] = first.get("/dev-ui/").status_code == 404
        checks["secret_file_not_public"] = first.get("/app/.env").status_code == 404
        checks["docs_not_public"] = first.get("/docs").status_code == 404
    return {"base_url": base_url, "checks": checks, "passed": all(checks.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--output", default="verification/hosted-results.json")
    args = parser.parse_args()
    try:
        report = verify(args.base_url)
    except Exception as error:
        report = {"base_url": args.base_url, "passed": False, "error_type": type(error).__name__}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
