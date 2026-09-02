# Buyer agent simulator.
#
# Queries the live catalog, builds the demo scenario mandates from real
# catalog data, and posts each one to the decision endpoint. This is the
# on-demand terminal trigger for the demo - it never hardcodes purchase
# intents, it always shops from whatever the catalog endpoint returns.
#
# The scenarios themselves live in app/scenarios/demo_scenarios.py so this
# script and the /scenarios endpoint (which feeds the dashboard's Live demo
# tab) can never drift apart. They're re-exported here because the tests
# import them from this module.
#
# Usage: start the backend first (uvicorn app.main:app --reload from
# backend/), then run this script from backend/:
#     python scripts/buyer_agent_simulator.py

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

# Running this file directly puts scripts/ on sys.path, not backend/, so the
# app package wouldn't be importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scenarios.demo_scenarios import build_scenarios, find_product, iso_in_days  # noqa: E402,F401

BASE_URL = os.environ.get("AGENT_GATEKEEPER_BASE_URL", "http://localhost:8000")


def fetch_catalog(client: httpx.Client) -> List[Dict[str, Any]]:
    """Fetch the live product catalog rather than assuming its contents."""
    response = client.get(f"{BASE_URL}/catalog")
    response.raise_for_status()
    return response.json()


def run_scenario(client: httpx.Client, scenario: Dict[str, Any]) -> None:
    payload = {"mandate": scenario["mandate"], "transaction": scenario["transaction"]}
    response = client.post(f"{BASE_URL}/decide", json=payload)
    print(f"\n=== {scenario['name']} ===")
    print(scenario["description"])
    print(f"POST /decide -> {response.status_code}")
    # ensure_ascii=True escapes non-ASCII characters (e.g. a smart hyphen
    # in an LLM-generated justification) as \uXXXX, since Windows consoles
    # commonly default to a codepage (cp1252) that can't print them raw.
    print(json.dumps(response.json(), ensure_ascii=True))


def main() -> None:
    with httpx.Client(timeout=10.0) as client:
        catalog = fetch_catalog(client)
        for scenario in build_scenarios(catalog):
            run_scenario(client, scenario)


if __name__ == "__main__":
    main()
