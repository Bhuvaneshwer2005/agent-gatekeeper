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

Repo scaffold only. No functional modules are wired up yet.

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
