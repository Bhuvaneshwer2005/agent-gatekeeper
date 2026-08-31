# Frontend

`dashboard.py` is a single Streamlit app with two tabs, both reading the
backend's audit log (`backend/data/audit_log.db`) directly - no separate
data path for either one.

## Trust panel

Renders the audit log as a live table. Every decision is one of three
statuses - Approved, Upsold, or Refused - each with its own icon and row
color so refused decisions are never just another line of text in the
table. Selecting a row shows the full validation/upsell detail, including
the LLM's raw response(s) even when one was rejected by the schema or
second-pass check.

`audit_view.py` holds the data-reading and classification logic on its
own, separate from the Streamlit rendering code, so it's unit testable
with plain pytest instead of a Streamlit test harness.

## Growth panel

Computes upsell acceptance rate and AOV (average order value) lift from
the same approved decisions, plus a bar chart comparing actual vs.
projected AOV.

Neither metric has a real "did the buyer actually pay for the upsell"
signal to draw on - Step 7 deliberately never folds a proposed upsell into
the Razorpay charge, and no step asks the buyer agent whether it accepts
one. Both metrics are computed on an honest, clearly-labeled basis instead
(see the "?" tooltips on each metric in the app):

- **Acceptance rate**: the share of approved decisions where the upsell
  engine successfully proposed a valid upsell - the system's actual final
  output, since no separate buyer-confirmation step exists yet.
- **AOV lift**: actual AOV (what was really charged) vs. projected AOV
  (what it would be if every proposed upsell had been bought) - a measure
  of upside the upsell engine is surfacing, not revenue already captured.

`growth_view.py` holds this logic on its own, same pattern as
`audit_view.py`.

## Setup

```bash
cd frontend
pip install -r requirements.txt
streamlit run dashboard.py
```

The backend doesn't need to be running for the dashboard itself to start -
it just shows an empty state on both tabs until at least one request has
gone through `/decide`.

## Tests

```bash
cd frontend
pytest
```
