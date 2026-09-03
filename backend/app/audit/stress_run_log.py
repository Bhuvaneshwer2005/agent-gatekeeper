# Durable record of stress-test runs.
#
# The Stress Test tab grades its batch client-side (the frontend already
# has the case list with its expected outcomes) - this module exists only
# to persist the graded result of a run so it survives a page refresh or a
# tab switch, which Streamlit's session state does not. One row per run,
# holding the summary and the full per-case verdict list together, so
# reloading the latest run is a single read, not a reassembly.
#
# Shares audit_log.db, same as mandate_registry.py - one file for all of
# the app's runtime state.

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "audit_log.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stress_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    total INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    by_group TEXT NOT NULL,
    results TEXT NOT NULL
);
"""


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(_SCHEMA)
    connection.row_factory = sqlite3.Row
    return connection


def log_stress_run(summary: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    """Persist one graded stress-test run.

    summary is the {total, passed, failed, by_group} shape the frontend's
    summarize() already computes; results is the full list of per-case
    verdicts. Both are stored as-is (as JSON) rather than re-derived here,
    since the grading rules live in stress_test_view.py, not this module -
    this is a record of what was graded, not a second grader.
    """
    with closing(_get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO stress_runs (created_at, total, passed, failed, by_group, results)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                summary["total"],
                summary["passed"],
                summary["failed"],
                json.dumps(summary["by_group"]),
                json.dumps(results),
            ),
        )
        connection.commit()


def get_latest_stress_run() -> Optional[Dict[str, Any]]:
    """Return the most recently logged stress run, or None if none exist yet."""
    with closing(_get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM stress_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None

    record = dict(row)
    record["by_group"] = json.loads(record["by_group"])
    record["results"] = json.loads(record["results"])
    return record
