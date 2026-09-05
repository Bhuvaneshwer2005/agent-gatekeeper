# Pure data-layer functions for the Trust panel dashboard: reading and
# classifying audit log rows. Kept separate from dashboard.py, which only
# calls Streamlit rendering functions, so this logic can be unit tested
# with plain pytest instead of a Streamlit test harness.

import sqlite3
from pathlib import Path
from typing import Union

import pandas as pd

STATUS_APPROVED = "Approved"
STATUS_UPSOLD = "Upsold"
STATUS_REFUSED = "Refused"

STATUS_ICONS = {
    STATUS_APPROVED: "✅",  # checkmark
    STATUS_UPSOLD: "\U0001F53C",  # up arrow
    STATUS_REFUSED: "❌",  # cross mark
}

STATUS_COLORS = {
    STATUS_APPROVED: "#e6f4ea",
    STATUS_UPSOLD: "#e8eefc",
    STATUS_REFUSED: "#fdecea",
}


def load_audit_log(db_path: Union[str, Path]) -> pd.DataFrame:
    """Read every row of the audit log, newest first.

    Returns an empty DataFrame if the database file doesn't exist yet, or
    if it exists but has no audit_log table yet - both just mean /decide
    hasn't been called by anything, not an error. The second case is real:
    this file also holds the mandate registry and stress-run tables, each
    created independently by its own backend module on first use, so a
    fresh deployment can end up with an audit_log.db that has a mandates
    table (someone opened the Active Mandates tab first) but no audit_log
    table yet (nothing has gone through /decide). A bare file-existence
    check can't tell those two apart.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as connection:
        table_exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
        ).fetchone()
        if table_exists is None:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM audit_log ORDER BY id DESC", connection)


def classify_status(validation_approved, upsell_sku) -> str:
    """Map the raw audit columns to the project's own approved/upsold/
    refused framing.

    Three-way, not just approved/declined: an approved purchase that also
    got an upsell proposal is a meaningfully different outcome from a plain
    approval, and the Growth panel (Step 10) will care about that
    distinction specifically.

    A NULL upsell_sku comes back from pandas as NaN (a float), not None -
    and NaN is truthy in Python, so a plain `if upsell_sku:` would
    misclassify every non-upsold approval as upsold. pd.notna() is the
    correct check regardless of whether the caller passes None or NaN.
    """
    if not validation_approved:
        return STATUS_REFUSED
    if pd.notna(upsell_sku) and upsell_sku:
        return STATUS_UPSOLD
    return STATUS_APPROVED


def with_status_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add Status and Icon columns derived from the raw audit log columns."""
    df = df.copy()
    df["Status"] = [
        classify_status(approved, sku)
        for approved, sku in zip(df["validation_approved"], df["upsell_sku"])
    ]
    df["Icon"] = df["Status"].map(STATUS_ICONS)
    return df


def highlight_by_status(row: pd.Series) -> list:
    """Row-level background + text color for a Styler.apply(axis=1) call.

    Refused rows need to be visually distinct from approved/upsold ones at
    a glance - not just distinguishable by reading the text of every row -
    so each status gets its own color, not just refused-vs-everything-else.

    Text color is set explicitly, not just background: these are light
    pastel backgrounds, and Streamlit's dark theme default cell text is
    light gray, which is nearly unreadable on top of them. Forcing a dark,
    near-black text color keeps every row legible in both themes.
    """
    color = STATUS_COLORS.get(row.get("Status"), "")
    style = f"background-color: {color}; color: #111111" if color else ""
    return [style] * len(row)
