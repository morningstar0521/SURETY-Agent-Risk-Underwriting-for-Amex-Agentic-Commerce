SURETY - INTERFACE MOCKUPS
================================================================================

demo_slide_4_claim_resolution.png
    The moment SURETY detects an intent deviation and triggers protection, for
    the headphone overcharge scenario. Left: the authenticated Card Member
    instruction, "Buy noise-cancelling headphones under Rs 25,000", with the
    parsed ceiling and category. Right: the agent's executed Rs 42,000 studio
    headphone purchase, flagged as exceeding the intent limit. Centre: the three
    SURETY decision states - intent deviation detected, Agent Purchase
    Protection triggered, Claims Package assembled. Along the bottom: the
    enforcement timeline with per-step latency, a 2.3 second end-to-end
    resolution, and the agent's tightened exposure limit. Appears as Slide 4 of
    the deck.

dashboard_operator_console.png
    The live operator risk console. Left: the fleet map of 50 registered agents
    coloured by risk tier, with one throttled agent ringed in red. Right: total
    live exposure against the fleet ceiling, the policy decision latency
    distribution with its p99 marker, and the audit-chain integrity check
    reading VERIFIED. Bottom: tier breakdown and armed circuit-breaker levels.
    Appears as Slide 9 of the deck.

appendix_a_architecture.png
    The SURETY-ACE integration architecture. ACE Intent Intelligence and Cart
    Context feed SURETY as underwriting features; risk scoring, underwriting and
    enforcement, and Claims Package generation happen inside SURETY; policy
    decisions are written back to ACE Agent Registration, closing the governance
    loop. The Operator Dashboard and Card Member Portal sit downstream. Appears
    as Slide 10 of the deck.

--------------------------------------------------------------------------------
All mockups follow the SURETY design system: navy #0B1F3A field, Amex blue
#016FD0 for structure and data flow, gold #C8A951 reserved for money, triggers
and key decisions. Typeface: Inter.
