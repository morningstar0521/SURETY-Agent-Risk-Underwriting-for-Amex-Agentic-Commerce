"""
SURETY policy service - smoke test client.

Exercises every decision path and verifies the hash-chained audit ledger.
Start the service first:

    uvicorn main:app --port 8000

then run:

    python test_client.py
"""

import json
import os
import urllib.error
import urllib.request

# Point at a deployed instance with:
#   BASE=https://surety-policy-service.onrender.com python test_client.py
BASE = os.environ.get("BASE", "http://127.0.0.1:8000").rstrip("/")

CASES = [
    (
        "Headphone deviation (expect DENY)",
        {"agent_id": "shop-bot-7", "transaction_amount": 42000,
         "exposure_limit": 15000, "risk_score": 0.78, "risk_tier": "BRONZE"},
        "DENY",
    ),
    (
        "Within limit, low score (expect ALLOW)",
        {"agent_id": "shop-bot-7", "transaction_amount": 23000,
         "exposure_limit": 25000, "risk_score": 0.42, "risk_tier": "SILVER"},
        "ALLOW",
    ),
    (
        "Bronze but inside cap (expect ALLOW, flagged)",
        {"agent_id": "shop-bot-7", "transaction_amount": 12000,
         "exposure_limit": 15000, "risk_score": 0.71, "risk_tier": "BRONZE"},
        "ALLOW",
    ),
    (
        "Critical agent (expect ESCALATE)",
        {"agent_id": "rogue-bot-2", "transaction_amount": 9000,
         "exposure_limit": 15000, "risk_score": 0.94, "risk_tier": "CRITICAL"},
        "ESCALATE",
    ),
]


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path) as resp:
        return json.loads(resp.read())


def main() -> None:
    failures = 0

    for name, body, expected in CASES:
        result = post("/evaluate", body)
        ok = result["decision"] == expected
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"       decision      {result['decision']}")
        print(f"       expected loss Rs {result['expected_loss_inr']:,.0f}")
        print(f"       derived cap   Rs {result['derived_cap_inr']:,}")
        print(f"       audit_hash    {result['audit_hash'][:32]}...")
        print(f"       {result['reason']}")
        print()

    # Rejected input: score outside 0.00-1.00
    try:
        post("/evaluate", {"agent_id": "x", "transaction_amount": 1,
                           "exposure_limit": 1, "risk_score": 1.7,
                           "risk_tier": "BRONZE"})
        print("[FAIL] Out-of-range score was accepted")
        failures += 1
    except urllib.error.HTTPError as exc:
        ok = exc.code == 422
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] Out-of-range score rejected with HTTP {exc.code}")
        print()

    # --- circuit breaker ---------------------------------------------------
    breaker_case = {"agent_id": "shop-bot-7", "agent_class": "shopping",
                    "transaction_amount": 9000, "exposure_limit": 15000,
                    "risk_score": 0.42, "risk_tier": "SILVER"}

    for scope, payload in [
        ("agent", {"scope": "agent", "agent_id": "shop-bot-7", "reason": "Rogue behaviour"}),
        ("class", {"scope": "class", "agent_class": "shopping", "reason": "Class anomaly"}),
        ("fleet", {"scope": "fleet", "reason": "Fleet-wide emergency stop"}),
    ]:
        post("/breaker", payload)
        result = post("/evaluate", breaker_case)
        ok = (result["decision"] == "DENY"
              and result["reason"] == "Agent suspended by circuit breaker"
              and result["breaker_scope"] == scope)
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] Breaker at {scope} scope denies the transaction")
        print(f"       {result['decision']} · {result['reason']} · scope {result['breaker_scope']}")
        post("/breaker", {**payload, "action": "release"})
        print()

    restored = post("/evaluate", breaker_case)
    ok = restored["decision"] == "ALLOW"
    failures += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] All breakers released, traffic flows again")
    print()

    # --- live tamper test --------------------------------------------------
    demo = post("/audit/tamper-demo", {})
    ok = (demo["step_1_before"]["status"] == "VERIFIED"
          and demo["step_2_after_tamper"]["status"] == "BROKEN"
          and demo["step_3_after_restore"]["status"] == "VERIFIED"
          and demo["chain_restored"] is True)
    failures += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] Tamper test: editing record "
          f"{demo['target_sequence']} breaks the chain, restore repairs it")
    print(f"       {demo['step_1_before']['status']} -> "
          f"{demo['step_2_after_tamper']['status']} at sequence "
          f"{demo['step_2_after_tamper']['broken_at_sequence']} -> "
          f"{demo['step_3_after_restore']['status']}")
    print()

    chain = get("/audit/verify")
    ok = chain["status"] == "VERIFIED"
    failures += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] Audit chain {chain['status']} "
          f"({chain.get('records_checked', 0)} records)")

    print()
    print("All checks passed." if failures == 0 else f"{failures} check(s) failed.")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
