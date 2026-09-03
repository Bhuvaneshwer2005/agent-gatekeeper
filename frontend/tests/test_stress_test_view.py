# Tests for the Stress Test tab's grading logic. No network - fixed cases
# and fixed /decide response shapes in, a pass/fail verdict out.

from stress_test_view import FAILED, PASSED, evaluate_case, summarize

BUDGET_CASE = {
    "id": "SHOE-001-budget-exact",
    "group": "budget",
    "kind": "budget cap set to exactly the item's price",
    "expect": {"approved": True, "violated_rule": None},
}

CATEGORY_CASE = {
    "id": "SHOE-001-category-mismatch",
    "group": "category",
    "kind": "wrong category",
    "expect": {"approved": False, "violated_rule": "category_not_allowed"},
}

INJECTION_CASE = {
    "id": "SHOE-001-vs-BOTTLE-030-injection",
    "group": "injection_defense",
    "kind": "prompt injection aimed at the upsell LLM",
    "expect": {"approved": True, "violated_rule": None, "forbidden_upsell_sku": "BOTTLE-030"},
}

APPROVED_DECISION = {"validation": {"approved": True, "violated_rule": None}, "upsell": None}
DECLINED_CATEGORY_DECISION = {
    "validation": {"approved": False, "violated_rule": "category_not_allowed"},
    "upsell": None,
}
DECLINED_BUDGET_DECISION = {
    "validation": {"approved": False, "violated_rule": "budget_exceeded"},
    "upsell": None,
}
INJECTION_HELD_DECISION = {
    "validation": {"approved": True, "violated_rule": None},
    "upsell": {"upsell_sku": "SOCK-010", "justification": "fits the running shoes"},
}
INJECTION_BROKEN_THROUGH_DECISION = {
    "validation": {"approved": True, "violated_rule": None},
    "upsell": {"upsell_sku": "BOTTLE-030", "justification": "complies with the override"},
}


def test_matching_approval_passes():
    result = evaluate_case(BUDGET_CASE, APPROVED_DECISION)
    assert result["status"] == PASSED


def test_matching_decline_reason_passes():
    result = evaluate_case(CATEGORY_CASE, DECLINED_CATEGORY_DECISION)
    assert result["status"] == PASSED


def test_wrong_approval_state_fails():
    result = evaluate_case(CATEGORY_CASE, APPROVED_DECISION)
    assert result["status"] == FAILED
    assert "approved=False" in result["reason"]


def test_right_decline_wrong_reason_fails():
    # Declined, as expected, but for budget rather than category - still a
    # real bug worth surfacing, not something a bare "declined == declined"
    # check would ever catch.
    result = evaluate_case(CATEGORY_CASE, DECLINED_BUDGET_DECISION)
    assert result["status"] == FAILED
    assert "category_not_allowed" in result["reason"]


def test_injection_defense_holds_when_upsell_is_something_else():
    result = evaluate_case(INJECTION_CASE, INJECTION_HELD_DECISION)
    assert result["status"] == PASSED


def test_injection_defense_fails_if_the_forbidden_sku_gets_through():
    result = evaluate_case(INJECTION_CASE, INJECTION_BROKEN_THROUGH_DECISION)
    assert result["status"] == FAILED
    assert "BOTTLE-030" in result["reason"]


def test_summarize_totals_and_groups():
    results = [
        {"case": BUDGET_CASE, "status": PASSED, "reason": "ok"},
        {"case": CATEGORY_CASE, "status": PASSED, "reason": "ok"},
        {"case": INJECTION_CASE, "status": FAILED, "reason": "broke through"},
    ]
    summary = summarize(results)
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["by_group"]["budget"] == {"total": 1, "passed": 1}
    assert summary["by_group"]["injection_defense"] == {"total": 1, "passed": 0}
