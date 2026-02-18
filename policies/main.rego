package aegis.main

# ── Defaults ──
default allow := false
default requires_hitl := false

# ── Helpers ──
time_to_minutes(t) := result if {
    parts := split(t, ":")
    result := to_number(parts[0]) * 60 + to_number(parts[1])
}

current_minutes := input.current_hour * 60 + input.current_minute

# ── Sub-policies ──
action_allowed if {
    input.action == input.allowed_actions[_]
}

within_time_window if {
    start_min := time_to_minutes(input.time_window_start)
    end_min := time_to_minutes(input.time_window_end)
    current_minutes >= start_min
    current_minutes <= end_min
}

within_rate_limit if {
    input.current_hour_requests < input.max_requests_per_hour
}

wallet_sufficient if {
    input.wallet_balance >= input.estimated_cost
}

trust_sufficient if {
    input.trust_score >= 10
}

# ── Main allow ──
allow if {
    action_allowed
    within_time_window
    within_rate_limit
    wallet_sufficient
    trust_sufficient
    not requires_hitl
}

# ── HITL triggers ──
requires_hitl if {
    input.requires_hitl == true
    input.trust_score < 80
}

requires_hitl if {
    input.estimated_cost > 5.0
    input.trust_score < 70
}

requires_hitl if {
    input.action == "delete"
    input.trust_score < 90
}

# ── Deny reasons ──
deny_reasons contains reason if {
    not action_allowed
    reason := sprintf("Action '%s' not in allowed: %v", [input.action, input.allowed_actions])
}

deny_reasons contains reason if {
    not within_time_window
    reason := sprintf("Outside time window %s-%s (current: %d min)",
        [input.time_window_start, input.time_window_end, current_minutes])
}

deny_reasons contains reason if {
    not within_rate_limit
    reason := sprintf("Rate limit: %d/%d requests this hour",
        [input.current_hour_requests, input.max_requests_per_hour])
}

deny_reasons contains reason if {
    not wallet_sufficient
    reason := sprintf("Insufficient funds: $%.4f < $%.4f",
        [input.wallet_balance, input.estimated_cost])
}

deny_reasons contains reason if {
    not trust_sufficient
    reason := sprintf("Trust too low: %.1f < 10.0", [input.trust_score])
}