# Durable audit trail for every decision the system makes.
#
# One row per transaction processed by /decide, covering the full pipeline
# in a single record: the deterministic validator's result, the LLM's
# upsell justification (if any), and whatever happened with Razorpay. A
# single query against this table is the whole story of one decision, not
# four separate logs that have to be reassembled by hand.

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.decision import Decision
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction

# A plain module-level path (not baked into a function default) so tests
# can point it at a temp file via monkeypatch without touching the real
# audit trail on disk.
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "audit_log.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    buyer_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    category TEXT NOT NULL,
    transaction_amount REAL NOT NULL,
    validation_approved INTEGER NOT NULL,
    violated_rule TEXT,
    validation_detail TEXT NOT NULL,
    upsell_sku TEXT,
    upsell_justification TEXT,
    llm_raw_responses TEXT NOT NULL,
    razorpay_status TEXT NOT NULL,
    razorpay_order_id TEXT,
    razorpay_detail TEXT
);
"""


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(_SCHEMA)
    return connection


def log_decision(
    mandate: Mandate,
    transaction: ProposedTransaction,
    decision: Decision,
    razorpay_status: str,
    razorpay_order_id: Optional[str] = None,
    razorpay_detail: Optional[str] = None,
) -> None:
    """Write exactly one audit row for a fully-processed transaction.

    razorpay_status is one of "skipped" (the mandate was declined, so
    Razorpay was never attempted), "created" (an order was created
    successfully), or "failed" (an attempt was made and it errored - e.g.
    missing credentials or a network problem). Whichever it is, this
    function is called exactly once per /decide request, so it writes
    exactly one row per event - never zero, never more than one.
    """
    with closing(_get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO audit_log (
                created_at, buyer_id, sku, category, transaction_amount,
                validation_approved, violated_rule, validation_detail,
                upsell_sku, upsell_justification, llm_raw_responses,
                razorpay_status, razorpay_order_id, razorpay_detail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                mandate.buyer_id,
                transaction.sku,
                transaction.category,
                transaction.amount,
                int(decision.validation.approved),
                decision.validation.violated_rule.value
                if decision.validation.violated_rule
                else None,
                decision.validation.detail,
                decision.upsell.upsell_sku if decision.upsell else None,
                decision.upsell.justification if decision.upsell else None,
                json.dumps(decision.llm_raw_responses),
                razorpay_status,
                razorpay_order_id,
                razorpay_detail,
            ),
        )
        connection.commit()
