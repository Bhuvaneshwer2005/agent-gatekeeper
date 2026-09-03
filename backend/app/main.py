# Entry point for the Agent Gatekeeper backend.
# Routes and wiring get added as each module (mandate validator, catalog,
# upsell engine, audit log, panels) is built.

from typing import List

from fastapi import FastAPI

from app.audit.audit_log import log_decision
from app.catalog.catalog_service import get_catalog
from app.models.decision import Decision
from app.models.decision_request import DecisionRequest
from app.models.product import Product
from app.razorpay_client.checkout import create_order
from app.scenarios.demo_scenarios import build_scenarios
from app.scenarios.stress_cases import build_stress_cases
from app.upsell.decision_engine import make_decision

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


@app.get("/scenarios")
def scenarios():
    """Serve the demo scenarios, built fresh from the current catalog.

    Exists so the dashboard's Live demo tab can offer the same scenarios
    the terminal simulator runs, without duplicating their definitions on
    the frontend - which matters more once the two are deployed separately
    and can't share a filesystem.
    """
    return build_scenarios([product.model_dump() for product in get_catalog()])


@app.get("/stress-cases")
def stress_cases():
    """Serve the stress-test batch: many structured mandate/transaction pairs,
    built fresh from the current catalog, each carrying its own expected
    outcome for the dashboard's Stress Test tab to grade against.
    """
    return build_stress_cases([product.model_dump() for product in get_catalog()])


@app.post("/decide", response_model=Decision)
def decide(request: DecisionRequest):
    """Run a transaction through the full decision pipeline.

    Always validates against the mandate's rules first (Step 3); only
    reaches the LLM upsell engine (Step 6) if that validation approves. An
    approved decision then attempts a Razorpay test-mode order (Step 7) -
    a declined one never does, since create_order refuses it outright.
    Whatever happens - approved, declined, or a Razorpay failure - exactly
    one row goes to the audit log (Step 8) before the response is sent.
    """
    decision = make_decision(request.mandate, request.transaction)

    razorpay_status = "skipped"
    razorpay_order_id = None
    razorpay_detail = None

    if decision.validation.approved:
        try:
            order = create_order(decision, request.mandate, request.transaction)
            razorpay_status = "created"
            razorpay_order_id = order.get("id")
        except Exception as exc:
            # Deliberately broad: whatever goes wrong talking to Razorpay
            # (missing credentials, a bad request, a network error) must
            # still produce a logged outcome and a normal response, not a
            # crashed request - the audit trail exists precisely to make
            # failures like this visible rather than silent.
            razorpay_status = "failed"
            razorpay_detail = str(exc)

    log_decision(
        mandate=request.mandate,
        transaction=request.transaction,
        decision=decision,
        razorpay_status=razorpay_status,
        razorpay_order_id=razorpay_order_id,
        razorpay_detail=razorpay_detail,
    )

    return decision
