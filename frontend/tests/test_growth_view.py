# Tests for the Growth panel's pure data-layer functions.

import json
import sqlite3

import pandas as pd

from audit_view import load_audit_log
from growth_view import compute_growth_metrics, load_catalog_prices

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


def seed_row(connection, **overrides):
    row = {
        "created_at": "2026-09-01T00:00:00+00:00",
        "buyer_id": "agent-1",
        "sku": "SHOE-001",
        "category": "footwear",
        "transaction_amount": 1000.0,
        "validation_approved": 1,
        "violated_rule": None,
        "validation_detail": "ok",
        "upsell_sku": None,
        "upsell_justification": None,
        "llm_raw_responses": "[]",
        "razorpay_status": "failed",
        "razorpay_order_id": None,
        "razorpay_detail": "no keys",
    }
    row.update(overrides)
    connection.execute(
        """
        INSERT INTO audit_log (
            created_at, buyer_id, sku, category, transaction_amount,
            validation_approved, violated_rule, validation_detail,
            upsell_sku, upsell_justification, llm_raw_responses,
            razorpay_status, razorpay_order_id, razorpay_detail
        ) VALUES (:created_at, :buyer_id, :sku, :category, :transaction_amount,
            :validation_approved, :violated_rule, :validation_detail,
            :upsell_sku, :upsell_justification, :llm_raw_responses,
            :razorpay_status, :razorpay_order_id, :razorpay_detail)
        """,
        row,
    )


def make_df(rows):
    return pd.DataFrame(rows)


def test_load_catalog_prices_returns_empty_dict_when_file_missing(tmp_path):
    assert load_catalog_prices(tmp_path / "missing.json") == {}


def test_load_catalog_prices_reads_sku_to_price_mapping(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {"sku": "SHOE-001", "name": "Shoe", "price": 2499.0, "category": "footwear", "stock": 1, "upsell_eligible": False},
                {"sku": "SOCK-010", "name": "Socks", "price": 399.0, "category": "footwear", "stock": 1, "upsell_eligible": True},
            ]
        ),
        encoding="utf-8",
    )
    assert load_catalog_prices(catalog_path) == {"SHOE-001": 2499.0, "SOCK-010": 399.0}


def test_compute_growth_metrics_returns_none_when_no_approved_decisions():
    df = make_df([{"validation_approved": 0, "upsell_sku": None, "transaction_amount": 2499.0}])
    assert compute_growth_metrics(df, {}) is None


def test_compute_growth_metrics_ignores_refused_rows():
    df = make_df(
        [
            {"validation_approved": 1, "upsell_sku": None, "transaction_amount": 1000.0},
            {"validation_approved": 0, "upsell_sku": None, "transaction_amount": 999999.0},
        ]
    )
    metrics = compute_growth_metrics(df, {})
    assert metrics["total_approved"] == 1
    assert metrics["baseline_aov"] == 1000.0


def test_compute_growth_metrics_acceptance_rate_and_aov_lift():
    df = make_df(
        [
            {"validation_approved": 1, "upsell_sku": None, "transaction_amount": 1000.0},
            {"validation_approved": 1, "upsell_sku": "SOCK-010", "transaction_amount": 1000.0},
        ]
    )
    metrics = compute_growth_metrics(df, {"SOCK-010": 400.0})

    assert metrics["total_approved"] == 2
    assert metrics["upsell_count"] == 1
    assert metrics["acceptance_rate"] == 0.5
    assert metrics["baseline_aov"] == 1000.0
    assert metrics["projected_aov"] == 1200.0  # (1000 + (1000+400)) / 2
    assert round(metrics["aov_lift_pct"], 2) == 20.0


def test_compute_growth_metrics_missing_catalog_price_degrades_to_zero_contribution():
    df = make_df([{"validation_approved": 1, "upsell_sku": "GHOST-SKU", "transaction_amount": 1000.0}])
    metrics = compute_growth_metrics(df, {})  # SKU not in the price lookup
    assert metrics["baseline_aov"] == 1000.0
    assert metrics["projected_aov"] == 1000.0


def test_compute_growth_metrics_against_a_real_sqlite_roundtrip(tmp_path):
    # Regression test for the NaN-vs-None bug caught in the Trust panel:
    # confirms this module's NULL handling works against data that has
    # actually round-tripped through SQLite (where a NULL upsell_sku comes
    # back as NaN, not None), not just a hand-built DataFrame.
    db_path = tmp_path / "audit.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(SCHEMA)
        seed_row(connection, buyer_id="agent-1")  # approved, no upsell
        seed_row(
            connection,
            buyer_id="agent-2",
            upsell_sku="SOCK-010",
            upsell_justification="fits the budget",
        )
        connection.commit()

    df = load_audit_log(db_path)
    metrics = compute_growth_metrics(df, {"SOCK-010": 400.0})

    assert metrics["total_approved"] == 2
    assert metrics["upsell_count"] == 1  # must not be miscounted due to NaN truthiness
    assert metrics["acceptance_rate"] == 0.5
