# Pure data-layer functions for the Growth panel: upsell acceptance rate
# and AOV lift, computed from the same audit log the Trust panel reads.
# Kept separate from dashboard.py for the same reason as audit_view.py -
# so this logic is unit-testable with plain pytest, not a Streamlit
# harness.
#
# Neither metric has a real "did the buyer actually pay for the upsell"
# signal to draw on: Step 7 deliberately never folds a proposed upsell
# into the Razorpay charge (it's a suggestion, not a confirmed add-on),
# and no later step asks the buyer agent whether it accepts one. Both
# metrics are computed on that same honest basis instead of inventing a
# fake acceptance signal:
#   - "acceptance" means the upsell engine successfully proposed a valid
#     upsell that passed every guardrail in Step 6 - the system's actual
#     final output, since no rejection step exists yet.
#   - AOV lift compares the real, charged average order value against the
#     hypothetical value if every proposed upsell had been bought - it is
#     a projection of upside, not a claim that revenue already grew.
# The dashboard surfaces this assumption directly (see the help text on
# the acceptance-rate metric) rather than leaving it implicit.

import json
from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd


def load_catalog_prices(catalog_path: Union[str, Path]) -> Dict[str, float]:
    """Read the product catalog and return a sku -> price lookup.

    Returns an empty dict if the catalog file is missing, rather than
    raising - a growth metric that can't price one proposed upsell should
    degrade that upsell's contribution to zero, not crash the whole panel.
    """
    catalog_path = Path(catalog_path)
    if not catalog_path.exists():
        return {}
    items = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {item["sku"]: item["price"] for item in items}


def compute_growth_metrics(
    df: pd.DataFrame, catalog_prices: Dict[str, float]
) -> Optional[dict]:
    """Compute upsell acceptance rate and AOV lift from approved decisions.

    Scoped to approved decisions only - a refused decision was never
    charged, so it has no order value to fold into an *average order*
    value. Returns None when there are no approved decisions yet, since
    there is nothing to compute a rate or an average over.
    """
    approved = df[df["validation_approved"] == 1]
    if approved.empty:
        return None

    has_upsell = approved["upsell_sku"].notna()
    upsell_count = int(has_upsell.sum())
    total_approved = len(approved)
    acceptance_rate = upsell_count / total_approved

    baseline_aov = float(approved["transaction_amount"].mean())

    def projected_amount(row: pd.Series) -> float:
        if pd.notna(row["upsell_sku"]):
            return row["transaction_amount"] + catalog_prices.get(row["upsell_sku"], 0.0)
        return row["transaction_amount"]

    projected_aov = float(approved.apply(projected_amount, axis=1).mean())
    aov_lift_pct = (
        ((projected_aov - baseline_aov) / baseline_aov) * 100 if baseline_aov else 0.0
    )

    return {
        "total_approved": total_approved,
        "upsell_count": upsell_count,
        "acceptance_rate": acceptance_rate,
        "baseline_aov": baseline_aov,
        "projected_aov": projected_aov,
        "aov_lift_pct": aov_lift_pct,
    }
