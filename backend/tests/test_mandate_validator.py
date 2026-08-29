# Tests for the deterministic mandate validator.
#
# Covers the approve path, one decline case per rule, and the fixed
# check-order guarantee (a transaction that fails more than one rule should
# always report the same rule, not whichever one happened to run last).

from datetime import datetime, timedelta, timezone

from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.models.validation_result import ValidationRule
from app.validator.mandate_validator import validate_mandate


def make_mandate(**overrides):
    defaults = {
        "buyer_id": "agent-42",
        "intent": "Buy running shoes",
        "budget_max": 2500.0,
        "category_allowlist": ["footwear"],
        "expiry": datetime.now(timezone.utc) + timedelta(days=1),
    }
    defaults.update(overrides)
    return Mandate(**defaults)


def make_transaction(**overrides):
    defaults = {
        "sku": "SHOE-001",
        "category": "footwear",
        "amount": 1999.0,
    }
    defaults.update(overrides)
    return ProposedTransaction(**defaults)


def test_approves_when_within_budget_category_and_expiry():
    result = validate_mandate(make_mandate(), make_transaction())
    assert result.approved is True
    assert result.violated_rule is None


def test_declines_when_amount_exceeds_budget():
    result = validate_mandate(make_mandate(budget_max=1000.0), make_transaction())
    assert result.approved is False
    assert result.violated_rule == ValidationRule.BUDGET_EXCEEDED


def test_declines_when_category_not_in_allowlist():
    result = validate_mandate(
        make_mandate(category_allowlist=["electronics"]), make_transaction()
    )
    assert result.approved is False
    assert result.violated_rule == ValidationRule.CATEGORY_NOT_ALLOWED


def test_declines_when_mandate_expired():
    expired_mandate = make_mandate(
        expiry=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    result = validate_mandate(expired_mandate, make_transaction())
    assert result.approved is False
    assert result.violated_rule == ValidationRule.MANDATE_EXPIRED


def test_expired_and_over_budget_reports_expiry_first():
    # Violates both expiry and budget - expiry is checked first, so that's
    # the reason that should come back, deterministically.
    mandate = make_mandate(
        expiry=datetime.now(timezone.utc) - timedelta(minutes=1),
        budget_max=10.0,
    )
    result = validate_mandate(mandate, make_transaction())
    assert result.violated_rule == ValidationRule.MANDATE_EXPIRED
