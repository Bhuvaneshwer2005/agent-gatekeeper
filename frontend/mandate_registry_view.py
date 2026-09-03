# Pure data-layer functions for the Active Mandates tab: issuing a mandate
# through the registry, listing what's been issued, and the small bits of
# display logic (status icon, status counts) worth keeping out of
# dashboard.py so they're unit-testable.

from typing import Any, Dict, List

import httpx

STATUS_ICONS = {"active": "\U0001F7E2", "exhausted": "\U0001F7E0", "expired": "\U0001F534"}


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


def status_icon(status: str) -> str:
    return STATUS_ICONS.get(status, "⚪")


def summarize_mandates(mandates: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count mandates by status, for a quick totals row above the table."""
    counts = {"active": 0, "exhausted": 0, "expired": 0}
    for mandate in mandates:
        counts[mandate["status"]] = counts.get(mandate["status"], 0) + 1
    return counts
