# Entry point for the Agent Gatekeeper backend.
# Routes and wiring get added as each module (mandate validator, catalog,
# upsell engine, audit log, panels) is built.

from typing import List

from fastapi import FastAPI

from app.catalog.catalog_service import get_catalog
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
