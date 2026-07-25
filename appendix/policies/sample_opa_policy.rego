# ---------------------------------------------------------------------------
# SURETY - dynamic exposure cap enforcement
# Evaluated in-path on every agent-initiated transaction.
# Risk scores are probabilities on a 0.00-1.00 scale (0 = safest, 1 = riskiest).
# Input: { agent_id, transaction_amount, exposure_limit, risk_score,
#          risk_threshold, risk_tier }
# ---------------------------------------------------------------------------
package surety.enforcement

import future.keywords.if

# Deny by default. Only an explicit allow rule permits a transaction.
default allow := false

# Scores at or above 0.90 are never auto-approved, whatever the headroom.
default requires_human_approval := false

# Allow: the amount is inside the agent's current cap, the score is below the
# decline threshold (Gold or Silver), and no escalation is pending.
allow if {
	input.transaction_amount <= input.exposure_limit
	input.risk_score < input.risk_threshold
	not requires_human_approval
}

# Escalation: an extreme score forces an underwriter decision. The cap governs
# how large a loss can be; the score governs whether to trust the agent at all.
requires_human_approval if {
	input.risk_score >= 0.90
}

# Denial: the agent has crossed into Bronze and the amount breaches its cap.
deny_reason := msg if {
	input.risk_score >= input.risk_threshold
	input.transaction_amount > input.exposure_limit
	msg := sprintf(
		"DENIED: agent %v scored %v against a %v threshold (tier %v). Rs %v exceeds its Rs %v per-transaction exposure limit by Rs %v.",
		[
			input.agent_id, input.risk_score, input.risk_threshold, input.risk_tier,
			input.transaction_amount, input.exposure_limit,
			input.transaction_amount - input.exposure_limit,
		],
	)
}

# Escalation message, emitted instead of a hard denial.
deny_reason := msg if {
	requires_human_approval
	msg := sprintf(
		"ESCALATED: agent %v scored %v. Underwriter approval required before authorisation.",
		[input.agent_id, input.risk_score],
	)
}
