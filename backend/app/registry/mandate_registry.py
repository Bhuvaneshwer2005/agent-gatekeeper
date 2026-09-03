# Persisted mandate registry.
#
# Every mandate handled by /decide up to this point has been stateless: a
# buyer agent hands over a fresh mandate object with every single request,
# and nothing remembers it afterward. That's fine for a one-shot purchase,
# but it leaves a real gap - nothing stops an agent from staying under a
# per-transaction budget cap across many small purchases while blowing well
# past what the mandate actually authorized in total (the same "salami
# slicing" risk a merchant would worry about with a real spending limit).
#
# This module gives a mandate a real identity: issue it once via
# issue_mandate(), get a mandate_id back, and every purchase charged against
# that id draws down a persisted budget_spent instead of getting a fresh
# full budget_max to work with each time. This is purely additive - a
# mandate submitted inline to /decide (as every existing scenario, the
# custom mandate builder, and the whole stress-test batch still do) never
# touches this table and behaves exactly as it always has.
#
# Shares audit_log.db rather than a separate file - one SQLite file for all
# of the app's runtime state is simpler to reason about and gitignore than
# several, and there's no reason for these tables to live elsewhere.

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.mandate import Mandate

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "audit_log.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mandates (
    mandate_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    buyer_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    budget_max REAL NOT NULL,
    category_allowlist TEXT NOT NULL,
    expiry TEXT NOT NULL,
    budget_spent REAL NOT NULL DEFAULT 0
);
"""


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(_SCHEMA)
    connection.row_factory = sqlite3.Row
    return connection


def _with_computed_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """Add status and budget_remaining, computed fresh against the current
    time rather than stored - status can change just by time passing (an
    active mandate becomes expired) with no write ever happening, so
    persisting it would just mean it could go stale.
    """
    now = datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(row["expiry"])
    budget_remaining = max(row["budget_max"] - row["budget_spent"], 0.0)

    if expiry <= now:
        status = "expired"
    elif budget_remaining <= 0:
        status = "exhausted"
    else:
        status = "active"

    return {
        **row,
        "category_allowlist": json.loads(row["category_allowlist"]),
        "budget_remaining": budget_remaining,
        "status": status,
    }


def issue_mandate(mandate: Mandate) -> Dict[str, Any]:
    """Persist a new mandate and return it with a freshly assigned id.

    Structural validation (required fields, positive budget, non-blank
    categories, an aware expiry) already happened when the request body
    parsed as a Mandate - this function only ever handles a mandate that's
    already valid on its face; whether it's still active is a matter of
    time and spend from here on, not shape.
    """
    mandate_id = f"mnd_{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(_get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO mandates (
                mandate_id, created_at, buyer_id, intent, budget_max,
                category_allowlist, expiry, budget_spent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                mandate_id,
                created_at,
                mandate.buyer_id,
                mandate.intent,
                mandate.budget_max,
                json.dumps(mandate.category_allowlist),
                mandate.expiry.isoformat(),
            ),
        )
        connection.commit()

    return get_mandate(mandate_id)


def get_mandate(mandate_id: str) -> Optional[Dict[str, Any]]:
    with closing(_get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM mandates WHERE mandate_id = ?", (mandate_id,)
        ).fetchone()
    if row is None:
        return None
    return _with_computed_fields(dict(row))


def list_mandates() -> List[Dict[str, Any]]:
    with closing(_get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM mandates ORDER BY created_at DESC"
        ).fetchall()
    return [_with_computed_fields(dict(row)) for row in rows]


def record_spend(mandate_id: str, amount: float) -> None:
    """Draw down a mandate's persisted budget after an approved purchase.

    Called only for a transaction the validator has already approved -
    a declined one never reaches here, so budget_spent only ever reflects
    purchases that genuinely happened against this mandate, the same way
    the audit log only records what the pipeline actually did.
    """
    with closing(_get_connection()) as connection:
        connection.execute(
            "UPDATE mandates SET budget_spent = budget_spent + ? WHERE mandate_id = ?",
            (amount, mandate_id),
        )
        connection.commit()
