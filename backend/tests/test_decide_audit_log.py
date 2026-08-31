# Integration tests proving /decide writes exactly one audit row per
# request, whatever the outcome - declined, approved with a successful
# Razorpay order, or approved with a Razorpay failure. The LLM and
# Razorpay client are both monkeypatched so this file never makes a real
# network call and never needs live API keys to run.

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.audit import audit_log
from app.main import app
from app.razorpay_client import checkout
from app.upsell import upsell_engine

client = TestClient(app)


def mandate_payload(**overrides):
    defaults = {
        "buyer_id": "agent-audit-1",
        "intent": "Buy running shoes",
        "budget_max": 2499.0,
        "category_allowlist": ["footwear"],
        "expiry": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    defaults.update(overrides)
    return defaults


def transaction_payload(**overrides):
    defaults = {"sku": "SHOE-001", "category": "footwear", "amount": 2499.0}
    defaults.update(overrides)
    return defaults


def row_count(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def fake_no_upsell_complete_json(system_prompt, user_prompt):
    return json.dumps(
        {"upsell_sku": None, "justification": "No candidate matches the buyer's stated intent."}
    )


def test_declined_decision_writes_one_skipped_row(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)

    payload = {
        "mandate": mandate_payload(budget_max=100.0),  # forces budget_exceeded
        "transaction": transaction_payload(),
    }
    response = client.post("/decide", json=payload)

    assert response.status_code == 200
    assert row_count(db_path) == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT validation_approved, razorpay_status FROM audit_log"
        ).fetchone()
    assert row == (0, "skipped")


def test_approved_decision_with_successful_order_writes_one_created_row(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)
    monkeypatch.setattr(upsell_engine, "complete_json", fake_no_upsell_complete_json)

    class FakeOrderResource:
        def create(self, data):
            return {"id": "order_test123", **data}

    class FakeClient:
        def __init__(self):
            self.order = FakeOrderResource()

    monkeypatch.setattr(checkout, "_get_client", lambda: FakeClient())

    payload = {"mandate": mandate_payload(), "transaction": transaction_payload()}
    response = client.post("/decide", json=payload)

    assert response.status_code == 200
    assert row_count(db_path) == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT validation_approved, razorpay_status, razorpay_order_id FROM audit_log"
        ).fetchone()
    assert row == (1, "created", "order_test123")


def test_approved_decision_with_razorpay_failure_still_writes_one_row(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)
    monkeypatch.setattr(upsell_engine, "complete_json", fake_no_upsell_complete_json)

    def fail_get_client():
        raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set.")

    monkeypatch.setattr(checkout, "_get_client", fail_get_client)

    payload = {"mandate": mandate_payload(), "transaction": transaction_payload()}
    response = client.post("/decide", json=payload)

    # A Razorpay failure must not crash the request - it must still be logged.
    assert response.status_code == 200
    assert row_count(db_path) == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT razorpay_status, razorpay_detail FROM audit_log"
        ).fetchone()
    assert row[0] == "failed"
    assert "RAZORPAY_KEY_ID" in row[1]


def test_repeated_requests_each_add_exactly_one_row(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)

    def fail_get_client():
        raise RuntimeError("no keys configured")

    monkeypatch.setattr(checkout, "_get_client", fail_get_client)
    monkeypatch.setattr(upsell_engine, "complete_json", fake_no_upsell_complete_json)

    payload = {
        "mandate": mandate_payload(budget_max=1.0),  # declined - cheapest path
        "transaction": transaction_payload(),
    }
    client.post("/decide", json=payload)
    client.post("/decide", json=payload)

    assert row_count(db_path) == 2
