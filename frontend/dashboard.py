# Agent Gatekeeper dashboard: Trust panel + Growth panel.
#
# Both panels read the same audit log (Step 8) - there's no separate data
# path for either one, so what they show is exactly what happened, not a
# summary computed elsewhere. They're kept in separate tabs, not stacked
# on one long page, so they read as two distinct views rather than one
# panel with a "and also here's growth" afterthought tacked on.

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from audit_view import (
    STATUS_APPROVED,
    STATUS_REFUSED,
    STATUS_UPSOLD,
    highlight_by_status,
    load_audit_log,
    with_status_columns,
)
from growth_view import compute_growth_metrics, load_catalog_prices

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "audit_log.db"
DB_PATH = Path(os.environ.get("AUDIT_LOG_DB_PATH", DEFAULT_DB_PATH))

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "catalog.json"
CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", DEFAULT_CATALOG_PATH))

st.set_page_config(page_title="Agent Gatekeeper", page_icon="\U0001F6E1", layout="wide")

st.title("Agent Gatekeeper")

if st.button("\U0001F504 Refresh"):
    st.rerun()

df = load_audit_log(DB_PATH)

trust_tab, growth_tab = st.tabs(["\U0001F6E1 Trust Panel", "\U0001F4C8 Growth Panel"])

with trust_tab:
    st.caption(
        "Every decision the deterministic validator and the upsell engine have "
        "made, read live from the audit log."
    )

    if df.empty:
        st.info(
            "No decisions logged yet. Start the backend and run "
            "`python scripts/buyer_agent_simulator.py` from `backend/`, then refresh this page."
        )
    else:
        trust_df = with_status_columns(df)

        total = len(trust_df)
        approved = int((trust_df["Status"] == STATUS_APPROVED).sum())
        upsold = int((trust_df["Status"] == STATUS_UPSOLD).sum())
        refused = int((trust_df["Status"] == STATUS_REFUSED).sum())

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total decisions", total)
        col2.metric("Approved", approved)
        col3.metric("Upsold", upsold)
        col4.metric("Refused", refused, help=f"{refused / total:.0%} of all logged decisions")

        display_df = trust_df[
            [
                "Icon",
                "Status",
                "created_at",
                "buyer_id",
                "sku",
                "transaction_amount",
                "violated_rule",
                "upsell_sku",
                "razorpay_status",
            ]
        ].rename(
            columns={
                "created_at": "Time (UTC)",
                "buyer_id": "Buyer",
                "sku": "SKU",
                "transaction_amount": "Amount (INR)",
                "violated_rule": "Refusal reason",
                "upsell_sku": "Upsell",
                "razorpay_status": "Razorpay",
            }
        )
        display_df["Amount (INR)"] = display_df["Amount (INR)"].map(lambda amount: f"₹{amount:,.2f}")
        display_df = display_df.fillna("-")

        styled = display_df.style.apply(highlight_by_status, axis=1)
        # use_container_width, not width="stretch": the latter is only
        # valid on newer Streamlit releases (width used to be pixels-only),
        # and pip won't upgrade an already-installed older Streamlit just
        # because requirements.txt lists it unpinned - found on a machine
        # with a pre-existing global Streamlit 1.40.1, where the string
        # crashed with "'str' object cannot be interpreted as an integer".
        # use_container_width is older and deprecated, but still works on
        # every version this project has actually been tested against.
        st.dataframe(styled, use_container_width=True, hide_index=True)

        st.subheader("Inspect a decision")
        selected_id = st.selectbox(
            "Row",
            trust_df["id"],
            format_func=lambda row_id: (
                f"#{row_id} - {trust_df.loc[trust_df['id'] == row_id, 'Status'].values[0]} - "
                f"{trust_df.loc[trust_df['id'] == row_id, 'sku'].values[0]}"
            ),
        )
        selected = trust_df[trust_df["id"] == selected_id].iloc[0]

        st.write(f"**Validation detail:** {selected['validation_detail']}")
        # NULL text columns come back from pandas as NaN, which is truthy in
        # Python - pd.notna() is the correct "is this actually present" check.
        if pd.notna(selected["upsell_justification"]):
            st.write(f"**Upsell justification:** {selected['upsell_justification']}")
        if pd.notna(selected["razorpay_detail"]):
            st.write(f"**Razorpay detail:** {selected['razorpay_detail']}")

        raw_responses = json.loads(selected["llm_raw_responses"]) if selected["llm_raw_responses"] else []
        if raw_responses:
            with st.expander(f"Raw LLM response(s) ({len(raw_responses)} attempt(s))"):
                for raw in raw_responses:
                    st.code(raw, language="json")

with growth_tab:
    st.caption(
        "Upsell acceptance rate and AOV lift, computed from the same approved "
        "decisions the Trust panel shows."
    )

    if df.empty:
        st.info(
            "No decisions logged yet. Start the backend and run "
            "`python scripts/buyer_agent_simulator.py` from `backend/`, then refresh this page."
        )
    else:
        catalog_prices = load_catalog_prices(CATALOG_PATH)
        metrics = compute_growth_metrics(df, catalog_prices)

        if metrics is None:
            st.info("No approved decisions yet - nothing has an order value to measure growth from.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Approved orders", metrics["total_approved"])
            col2.metric(
                "Upsell acceptance rate",
                f"{metrics['acceptance_rate']:.0%}",
                help=(
                    "An upsell counts as accepted once the engine successfully "
                    "proposes one that passes every guardrail in Step 6 - this "
                    "build has no separate buyer confirmation step, so proposal "
                    "and acceptance are the same event here."
                ),
            )
            col3.metric("AOV (actual)", f"₹{metrics['baseline_aov']:,.2f}")
            col4.metric(
                "AOV (projected w/ upsells)",
                f"₹{metrics['projected_aov']:,.2f}",
                delta=f"{metrics['aov_lift_pct']:+.1f}%",
                help=(
                    "Projected: what AOV would be if every proposed upsell had "
                    "been bought. Step 7 never adds a proposed upsell to the "
                    "actual Razorpay charge, so this is a measure of upside the "
                    "upsell engine is surfacing, not revenue already captured."
                ),
            )

            # A hand-rolled HTML bar instead of st.bar_chart(): the latter
            # imports altair internally, and an older Streamlit paired with
            # a newer Python can hit a real incompatibility there (altair's
            # schema uses TypedDict(closed=True), a typing feature not every
            # Python/typing_extensions combo supports) - found live on a
            # machine with Streamlit 1.40.1 on Python 3.14. Plain HTML has
            # no such dependency and works on any Streamlit version.
            max_aov = max(metrics["baseline_aov"], metrics["projected_aov"]) or 1
            for label, value in (
                ("Actual", metrics["baseline_aov"]),
                ("Projected w/ upsells", metrics["projected_aov"]),
            ):
                bar_pct = value / max_aov * 100
                st.markdown(
                    f"""
                    <div style="margin-bottom: 0.75rem;">
                      <div style="font-size: 0.85rem; margin-bottom: 0.25rem;">{label}</div>
                      <div style="background: rgba(128,128,128,0.25); border-radius: 4px; overflow: hidden;">
                        <div style="background: #6c8ef5; width: {bar_pct:.1f}%; padding: 0.4rem 0.6rem;
                                    color: white; font-size: 0.85rem; white-space: nowrap;">
                          ₹{value:,.2f}
                        </div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
