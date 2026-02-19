package aegis.main

# ═══════════════════════════════════════════════════════
#  OPA Policy Unit Tests for AEGIS
#  Run with: opa test policies/ -v
# ═══════════════════════════════════════════════════════

# ── Helper: base valid input ──

base_input := {
    "agent_id": "agent-001",
    "agent_type": "sales",
    "service_name": "openai",
    "action": "read",
    "trust_score": 50.0,
    "current_hour": 12,
    "current_minute": 30,
    "time_window_start": "00:00",
    "time_window_end": "23:59",
    "allowed_actions": ["read", "write"],
    "max_requests_per_hour": 100,
    "current_hour_requests": 10,
    "wallet_balance": 50.0,
    "estimated_cost": 1.0,
    "requires_hitl": false,
}

# ═══════════════════════════════════════════════════════
#  ALLOW — Happy Path
# ═══════════════════════════════════════════════════════

test_allow_valid_request if {
    allow with input as base_input
}

test_allow_at_exact_start_of_window if {
    allow with input as object.union(base_input, {
        "current_hour": 9,
        "current_minute": 0,
        "time_window_start": "09:00",
        "time_window_end": "17:00",
    })
}

test_allow_at_exact_end_of_window if {
    allow with input as object.union(base_input, {
        "current_hour": 17,
        "current_minute": 0,
        "time_window_start": "09:00",
        "time_window_end": "17:00",
    })
}

test_allow_minimum_trust if {
    allow with input as object.union(base_input, {"trust_score": 10.0})
}

test_allow_exact_balance if {
    allow with input as object.union(base_input, {
        "wallet_balance": 1.0,
        "estimated_cost": 1.0,
    })
}

test_allow_zero_cost if {
    allow with input as object.union(base_input, {
        "wallet_balance": 0.0,
        "estimated_cost": 0.0,
    })
}

test_allow_high_trust_bypasses_hitl if {
    allow with input as object.union(base_input, {
        "requires_hitl": true,
        "trust_score": 85.0,
    })
}

# ═══════════════════════════════════════════════════════
#  DENY — Action Not Allowed
# ═══════════════════════════════════════════════════════

test_deny_action_not_in_list if {
    not allow with input as object.union(base_input, {
        "action": "delete",
        "allowed_actions": ["read", "write"],
    })
}

test_deny_empty_allowed_actions if {
    not allow with input as object.union(base_input, {
        "allowed_actions": [],
    })
}

test_deny_reasons_include_action if {
    reasons := deny_reasons with input as object.union(base_input, {
        "action": "delete",
        "allowed_actions": ["read"],
    })
    count(reasons) > 0
}

# ═══════════════════════════════════════════════════════
#  DENY — Time Window
# ═══════════════════════════════════════════════════════

test_deny_before_window if {
    not allow with input as object.union(base_input, {
        "current_hour": 8,
        "current_minute": 59,
        "time_window_start": "09:00",
        "time_window_end": "17:00",
    })
}

test_deny_after_window if {
    not allow with input as object.union(base_input, {
        "current_hour": 17,
        "current_minute": 1,
        "time_window_start": "09:00",
        "time_window_end": "17:00",
    })
}

test_deny_reasons_include_time_window if {
    reasons := deny_reasons with input as object.union(base_input, {
        "current_hour": 3,
        "current_minute": 0,
        "time_window_start": "09:00",
        "time_window_end": "17:00",
    })
    some r in reasons
    contains(r, "time window")
}

# ═══════════════════════════════════════════════════════
#  DENY — Rate Limit
# ═══════════════════════════════════════════════════════

test_deny_at_rate_limit if {
    not allow with input as object.union(base_input, {
        "current_hour_requests": 100,
        "max_requests_per_hour": 100,
    })
}

test_deny_over_rate_limit if {
    not allow with input as object.union(base_input, {
        "current_hour_requests": 101,
        "max_requests_per_hour": 100,
    })
}

test_allow_under_rate_limit if {
    allow with input as object.union(base_input, {
        "current_hour_requests": 99,
        "max_requests_per_hour": 100,
    })
}

test_deny_reasons_include_rate_limit if {
    reasons := deny_reasons with input as object.union(base_input, {
        "current_hour_requests": 200,
        "max_requests_per_hour": 100,
    })
    some r in reasons
    contains(r, "Rate limit")
}

# ═══════════════════════════════════════════════════════
#  DENY — Wallet
# ═══════════════════════════════════════════════════════

test_deny_insufficient_balance if {
    not allow with input as object.union(base_input, {
        "wallet_balance": 0.5,
        "estimated_cost": 1.0,
    })
}

test_deny_zero_balance_with_cost if {
    not allow with input as object.union(base_input, {
        "wallet_balance": 0.0,
        "estimated_cost": 0.01,
    })
}

test_deny_reasons_include_funds if {
    reasons := deny_reasons with input as object.union(base_input, {
        "wallet_balance": 0.0,
        "estimated_cost": 5.0,
    })
    some r in reasons
    contains(r, "Insufficient funds")
}

# ═══════════════════════════════════════════════════════
#  DENY — Trust Score
# ═══════════════════════════════════════════════════════

test_deny_trust_below_minimum if {
    not allow with input as object.union(base_input, {
        "trust_score": 9.9,
    })
}

test_deny_zero_trust if {
    not allow with input as object.union(base_input, {
        "trust_score": 0.0,
    })
}

test_deny_reasons_include_trust if {
    reasons := deny_reasons with input as object.union(base_input, {
        "trust_score": 5.0,
    })
    some r in reasons
    contains(r, "Trust too low")
}

# ═══════════════════════════════════════════════════════
#  HITL — Human-in-the-Loop Triggers
# ═══════════════════════════════════════════════════════

test_hitl_required_low_trust if {
    requires_hitl with input as object.union(base_input, {
        "requires_hitl": true,
        "trust_score": 50.0,
    })
}

test_hitl_not_required_high_trust if {
    not requires_hitl with input as object.union(base_input, {
        "requires_hitl": true,
        "trust_score": 85.0,
    })
}

test_hitl_high_cost_low_trust if {
    requires_hitl with input as object.union(base_input, {
        "estimated_cost": 10.0,
        "trust_score": 60.0,
    })
}

test_hitl_high_cost_high_trust_no_hitl if {
    not requires_hitl with input as object.union(base_input, {
        "estimated_cost": 10.0,
        "trust_score": 75.0,
    })
}

test_hitl_delete_low_trust if {
    requires_hitl with input as object.union(base_input, {
        "action": "delete",
        "trust_score": 50.0,
    })
}

test_hitl_delete_high_trust_no_hitl if {
    not requires_hitl with input as object.union(base_input, {
        "action": "delete",
        "trust_score": 95.0,
    })
}

test_hitl_blocks_allow if {
    not allow with input as object.union(base_input, {
        "requires_hitl": true,
        "trust_score": 50.0,
    })
}

# ═══════════════════════════════════════════════════════
#  DENY — Multiple Violations
# ═══════════════════════════════════════════════════════

test_multiple_deny_reasons if {
    reasons := deny_reasons with input as object.union(base_input, {
        "action": "delete",
        "allowed_actions": ["read"],
        "trust_score": 5.0,
        "wallet_balance": 0.0,
        "estimated_cost": 10.0,
        "current_hour_requests": 999,
        "max_requests_per_hour": 10,
        "current_hour": 3,
        "current_minute": 0,
        "time_window_start": "09:00",
        "time_window_end": "17:00",
    })
    count(reasons) == 5
}

# ═══════════════════════════════════════════════════════
#  Edge Cases
# ═══════════════════════════════════════════════════════

test_midnight_window if {
    allow with input as object.union(base_input, {
        "current_hour": 0,
        "current_minute": 0,
        "time_window_start": "00:00",
        "time_window_end": "23:59",
    })
}

test_time_to_minutes_helper if {
    time_to_minutes("09:30") == 570
}

test_time_to_minutes_midnight if {
    time_to_minutes("00:00") == 0
}

test_time_to_minutes_end_of_day if {
    time_to_minutes("23:59") == 1439
}
