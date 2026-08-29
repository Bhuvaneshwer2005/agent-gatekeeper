# Agent Gatekeeper

A merchant-side trust layer that sits between an incoming AI buyer agent and
a merchant's Razorpay test-mode checkout.

It does three things:

1. **Validates the buyer agent's spending mandate** against hard-coded rules —
   budget, category, and expiry. This check is fully deterministic; it is
   never delegated to model judgment.
2. **Proposes at most one bounded upsell**, with a plain-language
   justification, but only after the mandate has already passed the
   deterministic check.
3. **Logs every decision** — approved, upsold, or refused — to an audit
   trail, and surfaces a Trust panel (bounded, gated, explainable, with
   refusal handling) and a Growth panel (AOV lift from upsells).

## Status

Mandate schema, deterministic validator, catalog endpoint, and a buyer
agent simulator are in place. The decision endpoint (`/decide`) is still a
stub — it acknowledges requests but doesn't call the validator yet.

## Project layout

```
backend/
  app/
    main.py            FastAPI app entry point
    models/             Shared schemas
    validator/          Deterministic mandate validator (budget/category/expiry)
    upsell/              Bounded upsell proposal + justification
    audit/               Decision logging / audit trail
    catalog/             Merchant product catalog
    razorpay_client/     Razorpay test-mode checkout integration
  data/
    catalog.json         Product catalog used as the upsell source of truth
  scripts/
    buyer_agent_simulator.py   Queries the catalog and sends demo scenarios to /decide
  tests/
frontend/                Trust panel + Growth panel UI
```

## Setup

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in real values
uvicorn app.main:app --reload
```

## Running the buyer agent simulator

With the backend running, in a separate terminal:

```bash
cd backend
python scripts/buyer_agent_simulator.py
```

This queries `/catalog`, builds four demo scenarios (clean purchase,
upsell-eligible purchase, mandate violation, adversarial upsell attempt),
and posts each one to `/decide`.
