# Frontend

## Trust panel

`dashboard.py` is a Streamlit app that reads the backend's audit log
(`backend/data/audit_log.db`) directly and renders it as a live table.
Every decision is one of three statuses - Approved, Upsold, or Refused -
each with its own icon and row color so refused decisions are never just
another line of text in the table.

`audit_view.py` holds the data-reading and classification logic on its
own, separate from the Streamlit rendering code, so it can be unit tested
with plain pytest instead of a Streamlit test harness.

### Setup

```bash
cd frontend
pip install -r requirements.txt
streamlit run dashboard.py
```

The backend doesn't need to be running for the dashboard itself to start -
it just shows an empty state until at least one request has gone through
`/decide`.

### Tests

```bash
cd frontend
pytest
```

## Growth panel

Not built yet - will sit alongside the Trust panel in this same app, not
replace it.
