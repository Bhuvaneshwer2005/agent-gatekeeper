# Entry point for the Agent Gatekeeper backend.
# Routes and wiring get added as each module (mandate validator, catalog,
# upsell engine, audit log, panels) is built.

from typing import List

from fastapi import FastAPI

from app.catalog.catalog_service import get_catalog
from app.models.decision_request import DecisionRequest
from app.models.product import Product

app = FastAPI(title="Agent Gatekeeper")


@app.get("/health")
def health_check():
    # Simple liveness check so the scaffold has something to run and verify.
    return {"status": "ok"}


@app.get("/catalog", response_model=List[Product])
def catalog():
    """Serve the merchant's product catalog for a buyer agent to shop from.

    This is the same catalog data the upsell engine will later be
    restricted to - a buyer agent (or its simulator) and the upsell engine
    both see exactly one source of truth for product info.
    """
    return get_catalog()


@app.post("/decide")
def decide(request: DecisionRequest):
    """Stub for the decision endpoint.

    Accepts a mandate plus a proposed transaction and only acknowledges
    receipt - it does not inspect budget, category, or expiry, and it does
    not call the validator. The real decision engine, which runs the
    deterministic validator first and only reaches an LLM after that check
    passes, is built in the next step. This stub exists so the buyer agent
    simulator has a real endpoint to send scenarios to in the meantime.
    """
    return {
        "received": True,
        "buyer_id": request.mandate.buyer_id,
        "sku": request.transaction.sku,
        "message": "Decision engine not implemented yet - this is a stub.",
    }
