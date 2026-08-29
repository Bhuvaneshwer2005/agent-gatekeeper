# Tests for the decision engine - specifically the one guarantee the whole
# project depends on: a declined mandate must never reach the LLM.

import json
from datetime import datetime, timedelta, timezone

from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.models.validation_result import ValidationRule
from app.upsell import decision_engine, upsell_engine


def make_mandate(**overrides):
    defaults = {
        "buyer_id": "agent-1",
        "intent": "Buy running shoes, open to add-ons",
        "budget_max": 2499.0 + 1500,
        "category_allowlist": ["footwear", "accessories"],
        "expiry": datetime.now(timezone.utc) + timedelta(days=1),
    }
    defaults.update(overrides)
    return Mandate(**defaults)


def make_transaction(**overrides):
    defaults = {"sku": "SHOE-001", "category": "footwear", "amount": 2499.0}
    defaults.update(overrides)
    return ProposedTransaction(**defaults)


def test_declined_mandate_never_calls_the_llm(monkeypatch):
    called = False

    def fake_complete_json(system_prompt, user_prompt):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    # Budget deliberately too low - should decline before ever reaching the LLM.
    mandate = make_mandate(budget_max=100.0)
    decision = decision_engine.make_decision(mandate, make_transaction())

    assert decision.validation.approved is False
    assert decision.validation.violated_rule == ValidationRule.BUDGET_EXCEEDED
    assert decision.upsell is None
    assert decision.llm_raw_responses == []
    assert called is False


def test_approved_mandate_reaches_the_upsell_engine(monkeypatch):
    def fake_complete_json(system_prompt, user_prompt):
        return json.dumps(
            {
                "upsell_sku": "SOCK-010",
                "justification": "The buyer's running shoes purchase pairs well with socks within their footwear budget.",
            }
        )

    monkeypatch.setattr(upsell_engine, "complete_json", fake_complete_json)

    decision = decision_engine.make_decision(make_mandate(), make_transaction())

    assert decision.validation.approved is True
    assert decision.upsell is not None
    assert decision.upsell.upsell_sku == "SOCK-010"
    assert len(decision.llm_raw_responses) == 1
