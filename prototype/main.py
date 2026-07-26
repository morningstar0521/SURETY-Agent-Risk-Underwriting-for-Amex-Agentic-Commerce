"""
SURETY - Agent Risk Underwriting for Amex Agentic Commerce
Policy evaluation service.

A minimal, self-contained FastAPI application implementing the SURETY
enforcement logic. No external Open Policy Agent dependency: the Rego rules in
../appendix/policies/sample_opa_policy.rego are mirrored here in Python so the
service runs with nothing but FastAPI and uvicorn installed.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload
    open http://127.0.0.1:8000
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

POLICY_VERSION = "surety.enforcement/v4.2"

# Risk scores are probabilities on a 0.00-1.00 scale (0 = safest, 1 = riskiest).
DECLINE_THRESHOLD = 0.65   # Bronze boundary
ESCALATION_THRESHOLD = 0.90  # CRITICAL: human approval regardless of headroom

# --- Actuarial model -------------------------------------------------------
# Expected Loss = P(breach | score) x mean severity.
# P(breach) is convex in the score: a small rise near the threshold moves the
# expected loss much more than the same rise at the safe end of the scale.
# BREACH_K and MEAN_SEVERITY_INR are calibration constants fitted on the
# synthetic backtest described in the project description. They are not
# measured production values.
BREACH_K = 0.30
MEAN_SEVERITY_INR = 80_000.0

# Tier loss-budget multipliers. The derived cap is the exposure the network is
# willing to carry given the expected loss on this agent at this score.
TIER_MULTIPLIER = {"GOLD": 3.00, "SILVER": 2.00, "BRONZE": 1.25, "CRITICAL": 0.50}

TIER_BOUNDS = [(0.30, "GOLD"), (0.65, "SILVER"), (0.90, "BRONZE")]


def breach_probability(score: float) -> float:
    """P(breach | score). Convex, clamped to [0, 1]."""
    return round(min(1.0, max(0.0, BREACH_K * score * score)), 4)


def expected_loss(score: float) -> float:
    """Expected loss in INR for a single transaction at this score."""
    return round(breach_probability(score) * MEAN_SEVERITY_INR, 2)


def derived_cap(score: float, tier: str) -> int:
    """
    Per-transaction exposure cap implied by the expected loss and the tier
    loss budget, rounded to the nearest INR 500.

    Worked example from the project description:
        score 0.71 -> P(breach) 0.1512 -> expected loss INR 12,096
        Bronze multiplier 1.25         -> derived cap INR 15,000
    """
    raw = expected_loss(score) * TIER_MULTIPLIER.get(tier.upper(), 1.0)
    return int(round(raw / 500.0) * 500)


def tier_for_score(score: float) -> str:
    for bound, name in TIER_BOUNDS:
        if score < bound:
            return name
    return "CRITICAL"


# ---------------------------------------------------------------------------
# Hash-chained audit ledger (in-memory)
# ---------------------------------------------------------------------------

GENESIS_HASH = "0" * 64
_audit_chain: list[dict] = []


def _chain_hash(payload: dict, timestamp: str, previous_hash: str) -> str:
    """SHA-256 over the canonical input, the timestamp and the previous hash."""
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    material += "|" + timestamp + "|" + previous_hash
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _append_audit(payload: dict, decision: str, reason: str) -> tuple[str, str, str]:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    previous_hash = _audit_chain[-1]["audit_hash"] if _audit_chain else GENESIS_HASH
    audit_hash = _chain_hash(payload, timestamp, previous_hash)
    _audit_chain.append(
        {
            "sequence": len(_audit_chain) + 1,
            "timestamp": timestamp,
            "input": payload,
            "decision": decision,
            "reason": reason,
            "previous_hash": previous_hash,
            "audit_hash": audit_hash,
        }
    )
    return audit_hash, previous_hash, timestamp


# ---------------------------------------------------------------------------
# Circuit breakers (in-memory, three levels)
# ---------------------------------------------------------------------------
#
# Emergency stop. A tripped breaker short-circuits /evaluate before any policy
# or actuarial logic runs, so a suspended agent is denied even when it is well
# inside its exposure limit. Three scopes, checked most specific first:
#
#   agent  -> one registered agent
#   class  -> a family of agents (for example every "shopping" agent)
#   fleet  -> every agent on the network
#
_breakers: dict[str, object] = {
    "fleet": None,        # None, or the trip record
    "classes": {},        # agent_class -> trip record
    "agents": {},         # agent_id    -> trip record
}


def _trip_record(scope: str, target: Optional[str], reason: Optional[str]) -> dict:
    return {
        "scope": scope,
        "target": target,
        "reason": reason,
        "tripped_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }


def breaker_hit(agent_id: str, agent_class: Optional[str]) -> Optional[dict]:
    """Return the trip record suspending this agent, or None."""
    if agent_id in _breakers["agents"]:
        return _breakers["agents"][agent_id]
    if agent_class and agent_class in _breakers["classes"]:
        return _breakers["classes"][agent_class]
    if _breakers["fleet"]:
        return _breakers["fleet"]
    return None


# ---------------------------------------------------------------------------
# Agent registry (in-memory) - portfolio underwriting
# ---------------------------------------------------------------------------
#
# Per-transaction decisions answer "can this agent do this?". A portfolio view
# answers the underwriter's question: "what is the network's total expected
# loss right now, and can we afford to onboard another Bronze agent?"
#
# Pre-populated with the three agents from the demo scenario.
#
FLEET_LOSS_BUDGET_INR = 200_000.0   # max aggregate expected loss the network carries

_agent_registry: dict[str, dict] = {
    "shop-bot-7": {
        "agent_id": "shop-bot-7",
        "risk_score": 0.78,
        "tier": "Bronze",
        "exposure_limit": 15_000.0,
        "average_severity": 80_000.0,
    },
    "travel-bot-2": {
        "agent_id": "travel-bot-2",
        "risk_score": 0.42,
        "tier": "Silver",
        "exposure_limit": 25_000.0,
        "average_severity": 40_000.0,
    },
    "grocery-bot-5": {
        "agent_id": "grocery-bot-5",
        "risk_score": 0.18,
        "tier": "Gold",
        "exposure_limit": 50_000.0,
        "average_severity": 20_000.0,
    },
}

# Portfolio reserving uses P(breach) = risk_score directly, a deliberately
# conservative upper bound. The in-path decision model in /evaluate uses the
# calibrated convex curve (0.30 x score^2), which is lower. Reserving high and
# deciding tight is standard actuarial practice; both figures are reported so
# the difference is visible rather than hidden.
def portfolio_breach_probability(risk_score: float) -> float:
    """P(breach) for reserving. Conservative: equals the risk score."""
    return round(min(1.0, max(0.0, risk_score)), 4)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

Tier = Literal["GOLD", "SILVER", "BRONZE", "CRITICAL"]
Decision = Literal["ALLOW", "DENY", "ESCALATE"]
Scope = Literal["agent", "class", "fleet"]
BreakerAction = Literal["trip", "release"]


class EvaluateRequest(BaseModel):
    agent_id: str = Field(..., examples=["shop-bot-7"])
    transaction_amount: float = Field(..., ge=0, examples=[42000])
    exposure_limit: float = Field(..., ge=0, examples=[15000])
    risk_score: float = Field(..., ge=0.0, le=1.0, examples=[0.78])
    risk_tier: Tier = Field(..., examples=["BRONZE"])
    agent_class: Optional[str] = Field(
        None,
        description="Agent family, used to match class-scope circuit breakers.",
        examples=["shopping"],
    )


class BreakerRequest(BaseModel):
    scope: Scope = Field(..., examples=["fleet"])
    agent_id: Optional[str] = Field(None, examples=["shop-bot-7"])
    agent_class: Optional[str] = Field(None, examples=["shopping"])
    action: BreakerAction = Field(
        "trip", description="'trip' suspends, 'release' restores."
    )
    reason: Optional[str] = Field(None, examples=["Rogue behaviour detected"])


class BreakerResponse(BaseModel):
    status: str
    scope: Scope
    target: Optional[str]
    reason: Optional[str]
    tripped_at: Optional[str]
    active_breakers: dict


class EvaluateResponse(BaseModel):
    decision: Decision
    reason: str
    audit_hash: str
    previous_hash: str
    risk_score: float
    limit: float
    agent_id: str
    risk_tier: Tier
    risk_threshold: float = DECLINE_THRESHOLD
    breach_probability: float
    expected_loss_inr: float
    derived_cap_inr: int
    tier_implied_by_score: str
    breaker_scope: Optional[str] = None
    policy_version: str = POLICY_VERSION
    timestamp: str
    evaluation_latency_ms: float


# ---------------------------------------------------------------------------
# Core policy
# ---------------------------------------------------------------------------

def evaluate_policy(req: EvaluateRequest) -> tuple[str, str, Optional[str]]:
    """
    Mirrors surety.enforcement in Rego.

      0. circuit breaker tripped    -> DENY (checked first, overrides everything)
      1. score >= 0.90              -> ESCALATE (human approval)
      2. score >= 0.65 (Bronze):
           amount > limit           -> DENY
           otherwise                -> ALLOW
      3. score <  0.65 (Silver/Gold):
           amount > limit           -> DENY
           otherwise                -> ALLOW

    Returns (decision, reason, breaker_scope).
    """
    amount = req.transaction_amount
    limit = req.exposure_limit
    score = req.risk_score

    # 0. Emergency stop wins over every other rule, including headroom.
    trip = breaker_hit(req.agent_id, req.agent_class)
    if trip:
        return "DENY", "Agent suspended by circuit breaker", trip["scope"]

    if score >= ESCALATION_THRESHOLD:
        return (
            "ESCALATE",
            f"CRITICAL tier: human approval required. Agent {req.agent_id} scored "
            f"{score:.2f}, at or above the {ESCALATION_THRESHOLD:.2f} escalation "
            f"threshold. The Rs {amount:,.0f} request is held pending an "
            f"underwriter decision.",
            None,
        )

    if amount > limit:
        band = "Bronze" if score >= DECLINE_THRESHOLD else req.risk_tier.title()
        return (
            "DENY",
            f"Transaction Rs {amount:,.0f} exceeds {band} per-transaction exposure "
            f"limit Rs {limit:,.0f} (score {score:.2f}, threshold "
            f"{DECLINE_THRESHOLD:.2f}). Excess Rs {amount - limit:,.0f}.",
            None,
        )

    if score >= DECLINE_THRESHOLD:
        return (
            "ALLOW",
            f"Within the Rs {limit:,.0f} Bronze exposure limit. Agent {req.agent_id} "
            f"scored {score:.2f}, at or above the {DECLINE_THRESHOLD:.2f} threshold, "
            f"so the transaction is allowed but the agent stays capped and flagged.",
            None,
        )

    return (
        "ALLOW",
        f"Within the Rs {limit:,.0f} exposure limit and below the "
        f"{DECLINE_THRESHOLD:.2f} decline threshold (score {score:.2f}).",
        None,
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SURETY Policy Evaluation Service",
    description=(
        "Agent Risk Underwriting for Amex Agentic Commerce. "
        "Scores are 0.00-1.00. All figures are synthetic; latency values are "
        "design targets, not measured production results."
    ),
    version="0.1.0",
)

STATIC_DIR = Path(__file__).parent / "static"


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    started = time.perf_counter()
    decision, reason, breaker_scope = evaluate_policy(req)

    payload = req.model_dump()
    audit_hash, previous_hash, timestamp = _append_audit(payload, decision, reason)

    return EvaluateResponse(
        decision=decision,
        reason=reason,
        audit_hash=audit_hash,
        previous_hash=previous_hash,
        risk_score=req.risk_score,
        limit=req.exposure_limit,
        agent_id=req.agent_id,
        risk_tier=req.risk_tier,
        breach_probability=breach_probability(req.risk_score),
        expected_loss_inr=expected_loss(req.risk_score),
        derived_cap_inr=derived_cap(req.risk_score, req.risk_tier),
        tier_implied_by_score=tier_for_score(req.risk_score),
        breaker_scope=breaker_scope,
        timestamp=timestamp,
        evaluation_latency_ms=round((time.perf_counter() - started) * 1000, 3),
    )


@app.post("/breaker", response_model=BreakerResponse)
def breaker(req: BreakerRequest) -> BreakerResponse:
    """
    Emergency stop. Trip or release a circuit breaker at agent, class or fleet
    scope. A tripped breaker denies every subsequent /evaluate for the agents it
    covers, whatever their score or headroom.

    Every breaker action is written to the same hash-chained audit ledger as
    policy decisions, so the operator who pulled it is on the record.
    """
    scope = req.scope
    target = req.agent_id if scope == "agent" else req.agent_class if scope == "class" else None

    if scope == "agent" and not req.agent_id:
        raise HTTPException(422, "agent_id is required when scope is 'agent'")
    if scope == "class" and not req.agent_class:
        raise HTTPException(422, "agent_class is required when scope is 'class'")

    if req.action == "trip":
        record = _trip_record(scope, target, req.reason)
        if scope == "fleet":
            _breakers["fleet"] = record
        elif scope == "class":
            _breakers["classes"][target] = record
        else:
            _breakers["agents"][target] = record
        status = "TRIPPED"
    else:
        if scope == "fleet":
            _breakers["fleet"] = None
        elif scope == "class":
            _breakers["classes"].pop(target, None)
        else:
            _breakers["agents"].pop(target, None)
        record = {"scope": scope, "target": target, "reason": req.reason, "tripped_at": None}
        status = "RELEASED"

    _append_audit(
        req.model_dump(),
        f"BREAKER_{status}",
        f"Circuit breaker {status.lower()} at {scope} scope"
        + (f" for {target}" if target else " (fleet-wide)"),
    )

    return BreakerResponse(
        status=status,
        scope=scope,
        target=target,
        reason=req.reason,
        tripped_at=record["tripped_at"],
        active_breakers=breaker_state(),
    )


def breaker_state() -> dict:
    return {
        "fleet": _breakers["fleet"],
        "classes": _breakers["classes"],
        "agents": _breakers["agents"],
        "active_count": (
            (1 if _breakers["fleet"] else 0)
            + len(_breakers["classes"])
            + len(_breakers["agents"])
        ),
    }


@app.get("/breaker/status")
def breaker_status() -> JSONResponse:
    """Current circuit breaker state across all three scopes."""
    state = breaker_state()
    state["fleet_suspended"] = _breakers["fleet"] is not None
    return JSONResponse(state)


# ---------------------------------------------------------------------------
# Portfolio underwriting view
# ---------------------------------------------------------------------------

@app.get("/portfolio")
def portfolio() -> JSONResponse:
    """
    Aggregate expected loss across every registered agent.

        expected_loss(agent) = P(breach | score) x average_severity
        total_expected_loss  = sum over the fleet
        headroom             = fleet_loss_budget - total_expected_loss
        utilisation_pct      = total / budget x 100

    Also broken down by tier, so an underwriter can see which tier is
    consuming the loss budget. Read-only: this endpoint changes nothing.
    """
    agents = []
    tier_breakdown: dict[str, float] = {"Gold": 0.0, "Silver": 0.0, "Bronze": 0.0}
    total_expected_loss = 0.0

    for profile in _agent_registry.values():
        p_breach = portfolio_breach_probability(profile["risk_score"])
        el = round(p_breach * profile["average_severity"], 2)
        total_expected_loss += el

        tier = profile["tier"]
        tier_breakdown[tier] = round(tier_breakdown.get(tier, 0.0) + el, 2)

        agents.append({
            **profile,
            "breach_probability": p_breach,
            "expected_loss_inr": el,
            # what the in-path decision model would say, for comparison
            "decision_model_expected_loss_inr": expected_loss(profile["risk_score"]),
            "suspended": breaker_hit(profile["agent_id"], None) is not None,
        })

    total_expected_loss = round(total_expected_loss, 2)
    headroom = round(FLEET_LOSS_BUDGET_INR - total_expected_loss, 2)
    utilisation_pct = round((total_expected_loss / FLEET_LOSS_BUDGET_INR) * 100, 2)

    body = {
        "total_expected_loss": total_expected_loss,
        "fleet_loss_budget": FLEET_LOSS_BUDGET_INR,
        "headroom": headroom,
        "utilisation_pct": utilisation_pct,
        "tier_breakdown": tier_breakdown,
        "agent_count": len(agents),
        "agents": agents,
        "model_note": (
            "Portfolio reserving uses P(breach) = risk_score, a conservative "
            "upper bound. The in-path decision model uses 0.30 x score^2; both "
            "are reported per agent."
        ),
    }

    # A fleet-wide emergency stop does not change the numbers, but it does
    # change what they mean: no new exposure is being written right now.
    if _breakers["fleet"]:
        body["warning"] = (
            "Fleet emergency stop active. Portfolio values are informational."
        )

    return JSONResponse(body)


@app.get("/audit")
def audit_log() -> JSONResponse:
    """The hash-chained decision ledger, most recent last."""
    return JSONResponse({"records": _audit_chain, "count": len(_audit_chain)})


def _verify_chain() -> dict:
    """
    Recompute every link in the chain and return the result as a plain dict.

    Shared by GET /audit/verify and the tamper demo, so both report integrity
    through exactly the same code path.
    """
    previous = GENESIS_HASH
    for record in _audit_chain:
        expected = _chain_hash(record["input"], record["timestamp"], previous)
        if expected != record["audit_hash"] or record["previous_hash"] != previous:
            return {
                "status": "BROKEN",
                "broken_at_sequence": record["sequence"],
                "expected_hash": expected,
                "stored_hash": record["audit_hash"],
                "records_after_break": len(_audit_chain) - record["sequence"],
            }
        previous = record["audit_hash"]
    return {"status": "VERIFIED", "records_checked": len(_audit_chain)}


@app.get("/audit/verify")
def audit_verify() -> JSONResponse:
    """
    Recompute every link in the chain. Editing any stored record breaks it,
    which is the tamper test demonstrated in the deck.
    """
    result = _verify_chain()
    return JSONResponse(result, status_code=409 if result["status"] == "BROKEN" else 200)


# ---------------------------------------------------------------------------
# Live tamper test
# ---------------------------------------------------------------------------
#
# The deck claims that editing one audit record provably breaks the chain.
# Without this endpoint that claim can only be checked by opening a Python
# shell against a running process, which no reviewer will do. This runs the
# whole proof in one call and puts the chain back exactly as it was.
#
# It is a demonstration, not a back door: it can only overwrite one numeric
# field on one record, it always restores the original value, and every step
# is reported so nothing is hidden.

TAMPER_FIELD = "transaction_amount"
TAMPER_VALUE = 1_000.0

# Used only when the ledger is empty, so the demo works on a cold instance.
_SEED_DECISION = {
    "agent_id": "shop-bot-7",
    "transaction_amount": 42_000.0,
    "exposure_limit": 15_000.0,
    "risk_score": 0.78,
    "risk_tier": "BRONZE",
    "agent_class": "shopping",
}


@app.post("/audit/tamper-demo")
def audit_tamper_demo(sequence: int = 1) -> JSONResponse:
    """
    Prove the ledger is tamper-evident, in one call.

        1. verify the chain            -> VERIFIED
        2. edit one stored record      -> the hash no longer matches
        3. verify again                -> BROKEN, with the exact link that failed
        4. restore the original value
        5. verify again                -> VERIFIED

    `sequence` selects which record to tamper with (1-based, defaults to the
    first). The chain is always restored before the response is returned, so
    running this leaves the ledger exactly as it was found.
    """
    # A cold instance has an empty ledger. Seed one real decision so the demo
    # never depends on the reviewer having called /evaluate first.
    seeded = False
    if not _audit_chain:
        decision, reason, _ = evaluate_policy(EvaluateRequest(**_SEED_DECISION))
        _append_audit(dict(_SEED_DECISION), decision, reason)
        seeded = True

    if not 1 <= sequence <= len(_audit_chain):
        raise HTTPException(
            422,
            f"sequence must be between 1 and {len(_audit_chain)}; "
            f"the ledger currently holds {len(_audit_chain)} record(s).",
        )

    before = _verify_chain()
    if before["status"] != "VERIFIED":
        # Refuse to run the demo on a chain that is already broken: the result
        # would prove nothing.
        raise HTTPException(409, "Chain is already BROKEN; nothing to demonstrate.")

    record = _audit_chain[sequence - 1]
    if TAMPER_FIELD not in record["input"]:
        raise HTTPException(
            422,
            f"Record {sequence} has no '{TAMPER_FIELD}' field to tamper with. "
            f"Pick a decision record rather than a breaker record.",
        )

    original_value = record["input"][TAMPER_FIELD]

    # --- tamper ------------------------------------------------------------
    record["input"][TAMPER_FIELD] = TAMPER_VALUE
    after_tamper = _verify_chain()

    # --- restore -----------------------------------------------------------
    record["input"][TAMPER_FIELD] = original_value
    after_restore = _verify_chain()

    return JSONResponse(
        {
            "demo": "audit chain tamper test",
            "target_sequence": sequence,
            "field_tampered": f"input.{TAMPER_FIELD}",
            "original_value": original_value,
            "tampered_value": TAMPER_VALUE,
            "step_1_before": before,
            "step_2_after_tamper": after_tamper,
            "step_3_after_restore": after_restore,
            "chain_restored": after_restore["status"] == "VERIFIED",
            "seeded_demo_record": seeded,
            "explanation": (
                "Each record hashes its own input, its timestamp and the hash of "
                "the record before it. Changing one stored amount changes that "
                "record's recomputed hash, so the stored hash no longer matches "
                "and every link after it is invalidated too. Rewriting history "
                "in this ledger requires rewriting every record that followed."
            ),
        }
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "policy_version": POLICY_VERSION,
        "decline_threshold": DECLINE_THRESHOLD,
        "escalation_threshold": ESCALATION_THRESHOLD,
        "audit_records": len(_audit_chain),
        "active_breakers": breaker_state()["active_count"],
        "registered_agents": len(_agent_registry),
    }


@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
