================================================================================
SURETY - APPENDIX PACKAGE
================================================================================

Team:       Team SURETY
Project:    SURETY - Agent Risk Underwriting for Amex Agentic Commerce
Event:      CodeStreet 2026 - Governance Layer for Financial Agents
Submitted:  Round 1

--------------------------------------------------------------------------------
ABOUT THIS PACKAGE
--------------------------------------------------------------------------------

SURETY is the actuarial layer for agentic commerce. It scores every registered
agent continuously, converts that score into dynamic exposure caps, circuit-
breaks agents that breach their terms, and assembles claims-grade evidence for
every breach.

This appendix contains the supporting artefacts referenced in the Round 1
presentation deck: a sample enforcement policy, a sample Claims Package, the
business brief for the SURETY Certified program, and the interface mockups used
on Slides 4, 9 and 10.

All figures use the demo scenario carried through the deck: a Card Member
instructs their shopping agent to buy noise-cancelling headphones under
Rs 25,000; the agent attempts a Rs 42,000 studio headphone purchase; SURETY
detects the intent deviation in-flight and resolves the claim in 2.3 seconds.

--------------------------------------------------------------------------------
LIVE DEMO
--------------------------------------------------------------------------------

Live prototype: https://surety-policy-service.onrender.com/

    The SURETY policy engine is deployed and running at the address above.

        /                browser policy console
        /docs            interactive OpenAPI documentation
        /health          liveness and current policy thresholds
        /evaluate        POST, evaluate one agent transaction
        /breaker         POST, emergency stop at agent / class / fleet scope
        /breaker/status  GET, current breaker state
        /portfolio       GET, fleet-wide expected loss against the loss budget
        /audit/verify    GET, recompute the hash chain
        /audit/tamper-demo
                         POST, live tamper test: breaks one record, proves the
                         chain detects it, then restores it

    The instance is on a free tier and sleeps after 15 minutes idle, so the
    first request may take about 30 seconds to wake it.

--------------------------------------------------------------------------------
TABLE OF CONTENTS
--------------------------------------------------------------------------------

- Live prototype: https://surety-policy-service.onrender.com/

README.txt
    This file. Index of the appendix package.

policies/
    sample_opa_policy.rego
        Open Policy Agent rule set enforcing a dynamic per-transaction
        exposure cap, with a mandatory human-approval path for CRITICAL
        risk tier agents.

claims/
    sample_claims_package.json
        A complete Claims Package for the headphone overcharge scenario:
        Card Member intent, cart context, risk drivers, counterfactuals,
        policy decision and the hash-chained audit reference.

business/
    surety_certified_program.txt
        One-page brief for the SURETY Certified Agent trust-tier program:
        tier structure, qualification rules, developer benefits and the
        revenue case for American Express.

mockups/
    README.txt
        Short description of each mockup image.
    demo_slide_4_claim_resolution.png
        The Slide 4 demo view: intent deviation detected, protection
        triggered, Claims Package assembled.
    dashboard_operator_console.png
        The Slide 9 operator risk console: fleet map, live exposure,
        latency distribution and audit-chain verification.
    appendix_a_architecture.png
        The SURETY-ACE integration architecture diagram.

--------------------------------------------------------------------------------
NOTES
--------------------------------------------------------------------------------

1.  The SURETY-ACE integration architecture (Appendix A) appears as Slide 10 of
    the presentation deck and is also included here as a standalone PNG at
    mockups/appendix_a_architecture.png, for reviewers who prefer to read it
    outside the deck.

2.  Video walkthrough:  [Video Link]
    A short narrated run through the demo scenario end to end.

3.  Source repository:
    https://github.com/morningstar0521/SURETY-Agent-Risk-Underwriting-for-Amex-Agentic-Commerce
    Submission artefacts; prototype code, policy bundle, feature extractor
    and simulation harness to follow in Round 2.

4.  Currency figures are written as "Rs" in plain-text files and as the rupee
    symbol in the deck and mockups. Both refer to Indian Rupees.

5.  Latency figures quoted anywhere in this package are design targets for the
    Round 2 prototype, not measured production results. Round 2 will report
    measured precision, recall and p99 latency from the 50-agent simulated
    fleet described in the deck.

================================================================================
