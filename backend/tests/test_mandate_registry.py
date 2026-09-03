# Unit tests for the mandate registry module - issuing, reading, and
# drawing down a persisted mandate directly, without going through the
# FastAPI layer. The end-to-end cumulative-enforcement guarantee (does
# /decide actually check and update this correctly) is covered separately
# in test_cumulative_spend.py.

from datetime import datetime, timedelta, timezone

from app.models.mandate import Mandate
from app.registry import mandate_registry


def make_mandate(**overrides):
    defaults = {
        "buyer_id": "agent-registry-1",
        "intent": "Buy running gear over time",
        "budget_max": 3000.0,
        "category_allowlist": ["footwear", "accessories"],
        "expiry": datetime.now(timezone.utc) + timedelta(days=1),
    }
    defaults.update(overrides)
    return Mandate(**defaults)


def test_issue_mandate_assigns_an_id_and_starts_with_zero_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    record = mandate_registry.issue_mandate(make_mandate())

    assert record["mandate_id"].startswith("mnd_")
    assert record["budget_spent"] == 0
    assert record["budget_remaining"] == 3000.0
    assert record["status"] == "active"
    assert record["category_allowlist"] == ["footwear", "accessories"]


def test_get_mandate_returns_none_for_an_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    assert mandate_registry.get_mandate("mnd_does_not_exist") is None


def test_record_spend_draws_down_budget_remaining(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    record = mandate_registry.issue_mandate(make_mandate(budget_max=1000.0))
    mandate_registry.record_spend(record["mandate_id"], 400.0)

    updated = mandate_registry.get_mandate(record["mandate_id"])
    assert updated["budget_spent"] == 400.0
    assert updated["budget_remaining"] == 600.0
    assert updated["status"] == "active"


def test_record_spend_accumulates_across_multiple_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    record = mandate_registry.issue_mandate(make_mandate(budget_max=1000.0))
    mandate_registry.record_spend(record["mandate_id"], 400.0)
    mandate_registry.record_spend(record["mandate_id"], 400.0)

    updated = mandate_registry.get_mandate(record["mandate_id"])
    assert updated["budget_spent"] == 800.0
    assert updated["budget_remaining"] == 200.0


def test_status_is_exhausted_once_spend_reaches_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    record = mandate_registry.issue_mandate(make_mandate(budget_max=500.0))
    mandate_registry.record_spend(record["mandate_id"], 500.0)

    updated = mandate_registry.get_mandate(record["mandate_id"])
    assert updated["budget_remaining"] == 0
    assert updated["status"] == "exhausted"


def test_status_is_expired_once_expiry_has_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    record = mandate_registry.issue_mandate(
        make_mandate(expiry=datetime.now(timezone.utc) - timedelta(minutes=1))
    )

    fetched = mandate_registry.get_mandate(record["mandate_id"])
    assert fetched["status"] == "expired"


def test_list_mandates_returns_every_issued_mandate_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(mandate_registry, "DB_PATH", tmp_path / "registry.db")

    first = mandate_registry.issue_mandate(make_mandate(buyer_id="agent-a"))
    second = mandate_registry.issue_mandate(make_mandate(buyer_id="agent-b"))

    listed = mandate_registry.list_mandates()
    assert [m["mandate_id"] for m in listed] == [second["mandate_id"], first["mandate_id"]]
