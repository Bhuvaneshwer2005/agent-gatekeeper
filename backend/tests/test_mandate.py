# Structural validation tests for the Mandate schema.
#
# These only check shape - required fields, types, basic constraints. They
# deliberately don't assert anything about business rules like "expiry is in
# the past" or "category isn't one we sell" - Step 2 is the data contract
# only; that judgment belongs to the validator built in the next step.

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.mandate import Mandate


def valid_payload():
    return {
        "buyer_id": "agent-42",
        "intent": "Buy a pair of running shoes",
        "budget_max": 2500.0,
        "category_allowlist": ["footwear"],
        "expiry": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


def test_valid_mandate_parses():
    mandate = Mandate(**valid_payload())
    assert mandate.buyer_id == "agent-42"
    assert mandate.category_allowlist == ["footwear"]


def test_missing_required_field_rejected():
    payload = valid_payload()
    del payload["budget_max"]
    with pytest.raises(ValidationError):
        Mandate(**payload)


def test_non_positive_budget_rejected():
    payload = valid_payload()
    payload["budget_max"] = 0
    with pytest.raises(ValidationError):
        Mandate(**payload)


def test_empty_category_allowlist_rejected():
    payload = valid_payload()
    payload["category_allowlist"] = []
    with pytest.raises(ValidationError):
        Mandate(**payload)


def test_blank_category_entry_rejected():
    payload = valid_payload()
    payload["category_allowlist"] = ["  "]
    with pytest.raises(ValidationError):
        Mandate(**payload)


def test_naive_datetime_expiry_rejected():
    payload = valid_payload()
    payload["expiry"] = datetime.now().isoformat()  # no tzinfo
    with pytest.raises(ValidationError):
        Mandate(**payload)
