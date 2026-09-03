# Integration tests proving the mandate_id path on /decide actually
# enforces cumulative spend, not just per-transaction spend - the gap a
# stateless, inline-only mandate could never close. An agent staying under
# a single transaction's budget across several purchases must still be
# stopped once the mandate's real total is exceeded.
#
# The LLM and Razorpay client are both monkeypatched, same as
# test_decide_audit_log.py, so this file never makes a real network call.

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.audit import audit_log
from app.main import app
from app.registry import mandate_registry
from app.upsell import upsell_engine

client = TestClient(app)


def fake_no_upsell_complete_json(system_prompt, user_prompt):
    return json.dumps({"upsell_sku": None, "justification": "No candidate matches the buyer's stated intent."})


def use_temp_dbs(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)
    monkeypatch.setattr(mandate_registry, "DB_PATH", db_path)
    monkeypatch.setattr(upsell_engine, "complete_json", fake_no_upsell_complete_json)


def issue_mandate(budget_max=3000.0, category_allowlist=None, expiry_days=1):
    payload = {
        "buyer_id": "agent-cumulative-1",
        "intent": "Buy running gear across a few purchases",
        "budget_max": budget_max,
        "category_allowlist": category_allowlist or ["footwear"],
        "expiry": (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat(),
    }
    response = client.post("/mandates", json=payload)
    assert response.status_code == 200
    return response.json()


def decide_against(mandate_id, amount, sku="SOCK-010", category="footwear"):
    payload = {
        "mandate_id": mandate_id,
        "transaction": {"sku": sku, "category": category, "amount": amount},
    }
    return client.post("/decide", json=payload)


def test_post_mandates_returns_a_fresh_id_with_full_budget_available(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)

    record = issue_mandate(budget_max=2000.0)

    assert record["mandate_id"].startswith("mnd_")
    assert record["budget_remaining"] == 2000.0
    assert record["status"] == "active"


def test_get_mandates_lists_what_was_issued(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    issue_mandate()

    response = client.get("/mandates")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_decide_with_unknown_mandate_id_returns_404(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)

    response = decide_against("mnd_does_not_exist", 500.0)
    assert response.status_code == 404


def test_two_purchases_each_individually_affordable_draw_down_the_same_mandate(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate(budget_max=1000.0)

    first = decide_against(mandate["mandate_id"], 400.0)
    assert first.status_code == 200
    assert first.json()["validation"]["approved"] is True

    second = decide_against(mandate["mandate_id"], 400.0)
    assert second.status_code == 200
    assert second.json()["validation"]["approved"] is True

    updated = client.get("/mandates").json()[0]
    assert updated["budget_spent"] == 800.0
    assert updated["budget_remaining"] == 200.0


def test_salami_slicing_is_caught_on_the_purchase_that_pushes_past_the_real_budget(
    tmp_path, monkeypatch
):
    # The whole point: each of these three purchases individually looks
    # fine against a naive per-request check (each is well under 1000), but
    # the mandate's real budget is 1000 - the third one must be declined,
    # even though 400 alone was never the problem.
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate(budget_max=1000.0)
    mandate_id = mandate["mandate_id"]

    assert decide_against(mandate_id, 400.0).json()["validation"]["approved"] is True
    assert decide_against(mandate_id, 400.0).json()["validation"]["approved"] is True

    third = decide_against(mandate_id, 400.0)
    body = third.json()
    assert body["validation"]["approved"] is False
    assert body["validation"]["violated_rule"] == "budget_exceeded"
    assert "1,200.00" in body["validation"]["detail"]  # 800 already spent + this 400
    assert "1,000.00" in body["validation"]["detail"]  # the mandate's real budget
    assert "200.00" in body["validation"]["detail"]  # what remained before this attempt

    # And the decline must not have drawn anything down further.
    updated = client.get("/mandates").json()[0]
    assert updated["budget_spent"] == 800.0


def test_declined_cumulative_purchase_never_reaches_razorpay(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate(budget_max=100.0)

    response = decide_against(mandate["mandate_id"], 500.0)
    body = response.json()
    assert body["validation"]["approved"] is False

    import sqlite3

    with sqlite3.connect(audit_log.DB_PATH) as connection:
        row = connection.execute("SELECT razorpay_status FROM audit_log").fetchone()
    assert row[0] == "skipped"


def test_mandate_expiry_is_still_checked_before_budget_on_the_registry_path(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate(budget_max=5000.0, expiry_days=-1)  # already expired

    response = decide_against(mandate["mandate_id"], 100.0)
    body = response.json()
    assert body["validation"]["approved"] is False
    assert body["validation"]["violated_rule"] == "mandate_expired"


def test_category_still_enforced_on_the_registry_path(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate(budget_max=5000.0, category_allowlist=["footwear"])

    response = decide_against(mandate["mandate_id"], 100.0, sku="BOTTLE-030", category="accessories")
    body = response.json()
    assert body["validation"]["approved"] is False
    assert body["validation"]["violated_rule"] == "category_not_allowed"


def test_exhausted_mandate_declines_further_purchases_without_crashing(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate(budget_max=400.0)
    mandate_id = mandate["mandate_id"]

    assert decide_against(mandate_id, 400.0).json()["validation"]["approved"] is True

    exhausted_attempt = decide_against(mandate_id, 50.0)
    assert exhausted_attempt.status_code == 200
    body = exhausted_attempt.json()
    assert body["validation"]["approved"] is False
    assert body["validation"]["violated_rule"] == "budget_exceeded"

    updated = client.get("/mandates").json()[0]
    assert updated["status"] == "exhausted"


def test_inline_mandates_are_completely_unaffected_by_the_registry(tmp_path, monkeypatch):
    # The additive guarantee: a request that never mentions mandate_id must
    # behave exactly as it always has - no registry row, no cumulative
    # check, nothing.
    use_temp_dbs(tmp_path, monkeypatch)

    payload = {
        "mandate": {
            "buyer_id": "agent-inline-1",
            "intent": "Buy running shoes",
            "budget_max": 2499.0,
            "category_allowlist": ["footwear"],
            "expiry": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        "transaction": {"sku": "SHOE-001", "category": "footwear", "amount": 2499.0},
    }
    response = client.post("/decide", json=payload)
    assert response.status_code == 200
    assert response.json()["validation"]["approved"] is True
    assert client.get("/mandates").json() == []


def test_decide_rejects_a_request_with_both_mandate_and_mandate_id(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)
    mandate = issue_mandate()

    payload = {
        "mandate": {
            "buyer_id": "agent-x",
            "intent": "test",
            "budget_max": 100.0,
            "category_allowlist": ["footwear"],
            "expiry": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        "mandate_id": mandate["mandate_id"],
        "transaction": {"sku": "SHOE-001", "category": "footwear", "amount": 50.0},
    }
    response = client.post("/decide", json=payload)
    assert response.status_code == 422


def test_decide_rejects_a_request_with_neither_mandate_nor_mandate_id(tmp_path, monkeypatch):
    use_temp_dbs(tmp_path, monkeypatch)

    payload = {"transaction": {"sku": "SHOE-001", "category": "footwear", "amount": 50.0}}
    response = client.post("/decide", json=payload)
    assert response.status_code == 422
