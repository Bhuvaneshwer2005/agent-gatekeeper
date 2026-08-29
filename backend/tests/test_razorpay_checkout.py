# Tests for the Razorpay checkout integration.
#
# The Razorpay client itself is never really constructed here - `_get_client`
# is monkeypatched with a fake that records calls, so this suite never makes
# a real network request and never needs live test-mode keys to run. The
# thing actually being proven is the hard rule this module exists to
# enforce: a declined decision must never reach Razorpay.

from datetime import datetime, timedelta, timezone

import pytest

from app.models.decision import Decision
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.models.upsell_proposal import UpsellProposal
from app.models.validation_result import ValidationResult, ValidationRule
from app.razorpay_client import checkout


def make_mandate(**overrides):
    defaults = {
        "buyer_id": "agent-1",
        "intent": "Buy running shoes",
        "budget_max": 2499.0,
        "category_allowlist": ["footwear"],
        "expiry": datetime.now(timezone.utc) + timedelta(days=1),
    }
    defaults.update(overrides)
    return Mandate(**defaults)


def make_transaction(**overrides):
    defaults = {"sku": "SHOE-001", "category": "footwear", "amount": 2499.0}
    defaults.update(overrides)
    return ProposedTransaction(**defaults)


def approved_decision(**overrides):
    defaults = {
        "validation": ValidationResult(approved=True, violated_rule=None, detail="ok"),
        "upsell": None,
        "llm_raw_responses": [],
    }
    defaults.update(overrides)
    return Decision(**defaults)


def declined_decision(rule=ValidationRule.BUDGET_EXCEEDED):
    validation = ValidationResult(approved=False, violated_rule=rule, detail="over budget")
    return Decision(validation=validation, upsell=None, llm_raw_responses=[])


class FakeOrderResource:
    def __init__(self):
        self.calls = []

    def create(self, data):
        self.calls.append(data)
        return {"id": "order_fake123", **data}


class FakeRazorpayClient:
    def __init__(self):
        self.order = FakeOrderResource()


def test_declined_decision_never_calls_razorpay(monkeypatch):
    fake_client = FakeRazorpayClient()
    monkeypatch.setattr(checkout, "_get_client", lambda: fake_client)

    with pytest.raises(checkout.DeclinedDecisionError):
        checkout.create_order(declined_decision(), make_mandate(), make_transaction())

    assert fake_client.order.calls == []


def test_declined_decision_raises_before_the_client_is_even_constructed(monkeypatch):
    # Stronger than the test above: proves there's no path from a declined
    # decision to Razorpay at all, not even as far as building a client.
    def fail_if_called():
        raise AssertionError("_get_client should never be called for a declined decision")

    monkeypatch.setattr(checkout, "_get_client", fail_if_called)

    with pytest.raises(checkout.DeclinedDecisionError):
        checkout.create_order(declined_decision(), make_mandate(), make_transaction())


def test_approved_decision_creates_an_order_in_paise(monkeypatch):
    fake_client = FakeRazorpayClient()
    monkeypatch.setattr(checkout, "_get_client", lambda: fake_client)

    order = checkout.create_order(approved_decision(), make_mandate(), make_transaction())

    assert len(fake_client.order.calls) == 1
    call = fake_client.order.calls[0]
    assert call["amount"] == 249900  # 2499.0 rupees -> paise
    assert call["currency"] == "INR"
    assert call["payment_capture"] == 1
    assert order["id"] == "order_fake123"


def test_order_notes_include_upsell_sku_when_present(monkeypatch):
    fake_client = FakeRazorpayClient()
    monkeypatch.setattr(checkout, "_get_client", lambda: fake_client)

    decision = approved_decision(
        upsell=UpsellProposal(upsell_sku="SOCK-010", justification="Fits the buyer's stated budget.")
    )
    checkout.create_order(decision, make_mandate(), make_transaction())

    call = fake_client.order.calls[0]
    assert call["notes"]["upsell_sku"] == "SOCK-010"


def test_order_amount_excludes_the_upsell_price(monkeypatch):
    # The upsell is a suggestion, not a confirmed charge - the order total
    # must equal the base transaction amount even when an upsell was proposed.
    fake_client = FakeRazorpayClient()
    monkeypatch.setattr(checkout, "_get_client", lambda: fake_client)

    decision = approved_decision(
        upsell=UpsellProposal(upsell_sku="SOCK-010", justification="Fits the buyer's stated budget.")
    )
    checkout.create_order(decision, make_mandate(), make_transaction())

    call = fake_client.order.calls[0]
    assert call["amount"] == 249900  # SHOE-001 only, not + SOCK-010's price
