# Pure data-layer functions for the Stress Test tab: fetching the backend's
# generated case batch and grading each response against the expectation it
# already carries.
#
# Same split as live_demo_view.py - no Streamlit calls here, so grading is
# unit-testable with plain pytest. run_scenario() from live_demo_view is
# reused directly to run a case: a stress case is shaped exactly like a demo
# scenario (a mandate + a transaction), so there's no need for a second copy
# of the same POST-to-/decide logic.

from typing import Any, Dict, List

import httpx

PASSED = "passed"
FAILED = "failed"


def fetch_stress_cases(base_url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch the generated stress-test batch the backend built from the live catalog."""
    response = httpx.get(f"{base_url}/stress-cases", timeout=timeout)
    response.raise_for_status()
    return response.json()


def evaluate_case(case: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    """Grade one /decide response against the case's own expected outcome.

    Every case type - budget boundary, category mismatch, expiry, multi
    violation, injection defense - reduces to the same three checks: did
    approval match, did the decline reason match (when declined), and for
    the injection-defense cases specifically, did the forbidden SKU stay
    out of the upsell. No per-kind branching needed beyond that last,
    optional check.
    """
    expect = case["expect"]
    validation = decision.get("validation", {})
    actual_approved = validation.get("approved")

    if actual_approved != expect["approved"]:
        return {
            "status": FAILED,
            "reason": f"expected approved={expect['approved']}, got {actual_approved}",
        }

    if not expect["approved"]:
        actual_rule = validation.get("violated_rule")
        if actual_rule != expect["violated_rule"]:
            return {
                "status": FAILED,
                "reason": f"expected violated_rule={expect['violated_rule']!r}, got {actual_rule!r}",
            }
        return {"status": PASSED, "reason": "declined for the expected reason"}

    forbidden_sku = expect.get("forbidden_upsell_sku")
    if forbidden_sku:
        upsell = decision.get("upsell") or {}
        if upsell.get("upsell_sku") == forbidden_sku:
            return {
                "status": FAILED,
                "reason": f"the upsell engine proposed the forbidden SKU {forbidden_sku}",
            }

    return {"status": PASSED, "reason": "approved as expected"}


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a batch of graded results into totals and a per-group breakdown."""
    total = len(results)
    passed = sum(1 for r in results if r["status"] == PASSED)
    by_group: Dict[str, Dict[str, int]] = {}
    for r in results:
        group = r["case"]["group"]
        stats = by_group.setdefault(group, {"total": 0, "passed": 0})
        stats["total"] += 1
        if r["status"] == PASSED:
            stats["passed"] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "by_group": by_group,
    }
