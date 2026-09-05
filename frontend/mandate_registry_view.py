# Pure data-layer functions for the Active Mandates tab: issuing a mandate
# through the registry, listing what's been issued, and the small bits of
# display logic (status counts, status color) worth keeping out of
# dashboard.py so they're unit-testable.

from typing import Any, Dict, List

import httpx

# Same light-pastel-background-plus-dark-text pattern as audit_view.py's
# highlight_by_status - keyed on the capitalized display text a row
# actually shows, not the raw lowercase status field, and legible in both
# themes for the same reason: Streamlit's dark-theme text is too light to
# read against a light pastel background otherwise.
STATUS_COLORS = {
    "Active": "#e6f4ea",
    "Exhausted": "#fff4e0",
    "Expired": "#fdecea",
}


def issue_mandate(base_url: str, mandate: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
    """POST a new mandate to the registry and return the issued record, mandate_id included."""
    response = httpx.post(f"{base_url}/mandates", json=mandate, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_mandates(base_url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch every mandate ever issued, each with live status and remaining budget."""
    response = httpx.get(f"{base_url}/mandates", timeout=timeout)
    response.raise_for_status()
    return response.json()


def highlight_by_mandate_status(row) -> list:
    """Row-level background + text color for a Styler.apply(axis=1) call,
    mirroring audit_view.highlight_by_status - same reasoning, applied to
    mandate status instead of decision status.
    """
    color = STATUS_COLORS.get(row.get("Status"), "")
    style = f"background-color: {color}; color: #111111" if color else ""
    return [style] * len(row)


def summarize_mandates(mandates: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count mandates by status, for a quick totals row above the table."""
    counts = {"active": 0, "exhausted": 0, "expired": 0}
    for mandate in mandates:
        counts[mandate["status"]] = counts.get(mandate["status"], 0) + 1
    return counts
