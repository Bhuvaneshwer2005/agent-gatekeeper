# Tests for the Active Mandates tab's pure display logic. No network -
# issue_mandate/fetch_mandates are thin httpx wrappers, same as
# fetch_scenarios/run_scenario in live_demo_view.py, and untested at the
# unit level for the same reason those are.

import pandas as pd

from mandate_registry_view import highlight_by_mandate_status, summarize_mandates


def test_highlight_by_mandate_status_gives_each_status_its_own_color():
    rows = pd.DataFrame([{"Status": "Active"}, {"Status": "Exhausted"}, {"Status": "Expired"}])
    colors = {row["Status"]: highlight_by_mandate_status(row)[0] for _, row in rows.iterrows()}

    assert colors["Active"] != colors["Exhausted"]
    assert colors["Active"] != colors["Expired"]
    assert colors["Exhausted"] != colors["Expired"]


def test_highlight_by_mandate_status_falls_back_for_unknown_status():
    row = pd.Series({"Status": "Something else"})
    assert highlight_by_mandate_status(row) == [""]


def test_summarize_mandates_counts_each_status():
    mandates = [
        {"status": "active"},
        {"status": "active"},
        {"status": "exhausted"},
        {"status": "expired"},
    ]
    counts = summarize_mandates(mandates)
    assert counts == {"active": 2, "exhausted": 1, "expired": 1}


def test_summarize_mandates_zero_fills_missing_statuses():
    counts = summarize_mandates([{"status": "active"}])
    assert counts == {"active": 1, "exhausted": 0, "expired": 0}


def test_summarize_mandates_handles_empty_list():
    assert summarize_mandates([]) == {"active": 0, "exhausted": 0, "expired": 0}
