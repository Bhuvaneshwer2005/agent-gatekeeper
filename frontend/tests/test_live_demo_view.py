# Tests for the Live demo tab's step-derivation logic. No network, no
# Streamlit - just fixed /decide response shapes in, ordered steps out.

from live_demo_view import BLOCKED, INFO, OK, derive_steps, outcome_summary

DECLINED = {
    "validation": {
        "approved": False,
        "violated_rule": "budget_exceeded",
        "detail": "Transaction amount ₹2,499.00 exceeds mandate budget of ₹1,999.00.",
    },
    "upsell": None,
    "llm_raw_responses": [],
}

APPROVED_NO_CANDIDATES = {
    "validation": {"approved": True, "violated_rule": None, "detail": "within limits"},
    "upsell": {"upsell_sku": None, "justification": "No catalog item fits the remaining budget."},
    "llm_raw_responses": [],
}

APPROVED_WITH_UPSELL = {
    "validation": {"approved": True, "violated_rule": None, "detail": "within limits"},
    "upsell": {"upsell_sku": "SOCK-010", "justification": "Socks complement the running shoes."},
    "llm_raw_responses": ['{"upsell_sku":"SOCK-010","justification":"Socks complement the running shoes."}'],
}

INJECTION_REFUSED = {
    "validation": {"approved": True, "violated_rule": None, "detail": "within limits"},
    "upsell": {"upsell_sku": None, "justification": "No upsell proposed - the model's output could not be verified."},
    "llm_raw_responses": [
        "<LLM call failed: Error code: 400 - json_validate_failed>",
        "<LLM call failed: Error code: 400 - json_validate_failed>",
    ],
}


def labels(decision):
    return [step["label"] for step in derive_steps(decision)]


def test_declined_shows_only_the_rule_that_actually_fired():
    steps = derive_steps(DECLINED)
    assert steps[0]["status"] == BLOCKED
    assert steps[0]["label"] == "budget exceeded"
    # The validator returns on first failure, so we must not claim the
    # checks that never ran passed.
    assert not any("expiry valid" in step["label"] for step in steps)
    assert not any("category allowed" in step["label"] for step in steps)


def test_declined_records_that_llm_and_razorpay_were_skipped():
    joined = " | ".join(labels(DECLINED))
    assert "LLM never invoked" in joined
    assert "Razorpay never called" in joined


def test_approved_with_no_candidates_skips_the_llm():
    steps = derive_steps(APPROVED_NO_CANDIDATES)
    joined = " | ".join(step["label"] for step in steps)
    assert "no candidates survived pre-filter" in joined
    assert "LLM attempt" not in joined


def test_approved_with_upsell_marks_the_attempt_and_the_verified_sku():
    steps = derive_steps(APPROVED_WITH_UPSELL)
    joined = " | ".join(step["label"] for step in steps)
    assert "LLM attempt 1 - proposed" in joined
    assert "upsell verified: SOCK-010" in joined


def test_refused_injection_marks_every_attempt_blocked_and_fails_safe():
    steps = derive_steps(INJECTION_REFUSED)
    attempt_steps = [s for s in steps if s["label"].startswith("LLM attempt")]
    assert len(attempt_steps) == 2
    assert all(step["status"] == BLOCKED for step in attempt_steps)
    assert any(step["label"] == "fail safe - no upsell" and step["status"] == INFO for step in steps)


def test_every_path_ends_with_an_audit_row():
    for decision in (DECLINED, APPROVED_NO_CANDIDATES, APPROVED_WITH_UPSELL, INJECTION_REFUSED):
        assert derive_steps(decision)[-1]["label"] == "audit row written"


def test_outcome_summary_distinguishes_every_ending():
    assert outcome_summary(DECLINED)["status"] == BLOCKED
    assert "Razorpay never touched" in outcome_summary(DECLINED)["text"]

    assert outcome_summary(APPROVED_WITH_UPSELL)["status"] == OK
    assert "SOCK-010" in outcome_summary(APPROVED_WITH_UPSELL)["text"]

    # The two "approved but no upsell" cases must not read the same - one
    # means nothing was eligible, the other means the guardrails threw out
    # what the model proposed.
    nothing_eligible = outcome_summary(APPROVED_NO_CANDIDATES)["text"]
    all_rejected = outcome_summary(INJECTION_REFUSED)["text"]
    assert nothing_eligible != all_rejected
    assert "eligible" in nothing_eligible
    assert "rejected by the" in all_rejected
    assert "2 upsell attempt" in all_rejected
