# Tests for the Trust panel's pure data-layer functions - no Streamlit
# involved, just reading and classifying audit log rows against a temp
# SQLite database.

import sqlite3

from audit_view import (
    STATUS_APPROVED,
    STATUS_REFUSED,
    STATUS_UPSOLD,
    classify_status,
    highlight_by_status,
    load_audit_log,
    with_status_columns,
)

SCHEMA = """
CREATE TABLE audit_log (
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

APPROVED_ROW = (
    "2026-09-01T00:00:00+00:00", "agent-1", "SHOE-001", "footwear", 2499.0,
    1, None, "ok", None, None, "[]", "failed", None, "no keys",
)
UPSOLD_ROW = (
    "2026-09-01T00:01:00+00:00", "agent-2", "SHOE-001", "footwear", 2499.0,
    1, None, "ok", "SOCK-010", "fits the budget", '["raw"]', "created", "order_1", None,
)
REFUSED_ROW = (
    "2026-09-01T00:02:00+00:00", "agent-3", "SHOE-001", "footwear", 2499.0,
    0, "budget_exceeded", "over budget", None, None, "[]", "skipped", None, None,
)


def seed_db(db_path, rows):
    with sqlite3.connect(db_path) as connection:
        connection.execute(SCHEMA)
        for row in rows:
            connection.execute(
                """
                INSERT INTO audit_log (
                    created_at, buyer_id, sku, category, transaction_amount,
                    validation_approved, violated_rule, validation_detail,
                    upsell_sku, upsell_justification, llm_raw_responses,
                    razorpay_status, razorpay_order_id, razorpay_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        connection.commit()


def test_load_audit_log_returns_empty_dataframe_when_db_missing(tmp_path):
    df = load_audit_log(tmp_path / "does_not_exist.db")
    assert df.empty


def test_load_audit_log_returns_empty_dataframe_when_file_exists_but_table_does_not(tmp_path):
    # Regression test: the db file is shared with the mandate registry and
    # stress-run tables, each created independently on first use. On a
    # fresh deployment, another tab's backend call can create this file
    # with one of those tables before /decide has ever run - so the file
    # existing is not proof the audit_log table does. Caught live on a
    # fresh Render deploy where the Trust panel crashed with
    # "no such table: audit_log" despite the db file being present.
    db_path = tmp_path / "audit.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE mandates (mandate_id TEXT PRIMARY KEY)")
        connection.commit()

    df = load_audit_log(db_path)
    assert df.empty


def test_load_audit_log_reads_rows_newest_first(tmp_path):
    db_path = tmp_path / "audit.db"
    seed_db(db_path, [APPROVED_ROW, UPSOLD_ROW])

    df = load_audit_log(db_path)

    assert len(df) == 2
    assert df.iloc[0]["buyer_id"] == "agent-2"  # inserted second - newest first


def test_classify_status_covers_all_three_outcomes():
    assert classify_status(1, None) == STATUS_APPROVED
    assert classify_status(1, "SOCK-010") == STATUS_UPSOLD
    assert classify_status(0, None) == STATUS_REFUSED
    assert classify_status(0, "SOCK-010") == STATUS_REFUSED  # declined wins regardless of upsell


def test_with_status_columns_labels_each_row_correctly(tmp_path):
    db_path = tmp_path / "audit.db"
    seed_db(db_path, [APPROVED_ROW, UPSOLD_ROW, REFUSED_ROW])

    df = with_status_columns(load_audit_log(db_path))
    statuses = dict(zip(df["buyer_id"], df["Status"]))

    assert statuses["agent-1"] == STATUS_APPROVED
    assert statuses["agent-2"] == STATUS_UPSOLD
    assert statuses["agent-3"] == STATUS_REFUSED


def test_refused_rows_are_a_different_color_from_approved_and_upsold(tmp_path):
    db_path = tmp_path / "audit.db"
    seed_db(db_path, [APPROVED_ROW, UPSOLD_ROW, REFUSED_ROW])
    df = with_status_columns(load_audit_log(db_path))

    colors = {row["Status"]: highlight_by_status(row)[0] for _, row in df.iterrows()}

    assert colors[STATUS_REFUSED] != colors[STATUS_APPROVED]
    assert colors[STATUS_REFUSED] != colors[STATUS_UPSOLD]
    assert colors[STATUS_APPROVED] != colors[STATUS_UPSOLD]
