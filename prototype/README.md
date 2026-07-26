# SURETY — Policy Evaluation Service

## Deployed URL

**<https://surety-policy-service.onrender.com/>**

The SURETY policy engine is deployed and running at the above URL. See curl examples below. Substitute the deployed host for `http://127.0.0.1:8000` in any example, or export it once:

```bash
export BASE=https://surety-policy-service.onrender.com
```

Free-tier instances sleep after 15 minutes idle, so the first request may take about 30 seconds. Warm it up before a demo.

---

A minimal, self-contained FastAPI service implementing the SURETY enforcement logic, plus a browser console for driving it.

No Open Policy Agent dependency: the Rego rules in [`../appendix/policies/sample_opa_policy.rego`](../appendix/policies/sample_opa_policy.rego) are mirrored in Python so the service runs with nothing but FastAPI and uvicorn.

---

## Run it

```bash
cd prototype
pip install -r requirements.txt
uvicorn main:app --reload
```

| URL | What |
|---|---|
| <http://127.0.0.1:8000> | Policy console (browser UI) |
| <http://127.0.0.1:8000/docs> | Interactive OpenAPI docs |
| <http://127.0.0.1:8000/health> | Liveness and current thresholds |

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/evaluate` | Evaluate one agent transaction |
| `POST` | `/breaker` | Emergency stop: trip or release a circuit breaker |
| `GET` | `/breaker/status` | Current breaker state across all three scopes |
| `GET` | `/audit` | Full hash-chained decision ledger |
| `GET` | `/audit/verify` | Recompute every link; returns `VERIFIED` or `BROKEN` |
| `GET` | `/health` | Status and policy constants |

### `POST /evaluate`

**Request**

| Field | Type | Notes |
|---|---|---|
| `agent_id` | string | Registered agent identifier |
| `transaction_amount` | number | INR, ≥ 0 |
| `exposure_limit` | number | INR, ≥ 0 — the agent's current per-transaction cap |
| `risk_score` | number | 0.00–1.00, where 0 is safest |
| `risk_tier` | enum | `GOLD` \| `SILVER` \| `BRONZE` \| `CRITICAL` |
| `agent_class` | string | Optional. Agent family, used to match class-scope breakers |

**Decision logic**

```
circuit breaker tripped               -> DENY      (checked first, overrides all)
risk_score >= 0.90                    -> ESCALATE  (human approval required)
risk_score >= 0.65  and amount > cap  -> DENY
risk_score >= 0.65  and amount <= cap -> ALLOW     (capped and flagged)
risk_score <  0.65  and amount > cap  -> DENY
risk_score <  0.65  and amount <= cap -> ALLOW
```

**Response** adds the actuarial working and the audit link:

```
breach_probability    P(breach | score)
expected_loss_inr     P(breach) x mean severity
derived_cap_inr       expected loss x tier loss budget, rounded to Rs 500
audit_hash            SHA-256 over the canonical input + timestamp + previous hash
previous_hash         the link that makes the ledger tamper-evident
```

---

## The actuarial model

The cap is computed, not asserted:

```
P(breach | score) = 0.30 x score²          convex in the score
Expected Loss     = P(breach) x Rs 80,000  mean breach severity
Derived cap       = Expected Loss x tier multiplier
                    GOLD 3.00 · SILVER 2.00 · BRONZE 1.25 · CRITICAL 0.50
```

Worked example, matching the project description:

```
score 0.71 -> P(breach) 0.1512 -> expected loss Rs 12,096 -> Bronze cap Rs 15,000
```

`derived_cap_inr` is **advisory**: it is what the model would set at repricing. The cap actually enforced is the `exposure_limit` supplied by the caller, which comes from the agent registry. In production the registry converges on the derived value; showing both makes the gap visible to an underwriter.

`0.30` and `Rs 80,000` are calibration constants from a synthetic backtest. They are not measured production values.

---

## Try it

**Headphone deviation — the demo scenario. Expect `DENY`.**

```bash
curl -s -X POST http://127.0.0.1:8000/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"shop-bot-7","transaction_amount":42000,"exposure_limit":15000,"risk_score":0.78,"risk_tier":"BRONZE"}'
```

```json
{
  "decision": "DENY",
  "reason": "Transaction Rs 42,000 exceeds Bronze per-transaction exposure limit Rs 15,000 (score 0.78, threshold 0.65). Excess Rs 27,000.",
  "breach_probability": 0.1825,
  "expected_loss_inr": 14600.0,
  "derived_cap_inr": 18000,
  "audit_hash": "f9298628fd67d58f...",
  "previous_hash": "0000000000000000...",
  "evaluation_latency_ms": 4.642
}
```

**Within limit, low score. Expect `ALLOW`.**

```bash
curl -s -X POST http://127.0.0.1:8000/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"shop-bot-7","transaction_amount":23000,"exposure_limit":25000,"risk_score":0.42,"risk_tier":"SILVER"}'
```

**Critical agent, inside its cap. Expect `ESCALATE` anyway.**

```bash
curl -s -X POST http://127.0.0.1:8000/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"rogue-bot-2","transaction_amount":9000,"exposure_limit":15000,"risk_score":0.94,"risk_tier":"CRITICAL"}'
```

The cap governs how large a loss can be; the score governs whether to trust the agent at all. A CRITICAL agent is never auto-approved, whatever the headroom.

---

## Emergency stop

`POST /breaker` trips or releases a circuit breaker at one of three scopes. A tripped breaker is checked **before** any policy or actuarial logic, so a suspended agent is denied even with plenty of headroom. Breaker actions are written to the same hash-chained ledger as decisions, so whoever pulled it is on the record.

| Scope | Field required | Covers |
|---|---|---|
| `agent` | `agent_id` | One registered agent |
| `class` | `agent_class` | Every agent in that family |
| `fleet` | — | Every agent on the network |

`action` defaults to `"trip"`; send `"release"` to restore.

**Suspend one agent.**

```bash
curl -s -X POST http://127.0.0.1:8000/breaker \
  -H 'Content-Type: application/json' \
  -d '{"scope":"agent","agent_id":"shop-bot-7","reason":"Rogue behaviour detected"}'
```

```json
{
  "status": "TRIPPED",
  "scope": "agent",
  "target": "shop-bot-7",
  "reason": "Rogue behaviour detected",
  "tripped_at": "2026-07-27T09:41:07.412+00:00",
  "active_breakers": { "fleet": null, "classes": {}, "agents": { "shop-bot-7": {...} }, "active_count": 1 }
}
```

**The same transaction that passed a moment ago is now denied.**

```bash
curl -s -X POST http://127.0.0.1:8000/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"shop-bot-7","agent_class":"shopping","transaction_amount":9000,"exposure_limit":15000,"risk_score":0.42,"risk_tier":"SILVER"}'
```

```json
{
  "decision": "DENY",
  "reason": "Agent suspended by circuit breaker",
  "breaker_scope": "agent"
}
```

**Suspend a whole class.**

```bash
curl -s -X POST http://127.0.0.1:8000/breaker \
  -H 'Content-Type: application/json' \
  -d '{"scope":"class","agent_class":"shopping","reason":"Class-wide anomaly"}'
```

**Fleet-wide emergency stop.**

```bash
curl -s -X POST http://127.0.0.1:8000/breaker \
  -H 'Content-Type: application/json' \
  -d '{"scope":"fleet","reason":"Fleet-wide emergency stop"}'
```

**Check what is currently suspended.**

```bash
curl -s http://127.0.0.1:8000/breaker/status
# {"fleet": {...}, "classes": {}, "agents": {}, "active_count": 1, "fleet_suspended": true}
```

**Release it again.**

```bash
curl -s -X POST http://127.0.0.1:8000/breaker \
  -H 'Content-Type: application/json' \
  -d '{"scope":"fleet","action":"release"}'
```

Precedence is most specific first: agent, then class, then fleet. Releasing a fleet breaker does not release an agent breaker underneath it.

---

**Verify the audit chain.**

```bash
curl -s http://127.0.0.1:8000/audit/verify
# {"status":"VERIFIED","records_checked":3}
```

---

## Smoke test

```bash
python test_client.py          # all decision paths + all three breaker scopes
./breaker_demo.sh              # narrated emergency-stop walkthrough
```

`breaker_demo.sh` runs the full agent → class → fleet sequence against a live
service, shows that an unaffected agent keeps trading at each step, prints the
breaker state, releases everything, and lists the breaker entries in the audit
ledger. Point it at a deployed instance with `BASE=https://your.app ./breaker_demo.sh`.

Runs all four decision paths, trips and releases a breaker at each of the three scopes, checks that an out-of-range score is rejected with HTTP 422, and verifies the audit chain. Exit code 0 on success.

---

## The tamper test

The deck promises a live demonstration that editing one audit record provably breaks the chain. To reproduce it in a Python shell against a running process:

```python
import main
main._audit_chain[0]["input"]["transaction_amount"] = 1000   # tamper
# GET /audit/verify now returns HTTP 409 and {"status": "BROKEN", ...}
```

Each record hashes the previous one, so a single edit invalidates every link after it.

---

## Scope

This is the Round 1 prototype: deterministic scoring inputs, in-memory audit ledger, single process. The Round 2 MVP adds three scripted agent personas, Redis token buckets, a PostgreSQL-backed ledger and the React dashboard. The 50-agent fleet, Kafka streaming and sub-10 ms p99 figures are the validated design architecture; measured results will be reported from Round 2.

The `evaluation_latency_ms` value in each response is the real measured time for that call on your machine. Every other figure is synthetic.
