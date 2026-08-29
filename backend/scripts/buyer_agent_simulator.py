# Buyer agent simulator.
#
# Queries the live catalog, builds four scenario mandates from real catalog
# data, and posts each one to the (currently stubbed) decision endpoint.
# This is the on-demand trigger every later demo and test will run through -
# it never hardcodes purchase intents, it always shops from whatever the
# catalog endpoint actually returns.
#
# Usage: start the backend first (uvicorn app.main:app --reload from
# backend/), then run this script from backend/:
#     python scripts/buyer_agent_simulator.py

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

BASE_URL = os.environ.get("AGENT_GATEKEEPER_BASE_URL", "http://localhost:8000")


def fetch_catalog(client: httpx.Client) -> List[Dict[str, Any]]:
    """Fetch the live product catalog rather than assuming its contents."""
    response = client.get(f"{BASE_URL}/catalog")
    response.raise_for_status()
    return response.json()


def find_product(catalog: List[Dict[str, Any]], sku: str) -> Dict[str, Any]:
    for product in catalog:
        if product["sku"] == sku:
            return product
    # Fail loudly rather than silently building a scenario around the wrong
    # item - the scenarios below are written around specific SKUs on purpose.
    raise ValueError(f"Catalog is missing expected SKU '{sku}' - has the catalog data changed?")


def iso_in_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def build_scenarios(catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the four demo scenarios from live catalog data.

    Each scenario pairs a mandate with a proposed transaction:

    - clean_purchase: budget just covers the item, category and expiry are
      both fine - the straightforward approve case.
    - upsell_eligible_purchase: same item, but the mandate leaves real
      budget headroom and allows a second category, so a later upsell
      engine has room to propose a companion product.
    - mandate_violation: budget is deliberately set below the item's price,
      so the validator's budget_exceeded rule should fire.
    - adversarial_upsell_attempt: the buyer agent goes straight for an
      upsell-eligible item outside its authorized category, framing it as
      an add-on in the intent text. Being upsell-eligible or having enough
      combined budget must not be a backdoor around the category rule.
    """
    main_item = find_product(catalog, "SHOE-001")
    accessory = find_product(catalog, "BOTTLE-030")

    return [
        {
            "name": "clean_purchase",
            "description": "Budget matches the item almost exactly; category and expiry are both fine.",
            "mandate": {
                "buyer_id": "agent-clean-01",
                "intent": f"Buy {main_item['name']}",
                "budget_max": main_item["price"] + 50,
                "category_allowlist": [main_item["category"]],
                "expiry": iso_in_days(1),
            },
            "transaction": {
                "sku": main_item["sku"],
                "category": main_item["category"],
                "amount": main_item["price"],
            },
        },
        {
            "name": "upsell_eligible_purchase",
            "description": "Same item, but the mandate leaves budget headroom and category room for a later upsell.",
            "mandate": {
                "buyer_id": "agent-upsell-02",
                "intent": f"Buy {main_item['name']}, open to add-ons",
                "budget_max": main_item["price"] + 1500,
                "category_allowlist": [main_item["category"], accessory["category"]],
                "expiry": iso_in_days(1),
            },
            "transaction": {
                "sku": main_item["sku"],
                "category": main_item["category"],
                "amount": main_item["price"],
            },
        },
        {
            "name": "mandate_violation",
            "description": "Budget is deliberately set below the item's price - should decline on budget_exceeded.",
            "mandate": {
                "buyer_id": "agent-violation-03",
                "intent": f"Buy {main_item['name']}",
                "budget_max": main_item["price"] - 500,
                "category_allowlist": [main_item["category"]],
                "expiry": iso_in_days(1),
            },
            "transaction": {
                "sku": main_item["sku"],
                "category": main_item["category"],
                "amount": main_item["price"],
            },
        },
        {
            "name": "adversarial_upsell_attempt",
            "description": (
                "Requests an upsell-eligible item outside the mandate's authorized "
                "category, framed as an add-on - should decline on category_not_allowed "
                "even though the combined budget would technically cover it."
            ),
            "mandate": {
                "buyer_id": "agent-adversarial-04",
                "intent": f"Buy {main_item['name']}, also grab {accessory['name']} as an add-on",
                "budget_max": main_item["price"] + accessory["price"] + 500,
                "category_allowlist": [main_item["category"]],
                "expiry": iso_in_days(1),
            },
            "transaction": {
                "sku": accessory["sku"],
                "category": accessory["category"],
                "amount": accessory["price"],
            },
        },
    ]


def run_scenario(client: httpx.Client, scenario: Dict[str, Any]) -> None:
    payload = {"mandate": scenario["mandate"], "transaction": scenario["transaction"]}
    response = client.post(f"{BASE_URL}/decide", json=payload)
    print(f"\n=== {scenario['name']} ===")
    print(scenario["description"])
    print(f"POST /decide -> {response.status_code}")
    print(response.json())


def main() -> None:
    with httpx.Client(timeout=10.0) as client:
        catalog = fetch_catalog(client)
        for scenario in build_scenarios(catalog):
            run_scenario(client, scenario)


if __name__ == "__main__":
    main()
