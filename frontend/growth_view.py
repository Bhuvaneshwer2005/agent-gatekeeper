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
import plotly.graph_objects as go

# Shared chart styling so every Growth panel figure reads as one system -
# transparent backgrounds (so the app's own theme shows through, not
# Plotly's default white canvas), the same accent colors as the rest of
# the dashboard, and light text for the dark theme.
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#E5E9F0"),
    margin=dict(l=10, r=10, t=10, b=10),
    showlegend=False,
)
GRID_COLOR = "rgba(255,255,255,0.08)"


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


def top_upsells(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    """Which catalog SKUs the upsell engine has actually proposed most often,
    among approved decisions - a ranking, not just the single acceptance
    rate number, so a merchant can see which upsells are pulling weight.
    """
    approved = df[df["validation_approved"] == 1]
    upsold = approved[approved["upsell_sku"].notna()]
    if upsold.empty:
        return pd.DataFrame(columns=["upsell_sku", "count"])

    counts = upsold["upsell_sku"].value_counts().reset_index()
    counts.columns = ["upsell_sku", "count"]
    return counts.head(limit)


def revenue_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Approved order revenue grouped by the purchased item's category.

    Uses the transaction's own category column already on every audit row -
    no catalog lookup needed, since the category a buyer actually bought in
    is exactly what was logged at decision time.
    """
    approved = df[df["validation_approved"] == 1]
    if approved.empty:
        return pd.DataFrame(columns=["category", "revenue"])

    grouped = approved.groupby("category")["transaction_amount"].sum().reset_index()
    grouped.columns = ["category", "revenue"]
    return grouped.sort_values("revenue", ascending=False).reset_index(drop=True)


def build_aov_comparison_chart(metrics: dict) -> go.Figure:
    """Actual vs. projected AOV as a real bar chart - proper axis, hover
    values, and value labels - instead of two hand-rolled HTML divs.

    Plotly rather than st.bar_chart(): the latter goes through the altair
    package internally, and this project already hit a real crash there -
    an old Streamlit paired with a newer Python broke on altair's own
    TypedDict(closed=True) schema definitions. Plotly is an independent
    charting library with no altair dependency, so it doesn't share that
    failure mode.
    """
    labels = ["Actual", "Projected w/ upsells"]
    values = [metrics["baseline_aov"], metrics["projected_aov"]]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=["#3B82F6", "#22C55E"],
                text=[f"₹{v:,.2f}" for v in values],
                textposition="outside",
                hovertemplate="%{x}: ₹%{y:,.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **CHART_LAYOUT,
        height=280,
        yaxis=dict(title="AOV (INR)", gridcolor=GRID_COLOR, rangemode="tozero"),
        xaxis=dict(gridcolor=GRID_COLOR),
    )
    return fig


def build_revenue_by_category_chart(by_category: pd.DataFrame) -> go.Figure:
    """Revenue by category as a horizontal bar chart, highest first.

    Horizontal rather than vertical: category names read better on their
    own row than rotated or truncated under a vertical bar, especially
    once the catalog has more than a couple of categories.
    """
    fig = go.Figure(
        data=[
            go.Bar(
                x=by_category["revenue"],
                y=by_category["category"],
                orientation="h",
                marker_color="#3B82F6",
                text=[f"₹{v:,.2f}" for v in by_category["revenue"]],
                textposition="outside",
                hovertemplate="%{y}: ₹%{x:,.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **CHART_LAYOUT,
        height=max(220, 55 * len(by_category)),
        xaxis=dict(title="Revenue (INR)", gridcolor=GRID_COLOR, rangemode="tozero"),
        # Reversed so the highest-revenue category (first row, since the
        # caller already sorts descending) renders at the top, matching
        # reading order instead of Plotly's bottom-up default for bars.
        yaxis=dict(autorange="reversed", gridcolor=GRID_COLOR),
    )
    return fig
