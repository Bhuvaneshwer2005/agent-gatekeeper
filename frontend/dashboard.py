# Agent Gatekeeper dashboard: a homepage, then Trust panel + Growth panel +
# Live demo + Stress test + Active Mandates once "Enter Dashboard" is
# clicked. The homepage is gated behind one session_state flag rather than
# a second Streamlit page, so the whole app stays one URL - the right
# tradeoff for a single-container deploy where there's no router in front
# of it to send /home and /app to different places.
#
# Trust and Growth read the same audit log (Step 8) - there's no separate
# data path for either one, so what they show is exactly what happened, not
# a summary computed elsewhere. Live demo, Stress test, and Active Mandates
# are the odd ones out: all three talk to the backend over HTTP, because
# they drive new decisions or new state rather than reporting on old ones -
# Live demo runs one mandate at a time and shows it step by step, Stress
# test runs a large generated batch and grades the results, and Active
# Mandates issues and tracks mandates that persist across multiple
# purchases instead of getting a fresh budget on every call.
#
# All five are separate tabs, not stacked on one long page, so they read as
# distinct views rather than one panel with the others tacked on.

import json
import os
from datetime import datetime, timedelta, timezone
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
from growth_view import (
    build_aov_comparison_chart,
    build_revenue_by_category_chart,
    compute_growth_metrics,
    load_catalog_prices,
    revenue_by_category,
    top_upsells,
)
from homepage_view import APP_NAME, CTA_LABEL, FEATURES, FLOW_STEPS, PITCH, TAGLINE
from live_demo_view import BLOCKED, OK, derive_steps, fetch_catalog, fetch_scenarios, outcome_summary, run_scenario
from mandate_registry_view import fetch_mandates, issue_mandate, status_icon, summarize_mandates
from stress_test_view import (
    FAILED,
    evaluate_case,
    fetch_latest_stress_run,
    fetch_stress_cases,
    submit_stress_run,
    summarize,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "audit_log.db"
DB_PATH = Path(os.environ.get("AUDIT_LOG_DB_PATH", DEFAULT_DB_PATH))

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "catalog.json"
CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", DEFAULT_CATALOG_PATH))

BACKEND_URL = os.environ.get("AGENT_GATEKEEPER_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title=APP_NAME, page_icon="\U0001F6E1", layout="wide")

# Global polish on top of the custom theme in .streamlit/config.toml - card
# treatment for metrics and the homepage's own feature/flow blocks, tighter
# default padding, and a consistent border radius. Selectors like
# data-testid="stMetric" are Streamlit's own internal DOM hooks: if a given
# Streamlit version doesn't have them, the rule just never matches (a CSS
# selector miss is silent, unlike a Python kwarg mismatch), so this can't
# break the app on an older Streamlit the way a real API change could.
st.markdown(
    """
    <style>
    .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1150px; }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 10px;
        padding: 0.9rem 0.8rem;
    }
    /* !important throughout: Streamlit's own stylesheet sets the metric
       label to a single truncated line, and it's a toss-up whether that
       rule or this one wins the cascade on any given Streamlit version -
       !important makes sure this one always does. */
    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricLabel"] * {
        overflow: visible !important;
        white-space: normal !important;
        text-overflow: unset !important;
        max-width: none !important;
    }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    /* Streamlit's default button padding (4px 12px) is sized for a text
       label, not a single centered glyph - on a single-emoji button that
       leaves the icon looking small and off-center rather than filling a
       clean square. These two keyed buttons get their own fixed-size,
       fully-centered treatment instead. */
    div.st-key-home_button button, div.st-key-refresh_button button {
        width: 44px !important;
        height: 44px !important;
        min-width: 44px !important;
        padding: 0 !important;
        font-size: 1.4rem !important;
        line-height: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .hero-badge {
        display: inline-block;
        background: rgba(59,130,246,0.15);
        color: #7fb2ff;
        border: 1px solid rgba(59,130,246,0.35);
        border-radius: 999px;
        padding: 0.25rem 0.9rem;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .flow-card, .feature-card {
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 12px;
        padding: 1.3rem 1.2rem;
        height: 100%;
    }
    /* A metric card built from plain HTML, not st.metric - used wherever
       a label is long enough that Streamlit's own metric component
       truncates it (its label truncation turned out to be enforced in a
       way no CSS override could reach, not just a text-overflow rule). */
    .custom-metric {
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 10px;
        padding: 0.9rem 1rem;
        height: 100%;
    }
    .custom-metric .cm-label { font-size: 0.875rem; color: #9aa4b2; line-height: 1.3; margin-bottom: 0.35rem; }
    .custom-metric .cm-value { font-size: 1.9rem; font-weight: 600; line-height: 1.2; }
    .custom-metric .cm-delta {
        display: inline-block; margin-top: 0.4rem; font-size: 0.8rem;
        padding: 0.1rem 0.55rem; border-radius: 999px;
    }
    .custom-metric .cm-delta.positive { background: rgba(34,197,94,0.15); color: #4ade80; }
    .custom-metric .cm-delta.negative { background: rgba(239,68,68,0.15); color: #f87171; }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_metric_card(column, label: str, value: str, delta: str = None, help_text: str = None) -> None:
    """A metric rendered as plain HTML instead of st.metric.

    Used specifically where the label is long enough to hit Streamlit's
    own metric-label truncation - that turned out to be enforced somewhere
    CSS overrides couldn't reach, so this sidesteps st.metric entirely for
    those cases rather than fighting it further.
    """
    delta_html = ""
    if delta is not None:
        sign_class = "positive" if delta.strip().startswith("+") else "negative" if delta.strip().startswith("-") else ""
        delta_html = f'<div class="cm-delta {sign_class}">{delta}</div>'
    help_html = f' <span title="{help_text}" style="cursor:help; opacity:0.55;">ⓘ</span>' if help_text else ""
    with column:
        st.markdown(
            f"""
            <div class="custom-metric">
              <div class="cm-label">{label}{help_html}</div>
              <div class="cm-value">{value}</div>
              {delta_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_homepage() -> None:
    # A landing page, not another tab: a visitor sees what this is and why
    # before being dropped into five tabs of live application state. The
    # only state involved is a single flag, flipped by the CTA button, so
    # there's nothing here for the pure-data homepage_view module to own.
    st.markdown(
        "<div style='text-align:center; margin-top:0.5rem;'>"
        "<span class='hero-badge'>MERCHANT TRUST LAYER</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<h1 style='text-align:center; margin:0.7rem 0 0.2rem;'>{APP_NAME}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='text-align:center; font-size:1.15rem; color:#9aa4b2; margin-bottom:1.6rem;'>{TAGLINE}</p>",
        unsafe_allow_html=True,
    )

    _, pitch_col, _ = st.columns([1, 3, 1])
    with pitch_col:
        st.markdown(
            f"<p style='line-height:1.65; color:#c7ccd6;'>{PITCH}</p>",
            unsafe_allow_html=True,
        )

    st.write("")
    st.write("")
    flow_columns = st.columns(len(FLOW_STEPS))
    for column, step in zip(flow_columns, FLOW_STEPS):
        with column:
            st.markdown(
                f"""
                <div class="flow-card">
                  <div style="font-size:1.6rem;">{step['icon']}</div>
                  <div style="font-weight:700; margin-top:0.5rem;">{step['title']}</div>
                  <div style="font-size:0.85rem; color:#9aa4b2; margin-top:0.35rem; line-height:1.5;">{step['detail']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    st.write("")
    st.markdown("<h4 style='text-align:center;'>What it does</h4>", unsafe_allow_html=True)
    st.write("")
    feature_columns = st.columns(len(FEATURES))
    for column, feature in zip(feature_columns, FEATURES):
        with column:
            st.markdown(
                f"""
                <div class="feature-card">
                  <div style="font-weight:700; margin-bottom:0.5rem;">{feature['icon']} {feature['title']}</div>
                  <div style="font-size:0.85rem; color:#9aa4b2; line-height:1.5;">{feature['detail']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    st.write("")
    _, cta_col, _ = st.columns([2, 1, 2])
    with cta_col:
        if st.button(CTA_LABEL, use_container_width=True, type="primary"):
            st.session_state["entered_app"] = True
            st.rerun()


if not st.session_state.get("entered_app", False):
    render_homepage()
    st.stop()

header_left, header_home, header_refresh = st.columns([8, 1, 1])
with header_left:
    st.markdown(f"<h2 style='margin-bottom:0;'>{APP_NAME}</h2>", unsafe_allow_html=True)
with header_home:
    # No use_container_width here on purpose - forcing these two small
    # icon buttons to stretch or shrink to fit a narrow column is exactly
    # what clipped them on a real screen; left at their natural size, the
    # column just needs to be wide enough to hold them, not the other way
    # around. The `key` gives Streamlit's own st-key-<key> class on the
    # wrapping element, which the CSS below uses to turn just these two
    # into proper square icon buttons - Streamlit's default button padding
    # is sized for text, not a single centered glyph, which read as an
    # oddly-placed, cramped icon rather than an actual clipped one.
    if st.button("\U0001F3E0", help="Back to homepage", key="home_button"):
        st.session_state["entered_app"] = False
        st.rerun()
with header_refresh:
    if st.button("\U0001F504", help="Refresh", key="refresh_button"):
        st.rerun()

df = load_audit_log(DB_PATH)

trust_tab, growth_tab, demo_tab, stress_tab, mandates_tab = st.tabs(
    [
        "\U0001F6E1 Trust Panel",
        "\U0001F4C8 Growth Panel",
        "\U000025B6 Live Demo",
        "\U0001F9EA Stress Test",
        "\U0001F5C2 Active Mandates",
    ]
)

with trust_tab:
    st.caption(
        "Every decision the deterministic validator and the upsell engine have "
        "made, read live from the audit log."
    )

    if df.empty:
        st.info(
            "No decisions logged yet. Run the five demo scenarios below to seed the audit "
            "log, or run `python scripts/buyer_agent_simulator.py` from `backend/` yourself."
        )
        if st.button("\U000025B6 Run demo scenarios", key="seed_demo_data_trust"):
            try:
                seed_scenarios = fetch_scenarios(BACKEND_URL)
            except Exception as exc:
                st.error(f"Can't reach the backend at {BACKEND_URL}: {exc}")
            else:
                seed_status = st.empty()
                for index, scenario in enumerate(seed_scenarios):
                    seed_status.caption(f"Running {index + 1}/{len(seed_scenarios)} - {scenario['name']}")
                    try:
                        run_scenario(BACKEND_URL, scenario)
                    except Exception as exc:
                        st.warning(f"`{scenario['name']}` failed: {exc}")
                seed_status.empty()
                st.rerun()
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
            render_metric_card(col1, "Approved orders", str(metrics["total_approved"]))
            render_metric_card(
                col2,
                "Upsell acceptance rate",
                f"{metrics['acceptance_rate']:.0%}",
                help_text=(
                    "An upsell counts as accepted once the engine successfully proposes one "
                    "that passes every guardrail in Step 6 - this build has no separate buyer "
                    "confirmation step, so proposal and acceptance are the same event here."
                ),
            )
            render_metric_card(col3, "AOV (actual)", f"₹{metrics['baseline_aov']:,.2f}")
            render_metric_card(
                col4,
                "AOV (projected w/ upsells)",
                f"₹{metrics['projected_aov']:,.2f}",
                delta=f"{metrics['aov_lift_pct']:+.1f}%",
                help_text=(
                    "Projected: what AOV would be if every proposed upsell had been bought. "
                    "Step 7 never adds a proposed upsell to the actual Razorpay charge, so "
                    "this is a measure of upside the upsell engine is surfacing, not revenue "
                    "already captured."
                ),
            )

            st.plotly_chart(build_aov_comparison_chart(metrics), use_container_width=True)

            st.divider()
            top_col, category_col = st.columns(2)

            with top_col:
                st.subheader("Top proposed upsells")
                st.caption("Which catalog items the upsell engine reaches for most often.")
                top = top_upsells(df)
                if top.empty:
                    st.info("No upsells proposed yet.")
                else:
                    for _, row in top.iterrows():
                        st.write(f"**{row['upsell_sku']}** - proposed {int(row['count'])}×")

            with category_col:
                st.subheader("Revenue by category")
                st.caption("Approved order value, grouped by what was actually purchased.")
                by_category = revenue_by_category(df)
                if by_category.empty:
                    st.info("No approved orders yet.")
                else:
                    st.plotly_chart(build_revenue_by_category_chart(by_category), use_container_width=True)

with demo_tab:
    st.caption(
        "Run any scenario against the live backend and watch what the gate does "
        "with it. Left is what the buyer agent asked for; right is the decision, "
        "step by step."
    )

    try:
        demo_scenarios = fetch_scenarios(BACKEND_URL)
        catalog_products = fetch_catalog(BACKEND_URL)
    except Exception as exc:
        demo_scenarios = []
        catalog_products = []
        st.error(
            f"Can't reach the backend at {BACKEND_URL} - start it with "
            f"`python -m uvicorn app.main:app --reload` from `backend/`, then reload this page.\n\n{exc}"
        )

    if demo_scenarios:
        # One button per scenario, laid out in a row. Clicking stores the
        # result in session state so it survives the reruns Streamlit does
        # on every interaction.
        button_columns = st.columns(len(demo_scenarios))
        for column, scenario in zip(button_columns, demo_scenarios):
            label = scenario["name"].replace("_", " ")
            if column.button(label, key=f"run-{scenario['name']}", use_container_width=True):
                with st.spinner("Running against the live gate..."):
                    try:
                        st.session_state["demo_result"] = {
                            "scenario": scenario,
                            "decision": run_scenario(BACKEND_URL, scenario),
                        }
                    except Exception as exc:
                        st.session_state["demo_result"] = {"scenario": scenario, "error": str(exc)}

        st.divider()
        st.subheader("Build your own mandate")
        st.caption(
            "Not convinced the five scenarios above are just staged to look good? "
            "Set your own budget, categories, and item, and send it through the same "
            "`/decide` pipeline - nothing here is scripted."
        )

        if not catalog_products:
            st.warning("No catalog items available - the catalog fetch above failed.")
        else:
            categories = sorted({product["category"] for product in catalog_products})

            col_left, col_right = st.columns(2)
            with col_left:
                custom_buyer_id = st.text_input("Buyer ID", value="agent-custom-01", key="custom_buyer_id")
                custom_budget = st.number_input(
                    "Budget cap (INR)", min_value=0.01, value=2500.0, step=50.0, key="custom_budget"
                )
                custom_days_valid = st.number_input(
                    "Mandate valid for (days from now)",
                    min_value=-30,
                    max_value=365,
                    value=1,
                    step=1,
                    key="custom_days_valid",
                    help="Use a negative number to hand the gate an already-expired mandate on purpose.",
                )
            with col_right:
                custom_categories = st.multiselect(
                    "Allowed categories", categories, default=categories[:1], key="custom_categories"
                )
                custom_intent = st.text_area(
                    "Stated intent", value="Buy running gear", height=80, key="custom_intent"
                )

            sku_choices = {
                f"{product['sku']} - {product['name']} (INR {product['price']:,.2f}, {product['category']})": product
                for product in catalog_products
            }
            custom_sku_label = st.selectbox("Item to buy", list(sku_choices.keys()), key="custom_sku_label")
            custom_product = sku_choices[custom_sku_label]
            # Keyed on the SKU so switching items resets the amount to that
            # item's real price instead of carrying over a stale one - the
            # field stays editable so a budget violation can still be forced
            # deliberately.
            custom_amount = st.number_input(
                "Transaction amount (INR)",
                min_value=0.01,
                value=float(custom_product["price"]),
                step=10.0,
                key=f"custom_amount_{custom_product['sku']}",
            )

            if st.button("Run this mandate", key="run_custom_mandate", use_container_width=True):
                if not custom_categories:
                    st.error("Pick at least one allowed category.")
                else:
                    custom_scenario = {
                        "mandate": {
                            "buyer_id": custom_buyer_id or "agent-custom-01",
                            "intent": custom_intent or "Custom mandate",
                            "budget_max": custom_budget,
                            "category_allowlist": custom_categories,
                            "expiry": (
                                datetime.now(timezone.utc) + timedelta(days=custom_days_valid)
                            ).isoformat(),
                        },
                        "transaction": {
                            "sku": custom_product["sku"],
                            "category": custom_product["category"],
                            "amount": custom_amount,
                        },
                    }
                    with st.spinner("Running against the live gate..."):
                        try:
                            st.session_state["demo_result"] = {
                                "scenario": custom_scenario,
                                "decision": run_scenario(BACKEND_URL, custom_scenario),
                            }
                        except Exception as exc:
                            st.session_state["demo_result"] = {"scenario": custom_scenario, "error": str(exc)}

        st.divider()
        st.subheader("Or charge an existing mandate")
        st.caption(
            "Every mandate above is one-off: fresh budget, spent in one call, gone. Issue a "
            "mandate on the Active Mandates tab instead, then run several purchases against it "
            "here and watch its real remaining budget shrink - including the purchase that "
            "finally exceeds it, even though no single purchase looked like a violation on its own."
        )

        try:
            active_mandates = [m for m in fetch_mandates(BACKEND_URL) if m["status"] == "active"]
        except Exception:
            active_mandates = []

        if not active_mandates:
            st.info("No active mandates yet - issue one on the Active Mandates tab first.")
        elif not catalog_products:
            st.warning("No catalog items available - the catalog fetch above failed.")
        else:
            mandate_choices = {
                f"{m['mandate_id']} - {m['buyer_id']} - ₹{m['budget_remaining']:,.2f} left "
                f"of ₹{m['budget_max']:,.2f}": m
                for m in active_mandates
            }
            chosen_label = st.selectbox("Mandate", list(mandate_choices.keys()), key="registry_mandate_choice")
            chosen_mandate = mandate_choices[chosen_label]

            eligible_products = [p for p in catalog_products if p["category"] in chosen_mandate["category_allowlist"]]
            if not eligible_products:
                st.warning(
                    f"No catalog items fall inside this mandate's allowed categories "
                    f"({', '.join(chosen_mandate['category_allowlist'])})."
                )
            else:
                registry_sku_choices = {
                    f"{p['sku']} - {p['name']} (INR {p['price']:,.2f}, {p['category']})": p
                    for p in eligible_products
                }
                registry_sku_label = st.selectbox(
                    "Item to buy", list(registry_sku_choices.keys()), key="registry_sku_label"
                )
                registry_product = registry_sku_choices[registry_sku_label]
                registry_amount = st.number_input(
                    "Transaction amount (INR)",
                    min_value=0.01,
                    value=float(registry_product["price"]),
                    step=10.0,
                    key=f"registry_amount_{chosen_mandate['mandate_id']}_{registry_product['sku']}",
                )

                if st.button("Charge this mandate", key="run_registry_mandate", use_container_width=True):
                    registry_payload = {
                        "mandate_id": chosen_mandate["mandate_id"],
                        "transaction": {
                            "sku": registry_product["sku"],
                            "category": registry_product["category"],
                            "amount": registry_amount,
                        },
                    }
                    # The agent-request panel below expects scenario["mandate"]
                    # with the usual fields - reconstruct that shape from the
                    # registry record so the same rendering works whether the
                    # mandate came in inline or by id.
                    display_scenario = {
                        "mandate": {
                            "buyer_id": chosen_mandate["buyer_id"],
                            "intent": chosen_mandate["intent"],
                            "budget_max": chosen_mandate["budget_max"],
                            "category_allowlist": chosen_mandate["category_allowlist"],
                            "expiry": chosen_mandate["expiry"],
                        },
                        "transaction": registry_payload["transaction"],
                    }
                    with st.spinner("Running against the live gate..."):
                        try:
                            decision = run_scenario(BACKEND_URL, registry_payload)
                            st.session_state["demo_result"] = {"scenario": display_scenario, "decision": decision}
                        except Exception as exc:
                            st.session_state["demo_result"] = {"scenario": display_scenario, "error": str(exc)}

        result = st.session_state.get("demo_result")

        if result is None:
            st.info("Pick a scenario above to run it.")
        elif "error" in result:
            st.error(f"Request failed: {result['error']}")
        else:
            scenario = result["scenario"]
            decision = result["decision"]
            mandate = scenario["mandate"]
            transaction = scenario["transaction"]

            agent_column, gate_column = st.columns(2)

            with agent_column:
                st.subheader("Buyer agent asks")
                st.markdown(
                    f"**Agent** `{mandate['buyer_id']}`  \n"
                    f"**Budget cap** ₹{mandate['budget_max']:,.2f}  \n"
                    f"**Allowed categories** {', '.join(mandate['category_allowlist'])}  \n"
                    f"**Wants** `{transaction['sku']}` · ₹{transaction['amount']:,.2f} "
                    f"({transaction['category']})"
                )
                # The injection payload is shown verbatim rather than
                # summarised - the whole point is that a judge can read the
                # hostile instruction and then watch it fail anyway.
                st.markdown("**Stated intent**")
                st.info(mandate["intent"])

            with gate_column:
                st.subheader("Gatekeeper does")
                for step in derive_steps(decision):
                    icon = {OK: "\u2705", BLOCKED: "\u274C"}.get(step["status"], "\u2022")
                    st.markdown(f"{icon} {step['label']}")
                    if step["detail"]:
                        st.caption(step["detail"])

            summary = outcome_summary(decision)
            if summary["status"] == BLOCKED:
                st.error(summary["text"])
            else:
                st.success(summary["text"])

            with st.expander("Raw decision JSON"):
                st.code(json.dumps(decision, indent=2, ensure_ascii=False), language="json")

with stress_tab:
    st.caption(
        "One crafted mandate proves the gate survives that mandate. This runs a large, "
        "structured batch of legitimate and adversarial mandates - built from every item "
        "in the catalog, not five hand-picked examples - against the live gate and grades "
        "every response against what should have happened."
    )

    GROUP_LABELS = {
        "budget": "Budget boundary",
        "category": "Category enforcement",
        "expiry": "Expiry enforcement",
        "multi_violation": "Multiple violations at once",
        "injection_defense": "Prompt-injection defense",
    }

    try:
        stress_cases = fetch_stress_cases(BACKEND_URL)
    except Exception as exc:
        stress_cases = []
        st.error(
            f"Can't reach the backend at {BACKEND_URL} - start it with "
            f"`python -m uvicorn app.main:app --reload` from `backend/`, then reload this page.\n\n{exc}"
        )

    if stress_cases:
        legitimate = sum(1 for c in stress_cases if c["expect"]["approved"])
        adversarial = len(stress_cases) - legitimate
        st.write(
            f"**{len(stress_cases)} cases** ready - {legitimate} legitimate purchases that "
            f"should be approved, {adversarial} edge cases and adversarial attempts that "
            "should be caught. Every logged decision this produces lands in the Trust panel "
            "like any other, since nothing here bypasses the audit log."
        )

        if st.button("\U0001F9EA Run stress test", key="run_stress_test", use_container_width=True):
            progress_placeholder = st.empty()
            status_placeholder = st.empty()
            results = []
            for index, case in enumerate(stress_cases):
                status_placeholder.caption(f"Running {index + 1}/{len(stress_cases)} - `{case['id']}`")
                try:
                    decision = run_scenario(BACKEND_URL, case)
                    outcome = evaluate_case(case, decision)
                    results.append({"case": case, "decision": decision, **outcome})
                except Exception as exc:
                    results.append(
                        {"case": case, "decision": None, "status": FAILED, "reason": f"request failed: {exc}"}
                    )
                progress_placeholder.progress((index + 1) / len(stress_cases))
            progress_placeholder.empty()
            status_placeholder.empty()

            run_summary = summarize(results)
            try:
                submit_stress_run(BACKEND_URL, run_summary, results)
            except Exception as exc:
                # A persistence failure shouldn't hide the run that just
                # finished - it's still shown below, just won't survive a
                # refresh this time.
                st.warning(f"Ran fine, but couldn't save this run for later: {exc}")

            st.session_state["stress_results"] = results
            st.session_state["stress_summary"] = run_summary
            st.session_state["stress_run_note"] = None

    # On first load of this tab in a fresh session (a refresh, a new
    # browser tab, or someone else opening the dashboard), there's nothing
    # in session state yet - reach for the last persisted run instead of
    # showing nothing, which is the exact gap that made a finished run
    # disappear the moment the page reloaded.
    if "stress_results" not in st.session_state:
        try:
            latest_run = fetch_latest_stress_run(BACKEND_URL)
        except Exception:
            latest_run = None

        if latest_run is not None:
            st.session_state["stress_results"] = latest_run["results"]
            st.session_state["stress_summary"] = {
                "total": latest_run["total"],
                "passed": latest_run["passed"],
                "failed": latest_run["failed"],
                "by_group": latest_run["by_group"],
            }
            st.session_state["stress_run_note"] = (
                f"Showing the most recent saved run, from {latest_run['created_at']} - "
                "not from this browser session. Run again above for a fresh result."
            )

    stress_results = st.session_state.get("stress_results")

    if stress_results is None:
        if stress_cases:
            st.info("Run the stress test above to grade the gate against the full batch.")
    else:
        if st.session_state.get("stress_run_note"):
            st.caption(st.session_state["stress_run_note"])

        summary = st.session_state.get("stress_summary") or summarize(stress_results)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total cases", summary["total"])
        col2.metric("Passed", summary["passed"])
        col3.metric(
            "Failed",
            summary["failed"],
            help="A failure means the gate's actual decision didn't match what this case expected - worth reading before trusting the pass count.",
        )

        st.subheader("By category")
        for group, stats in summary["by_group"].items():
            label = GROUP_LABELS.get(group, group)
            st.write(f"**{label}** - {stats['passed']}/{stats['total']} passed")

        failures = [r for r in stress_results if r["status"] == FAILED]
        if failures:
            st.error(
                f"{len(failures)} of {summary['total']} case(s) did not behave as expected - "
                "review these before trusting the rest."
            )
        else:
            st.success(f"All {summary['total']} cases behaved exactly as expected.")

        st.subheader(f"All {len(stress_results)} cases")
        st.caption(
            "Every case the batch ran, not just the failures above - what it expected, what "
            "actually happened, and why. Sort or search any column to dig in."
        )

        def expected_outcome(case: dict) -> str:
            if case["expect"]["approved"]:
                return "approved"
            return f"declined ({case['expect']['violated_rule']})"

        cases_table = pd.DataFrame(
            [
                {
                    "Result": "✅ passed" if r["status"] != FAILED else "❌ failed",
                    "Case ID": r["case"]["id"],
                    "Group": GROUP_LABELS.get(r["case"]["group"], r["case"]["group"]),
                    "Expected": expected_outcome(r["case"]),
                    "Reason": r["reason"],
                }
                for r in stress_results
            ]
        )
        st.dataframe(cases_table, use_container_width=True, hide_index=True)

        st.subheader("Inspect a case")
        case_lookup = {r["case"]["id"]: r for r in stress_results}
        inspect_id = st.selectbox(
            "Case",
            list(case_lookup.keys()),
            format_func=lambda case_id: (
                f"{'✅' if case_lookup[case_id]['status'] != FAILED else '❌'} {case_id}"
            ),
            key="inspect_stress_case",
        )
        inspected = case_lookup[inspect_id]
        st.write(f"**{inspected['case']['kind']}**")
        st.write(f"**Result:** {inspected['reason']}")
        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            st.write("**Mandate:**")
            st.json(inspected["case"]["mandate"])
            st.write("**Transaction:**")
            st.json(inspected["case"]["transaction"])
        with detail_col2:
            st.write("**Expected:**")
            st.json(inspected["case"]["expect"])
            if inspected["decision"] is not None:
                st.write("**Decision received:**")
                st.json(inspected["decision"])

with mandates_tab:
    st.caption(
        "Every mandate everywhere else in this dashboard is inline: presented fresh with "
        "every purchase, spent, and forgotten. A mandate issued here gets a real id and a "
        "persisted budget that purchases charged against it draw down cumulatively - closing "
        "the gap a fresh-mandate-per-call design can't: an agent staying under a per-purchase "
        "cap across several small purchases while blowing right past the mandate's real total."
    )

    st.subheader("Issue a new mandate")

    try:
        mandate_catalog = fetch_catalog(BACKEND_URL)
        mandate_categories = sorted({product["category"] for product in mandate_catalog})
    except Exception as exc:
        mandate_catalog = []
        mandate_categories = []
        st.error(
            f"Can't reach the backend at {BACKEND_URL} - start it with "
            f"`python -m uvicorn app.main:app --reload` from `backend/`, then reload this page.\n\n{exc}"
        )

    if mandate_categories:
        issue_col_left, issue_col_right = st.columns(2)
        with issue_col_left:
            issue_buyer_id = st.text_input("Buyer ID", value="agent-mandate-01", key="issue_buyer_id")
            issue_budget = st.number_input(
                "Total budget (INR)", min_value=0.01, value=3000.0, step=50.0, key="issue_budget"
            )
            issue_days = st.number_input(
                "Valid for (days)", min_value=1, max_value=365, value=7, step=1, key="issue_days"
            )
        with issue_col_right:
            issue_categories = st.multiselect(
                "Allowed categories", mandate_categories, default=mandate_categories[:1], key="issue_categories"
            )
            issue_intent = st.text_area(
                "Intent", value="Ongoing running-gear purchases", height=80, key="issue_intent"
            )

        if st.button("Issue mandate", key="issue_mandate_btn", use_container_width=True):
            if not issue_categories:
                st.error("Pick at least one allowed category.")
            else:
                issue_payload = {
                    "buyer_id": issue_buyer_id or "agent-mandate-01",
                    "intent": issue_intent or "Ongoing purchases",
                    "budget_max": issue_budget,
                    "category_allowlist": issue_categories,
                    "expiry": (datetime.now(timezone.utc) + timedelta(days=issue_days)).isoformat(),
                }
                try:
                    issued = issue_mandate(BACKEND_URL, issue_payload)
                    st.success(
                        f"Issued `{issued['mandate_id']}` - ₹{issued['budget_remaining']:,.2f} available. "
                        "Charge purchases against it from the Live Demo tab's "
                        "\"Or charge an existing mandate\" section."
                    )
                except Exception as exc:
                    st.error(f"Couldn't issue mandate: {exc}")

    st.divider()
    st.subheader("All mandates")

    try:
        all_mandates = fetch_mandates(BACKEND_URL)
    except Exception:
        all_mandates = []

    if not all_mandates:
        st.info("No mandates issued yet - use the form above to issue the first one.")
    else:
        status_counts = summarize_mandates(all_mandates)
        count_col1, count_col2, count_col3 = st.columns(3)
        count_col1.metric(f"{status_icon('active')} Active", status_counts["active"])
        count_col2.metric(f"{status_icon('exhausted')} Exhausted", status_counts["exhausted"])
        count_col3.metric(f"{status_icon('expired')} Expired", status_counts["expired"])

        mandates_df = pd.DataFrame(all_mandates)
        mandates_df["Status"] = mandates_df["status"].map(lambda s: f"{status_icon(s)} {s}")
        mandates_df["Categories"] = mandates_df["category_allowlist"].map(", ".join)
        for money_col in ("budget_max", "budget_spent", "budget_remaining"):
            mandates_df[money_col] = mandates_df[money_col].map(lambda v: f"₹{v:,.2f}")

        display_mandates = mandates_df[
            ["mandate_id", "Status", "buyer_id", "budget_max", "budget_spent", "budget_remaining", "Categories", "expiry"]
        ].rename(
            columns={
                "mandate_id": "Mandate ID",
                "buyer_id": "Buyer",
                "budget_max": "Budget",
                "budget_spent": "Spent",
                "budget_remaining": "Remaining",
                "expiry": "Expires",
            }
        )
        st.dataframe(display_mandates, use_container_width=True, hide_index=True)
