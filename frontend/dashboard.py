# Trust panel - live audit dashboard.
#
# Reads directly from the same SQLite table the backend's audit log writes
# to (Step 8) - there's no separate data path here, so what this page shows
# is exactly what happened, not a summary computed elsewhere. Refused
# decisions are visually distinct from approved/upsold ones (icon + row
# color), per the project's requirement.
#
# The Growth panel (Step 10) is meant to sit alongside this page, not
# replace it - see the note at the bottom of this file when that gets built.

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

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "audit_log.db"
DB_PATH = Path(os.environ.get("AUDIT_LOG_DB_PATH", DEFAULT_DB_PATH))

st.set_page_config(page_title="Agent Gatekeeper - Trust Panel", page_icon="\U0001F6E1", layout="wide")

st.title("\U0001F6E1 Agent Gatekeeper - Trust Panel")
st.caption(
    "Every decision the deterministic validator and the upsell engine have "
    "made, read live from the audit log."
)

if st.button("\U0001F504 Refresh"):
    st.rerun()

df = load_audit_log(DB_PATH)

if df.empty:
    st.info(
        "No decisions logged yet. Start the backend and run "
        "`python scripts/buyer_agent_simulator.py` from `backend/`, then refresh this page."
    )
else:
    df = with_status_columns(df)

    total = len(df)
    approved = int((df["Status"] == STATUS_APPROVED).sum())
    upsold = int((df["Status"] == STATUS_UPSOLD).sum())
    refused = int((df["Status"] == STATUS_REFUSED).sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total decisions", total)
    col2.metric("Approved", approved)
    col3.metric("Upsold", upsold)
    col4.metric("Refused", refused, help=f"{refused / total:.0%} of all logged decisions")

    display_df = df[
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
    st.dataframe(styled, width="stretch", hide_index=True)

    st.subheader("Inspect a decision")
    selected_id = st.selectbox(
        "Row",
        df["id"],
        format_func=lambda row_id: (
            f"#{row_id} - {df.loc[df['id'] == row_id, 'Status'].values[0]} - "
            f"{df.loc[df['id'] == row_id, 'sku'].values[0]}"
        ),
    )
    selected = df[df["id"] == selected_id].iloc[0]

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
