# Pure data-layer functions for the Live demo tab: talking to the backend
# and turning a /decide response into an ordered list of pipeline steps.
#
# Same split as audit_view.py and growth_view.py - no Streamlit calls here,
# so the step-derivation logic is unit-testable with plain pytest.
#
# The steps are derived from the response the backend already returns; this
# module never re-implements any validation or upsell logic. If it had its
# own copy of "was this within budget," the panel could show something the
# actual gate never decided - so it only ever reports what came back.

from typing import Any, Dict, List

import httpx

OK = "ok"
BLOCKED = "blocked"
INFO = "info"

RULE_LABELS = {
    "mandate_expired": "mandate expired",
    "category_not_allowed": "category not allowed",
    "budget_exceeded": "budget exceeded",
}


def fetch_scenarios(base_url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch the demo scenarios the backend defines."""
    response = httpx.get(f"{base_url}/scenarios", timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_catalog(base_url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch the live product catalog - used to populate the custom mandate builder."""
    response = httpx.get(f"{base_url}/catalog", timeout=timeout)
    response.raise_for_status()
    return response.json()


def run_scenario(base_url: str, scenario: Dict[str, Any], timeout: float = 40.0) -> Dict[str, Any]:
    """POST one scenario to /decide and return the decision.

    The timeout is generous because a scenario that reaches the LLM can take
    a couple of seconds, and one that gets refused and retried takes twice
    that.
    """
    payload = {"mandate": scenario["mandate"], "transaction": scenario["transaction"]}
    response = httpx.post(f"{base_url}/decide", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def derive_steps(decision: Dict[str, Any]) -> List[Dict[str, str]]:
    """Turn a /decide response into the ordered pipeline steps to display.

    The validator checks expiry, then category, then budget, and returns on
    the first failure - so a decline tells us the failing rule but says
    nothing about the checks that never ran. Rather than invent results for
    those, a decline shows only the rule that actually fired.
    """
    validation = decision.get("validation", {})
    approved = validation.get("approved", False)
    steps: List[Dict[str, str]] = []

    if not approved:
        rule = validation.get("violated_rule") or "declined"
        steps.append({"status": BLOCKED, "label": RULE_LABELS.get(rule, rule), "detail": validation.get("detail", "")})
        steps.append({"status": INFO, "label": "LLM never invoked", "detail": "Nothing to upsell on a refused purchase."})
        steps.append({"status": INFO, "label": "Razorpay never called", "detail": "No order created."})
        steps.append({"status": OK, "label": "audit row written", "detail": ""})
        return steps

    steps.append({"status": OK, "label": "expiry valid", "detail": ""})
    steps.append({"status": OK, "label": "category allowed", "detail": ""})
    steps.append({"status": OK, "label": "within budget", "detail": validation.get("detail", "")})

    attempts = decision.get("llm_raw_responses") or []
    upsell = decision.get("upsell") or {}
    upsell_sku = upsell.get("upsell_sku")

    if not attempts:
        steps.append(
            {
                "status": INFO,
                "label": "no candidates survived pre-filter",
                "detail": "LLM skipped entirely - nothing safe to offer.",
            }
        )
    else:
        for index, attempt in enumerate(attempts, start=1):
            failed = attempt.startswith("<LLM call failed")
            steps.append(
                {
                    "status": BLOCKED if failed else OK,
                    "label": f"LLM attempt {index}" + (" - refused or failed" if failed else " - proposed"),
                    "detail": attempt,
                }
            )

    if upsell_sku:
        steps.append({"status": OK, "label": f"upsell verified: {upsell_sku}", "detail": upsell.get("justification", "")})
    else:
        steps.append(
            {
                "status": INFO,
                "label": "fail safe - no upsell",
                "detail": upsell.get("justification", ""),
            }
        )

    steps.append({"status": OK, "label": "audit row written", "detail": ""})
    return steps


def outcome_summary(decision: Dict[str, Any]) -> Dict[str, str]:
    """One-line summary of what the whole pipeline concluded.

    "Approved with no upsell" has two very different causes worth telling
    apart: nothing was eligible in the first place, or something was
    proposed and the guardrails threw it out. Collapsing both into "no
    upsell proposed" hides the second one, which is the interesting case.
    """
    validation = decision.get("validation", {})
    upsell = decision.get("upsell") or {}
    attempts = decision.get("llm_raw_responses") or []

    if not validation.get("approved"):
        rule = validation.get("violated_rule") or "declined"
        return {"status": BLOCKED, "text": f"Refused - {RULE_LABELS.get(rule, rule)}. Razorpay never touched."}

    if upsell.get("upsell_sku"):
        return {"status": OK, "text": f"Approved, with a verified upsell ({upsell['upsell_sku']})."}

    if attempts:
        return {
            "status": OK,
            "text": (
                f"Approved. All {len(attempts)} upsell attempt(s) were rejected by the "
                "guardrails - nothing unverified reached checkout."
            ),
        }

    return {"status": OK, "text": "Approved. No upsell was eligible under this mandate."}
