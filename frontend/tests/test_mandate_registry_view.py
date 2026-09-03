# Tests for the Active Mandates tab's pure display logic. No network -
# issue_mandate/fetch_mandates are thin httpx wrappers, same as
# fetch_scenarios/run_scenario in live_demo_view.py, and untested at the
# unit level for the same reason those are.

from mandate_registry_view import status_icon, summarize_mandates


def test_status_icon_known_statuses():
    assert status_icon("active") != status_icon("exhausted") != status_icon("expired")


def test_status_icon_falls_back_for_unknown_status():
    assert status_icon("something-new") == "⚪"


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
