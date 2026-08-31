# Unit tests for the audit log module - writing rows directly via
# log_decision(), without going through the FastAPI layer. The end-to-end
# "exactly one row per /decide request" guarantee is covered separately in
# test_decide_audit_log.py.

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.audit import audit_log
from app.models.decision import Decision
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.models.upsell_proposal import UpsellProposal
from app.models.validation_result import ValidationResult, ValidationRule


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


def row_count(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def test_log_decision_writes_one_row_for_an_approval_with_upsell(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)

    raw_responses = ['{"upsell_sku": "SOCK-010", "justification": "Fits the running shoe budget."}']
    decision = Decision(
        validation=ValidationResult(approved=True, violated_rule=None, detail="ok"),
        upsell=UpsellProposal(upsell_sku="SOCK-010", justification="Fits the running shoe budget."),
        llm_raw_responses=raw_responses,
    )

    audit_log.log_decision(
        mandate=make_mandate(),
        transaction=make_transaction(),
        decision=decision,
        razorpay_status="created",
        razorpay_order_id="order_abc123",
    )

    assert row_count(db_path) == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT buyer_id, sku, validation_approved, upsell_sku, "
            "razorpay_status, razorpay_order_id, llm_raw_responses FROM audit_log"
        ).fetchone()
    assert row[0] == "agent-1"
    assert row[1] == "SHOE-001"
    assert row[2] == 1
    assert row[3] == "SOCK-010"
    assert row[4] == "created"
    assert row[5] == "order_abc123"
    assert json.loads(row[6]) == raw_responses


def test_log_decision_writes_one_row_for_a_decline(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)

    decision = Decision(
        validation=ValidationResult(
            approved=False, violated_rule=ValidationRule.BUDGET_EXCEEDED, detail="over budget"
        ),
        upsell=None,
        llm_raw_responses=[],
    )

    audit_log.log_decision(
        mandate=make_mandate(),
        transaction=make_transaction(),
        decision=decision,
        razorpay_status="skipped",
    )

    assert row_count(db_path) == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT validation_approved, violated_rule, upsell_sku, "
            "razorpay_status, razorpay_order_id FROM audit_log"
        ).fetchone()
    assert row[0] == 0
    assert row[1] == "budget_exceeded"
    assert row[2] is None
    assert row[3] == "skipped"
    assert row[4] is None


def test_each_call_adds_exactly_one_row(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(audit_log, "DB_PATH", db_path)

    decision = Decision(
        validation=ValidationResult(approved=True, violated_rule=None, detail="ok"),
        upsell=None,
        llm_raw_responses=[],
    )

    for _ in range(3):
        audit_log.log_decision(
            mandate=make_mandate(),
            transaction=make_transaction(),
            decision=decision,
            razorpay_status="created",
            razorpay_order_id="order_xyz",
        )

    assert row_count(db_path) == 3
