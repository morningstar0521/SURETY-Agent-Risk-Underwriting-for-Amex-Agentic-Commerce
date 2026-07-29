# SURETY: Agent Risk Underwriting for Amex Agentic Commerce

**Exposure limits, claims-grade audit trails, and circuit breakers for registered financial AI agents.**

*Theme: Governance Layer for Financial Agents*

---

## 1. The Problem: Agentic Commerce Has Protection, But No Underwriting

When a Card Member's AI assistant overspends by ₹17,000 and weeks later they are still fighting a chargeback with no evidence, the promise of agentic commerce breaks. In April 2026, American Express launched the Agentic Commerce Experiences (ACE) Developer Kit and Amex Agent Purchase Protection: an industry-first commitment to protect Card Members from charges caused by registered agent errors. That promise is **strategically powerful - and actuarially incomplete**: without underwriting behind it, it is an open-ended liability.

Every insurer must price risk before accepting it, limit live exposure, and assemble evidence when things go wrong. No such layer exists for AI agents. **Industry proposals are fences: permissions, dashboards, kill switches.** They stop agents but cannot say how risky an agent is, who is liable when it errs, or where the evidence lives. Chargebacks are forecast to grow **24% to 324 million annually by 2028**, before agent commerce adds a new error class.

## 2. The Solution: SURETY, the Actuarial Governance Layer

SURETY does not just police agents: **it underwrites the agent before it acts, controls its exposure while it acts, and proves what happened when it fails.**

**Underwrite:** each agent's live risk score sets its terms: merchant categories, per-transaction and daily limits, escalation thresholds. **Control:** limits tighten as behavior drifts; circuit breakers halt one agent, a class, or the fleet instantly. **Prove:** every decision lands on a hash-chained, tamper-evident audit trail with counterfactual transparency, showing what would change the outcome ("at ₹23,000, this purchase would have been allowed"): mathematically fair, not a black box.

**The moment SURETY exists for:** a Card Member tells their shopping agent, "Buy noise-cancelling headphones under ₹25,000." The agent buys ₹42,000 studio headphones. In-flight, SURETY detects the intent deviation, tightens the agent's limits, and instantly generates the evidence a protection program needs to resolve the claim. **Protected in seconds, not weeks. A resolved claim, not a dashboard alert.**

On any breach, SURETY auto-assembles a **Claims Package**: authenticated intent, cart context, merchant data, transaction, decision trail, and score adjustment, aligned to Amex Chargeback reason codes. The Claims Package is not an afterthought - it is the **investigation engine** that turns the protection promise from manual inquiry into closed-loop, evidence-backed resolution.

Every automated decision is explainable and reversible by a **human operator**, ensuring SURETY accelerates governance without removing accountability.

## 3. Rubric Task Mapping

| # | Rubric task | SURETY implementation |
|---|---|---|
| 1 | Permission model with granular, configurable controls | Per-agent underwriting terms in tiers: Bronze (higher risk, tightest terms), Silver (medium), Gold (lowest risk, widest terms): action types, merchant categories, velocity, amount ceilings; operator-configurable, defaults from the live score. |
| 2 | Dynamic spend caps and budget limits enforced in real time | Exposure limits (per-transaction, daily, per-category) recomputed from the live risk score, enforced in-path via Open Policy Agent with Redis token buckets. |
| 3 | Revocation mechanism and emergency stop | **Three-level circuit breakers: agent, class, or fleet-wide emergency stop.** Revocation propagates in milliseconds; in-flight actions declined. |
| 4 | Operator-facing dashboard | Underwriter's risk console: fleet map by risk tier, live dollar exposure, policy editor, decision replay, audit browser, one-click breakers. |
| 5 | Test and optimize for enforcement accuracy, low latency, auditability | 50-agent simulated fleet with planted rogue behaviors, measuring precision/recall, latency (target sub-10ms p99), and a **live tamper test callable in one request on the deployed service (POST /audit/tamper-demo)**: editing any record breaks the hash chain and every record after it. |

## 4. Technical Approach

- Agent actions stream through Kafka into a feature extractor: intent deviation, baseline amount deviation, merchant-category entropy, velocity, decline/dispute history, time-pattern drift.
- SURETY ingests Intent Intelligence and Cart Context signals from the ACE kit as core features, and writes per-agent policy decisions back to the Agent Registration service: a closed governance loop in Amex's agentic architecture.
- An XGBoost model outputs the risk score on a 0.00-1.00 scale with explained feature contributions (e.g., intent deviation +0.20, amount anomaly +0.10), keeping every score auditable and its drivers clear to operators and regulators.
- The risk score is converted into an actuarial underwriting decision through an expected-loss model: **Expected Loss = P(breach | score) × mean severity**. The per-transaction exposure cap is derived from this expected loss and the agent's tier loss budget, **ensuring the cap is not asserted but computed.** For instance, a score of 0.71 with breach probability 0.15 and severity ₹80,000 gives an expected loss of ₹12,000, grounding the **Bronze cap of ₹15,000**.
- Scores map deterministically to tiers, limits, and permissions.
- A stateless FastAPI + Open Policy Agent path with Redis token buckets enforces terms in real time; allow/block/escalate decisions target sub-10ms at 10,000-agent scale.
- Audit logging is asynchronous: enforcement targets under 10ms while every decision is written to a hash-chained PostgreSQL ledger (each record stores the prior hash; tampering provable).
- On breach, SURETY auto-assembles the Claims Package; React console updates over WebSockets.
- Design aligns with the NIST AI RMF (Govern/Manage).
- **Live prototype.** A working policy service is deployed at **https://surety-policy-service.onrender.com/** : browser console, OpenAPI docs, POST /evaluate with the expected-loss working returned on every decision, POST /breaker for agent, class and fleet emergency stops, GET /portfolio for aggregate expected loss against the fleet loss budget, and a hash-chained audit ledger with a /audit/verify integrity check plus POST /audit/tamper-demo, which edits one stored record, reports the exact link that fails, and restores it in a single call.
- **Video walkthrough.** A short narrated run through the demo scenario against the deployed service: **https://drive.google.com/file/d/17leJ1A4_X2td4Gr2oiL1quxUGx249yxo/view**
- **Prototype Scope.** The Round 2 MVP implements a deterministic risk-scoring engine with 3 scripted agent personas, FastAPI enforcement with Redis token buckets, PostgreSQL hash-chained audit, and a React dashboard. XGBoost is trained and validated offline on synthetic data as a production extension path. The 50-agent fleet, Kafka streaming, and sub-10ms p99 targets are the validated design architecture; measured results will be reported from the Round 2 prototype.
- All training and simulation data is disclosed and synthetic; features transfer to production signals.

A detailed SURETY-ACE integration diagram is included in the accompanying presentation (Appendix A).

## 5. Business Value and Amex Alignment

SURETY converts governance from cost center to enabler of Amex's announced strategy. It de-risks agent purchase protection by capping each agent's maximum loss and pricing risk upfront. SURETY also tracks aggregate exposure across categories, classes, and the fleet, preventing systemic risk from individually valid transactions: **the prototype exposes this as GET /portfolio, reporting total expected loss, remaining headroom and utilisation against a fleet loss budget, broken down by tier.** Pre-assembled Claims Packages cut resolution time and claims cost. A strategic extension: **underwriting-as-a-service**, where developers earn a **"SURETY Certified"** trust tier priced by demonstrated behavior - trust as a marketable asset for the agentic economy, consistent with the American Express brand. Developers holding Gold-tier scores for 90 days earn the badge, unlocking higher default limits and reduced checkout friction - compliance becomes competitive advantage and recurring Amex revenue. For Card Members, SURETY is a control surface: visibility into agent intents and limits, risk-tier alerts, and one-tap suspension.

## 6. Innovation Summary

**Every other governance proposal builds a fence. SURETY builds the actuarial layer that decides how high each fence must be, prices the residual risk, and files the claim when the fence is breached.** The first network to underwrite autonomous transactions at scale does not just manage a risk: it owns a moat. SURETY is **the credit score for autonomous agents** - the trust metric that makes the agentic economy safe, transparent, and insurable.
