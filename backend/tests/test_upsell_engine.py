# Tests for the upsell engine.
#
# The LLM is never actually called here - `complete_json` is monkeypatched
# in every test that would otherwise reach it, so the suite runs offline
# and deterministically. What's under test is the surrounding guardrails:
# candidate pre-filtering, malformed-output retry, hallucinated-SKU
# rejection, and the ungrounded-justification check.

import json
from datetime import datetime, timedelta, timezone

from app.models.mandate import Mandate
from app.models.product import Product
from app.models.transaction import ProposedTransaction
from app.upsell import upsell_engine

CATALOG = [
    Product(
        sku="SHOE-001",
        name="Trailrunner Pro Running Shoes",
        price=2499.0,
        category="footwear",
        stock=40,
        upsell_eligible=False,
    ),
    Product(
        sku="SOCK-010",
        name="Cushioned Running Socks",
        price=399.0,
        category="footwear",
        stock=120,
        upsell_eligible=True,
    ),
    Product(
        sku="BOTTLE-030",
        name="Insulated Water Bottle",
        price=799.0,
        category="accessories",
        stock=60,
        upsell_eligible=True,
    ),
]


def make_mandate(**overrides):
    defaults = {
        "buyer_id": "agent-1",
        "intent": "Buy running shoes and maybe a water bottle",
        "budget_max": 3500.0,
        "category_allowlist": ["footwear", "accessories"],
        "expiry": datetime.now(timezone.utc) + timedelta(days=1),
    }
    defaults.update(overrides)
    return Mandate(**defaults)


def make_transaction(**overrides):
    defaults = {"sku": "SHOE-001", "category": "footwear", "amount": 2499.0}
    defaults.update(overrides)
    return ProposedTransaction(**defaults)


def test_select_candidates_excludes_ineligible_over_budget_and_wrong_category():
    # Headroom of 400: socks (399) fit, the bottle (799) doesn't.
    mandate = make_mandate(budget_max=2499.0 + 400)
    transaction = make_transaction()
    candidates = upsell_engine._select_candidates(mandate, transaction, CATALOG)
    assert {product.sku for product in candidates} == {"SOCK-010"}


def test_propose_upsell_skips_the_llm_when_no_candidates_fit(monkeypatch):
    called = False

    def fake_complete_json(system_prompt, user_prompt):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    mandate = make_mandate(budget_max=2499.0)  # zero headroom
    proposal, raw = upsell_engine.propose_upsell(mandate, make_transaction(), CATALOG)

    assert proposal.upsell_sku is None
    assert raw == []
    assert called is False


def test_propose_upsell_accepts_a_valid_grounded_response(monkeypatch):
    def fake_complete_json(system_prompt, user_prompt):
        return json.dumps(
            {
                "upsell_sku": "SOCK-010",
                "justification": "The buyer wants running shoes, and matching socks fit their footwear budget.",
            }
        )

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    proposal, raw = upsell_engine.propose_upsell(
        make_mandate(), make_transaction(), CATALOG
    )

    assert proposal.upsell_sku == "SOCK-010"
    assert len(raw) == 1


def test_propose_upsell_retries_once_on_malformed_json(monkeypatch):
    attempts = []

    def fake_complete_json(system_prompt, user_prompt):
        attempts.append(1)
        if len(attempts) == 1:
            return "not valid json"
        return json.dumps(
            {
                "upsell_sku": None,
                "justification": "Nothing here clearly matches the buyer's running shoe intent.",
            }
        )

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    proposal, raw = upsell_engine.propose_upsell(
        make_mandate(), make_transaction(), CATALOG
    )

    assert len(raw) == 2
    assert proposal.upsell_sku is None


def test_propose_upsell_rejects_a_hallucinated_sku_and_falls_back_to_no_upsell(
    monkeypatch,
):
    def fake_complete_json(system_prompt, user_prompt):
        return json.dumps(
            {
                "upsell_sku": "NOT-A-REAL-SKU",
                "justification": "This great running shoe add-on definitely exists.",
            }
        )

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    proposal, raw = upsell_engine.propose_upsell(
        make_mandate(), make_transaction(), CATALOG
    )

    assert proposal.upsell_sku is None
    assert len(raw) == upsell_engine.MAX_ATTEMPTS
    assert "could not be verified" in proposal.justification.lower()


def test_propose_upsell_rejects_an_ungrounded_justification(monkeypatch):
    def fake_complete_json(system_prompt, user_prompt):
        return json.dumps(
            {"upsell_sku": "SOCK-010", "justification": "This is a great product that everyone loves."}
        )

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    proposal, raw = upsell_engine.propose_upsell(
        make_mandate(), make_transaction(), CATALOG
    )

    assert proposal.upsell_sku is None
    assert len(raw) == upsell_engine.MAX_ATTEMPTS
