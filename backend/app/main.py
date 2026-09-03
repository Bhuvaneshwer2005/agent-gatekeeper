# Entry point for the Agent Gatekeeper backend.
# Routes and wiring get added as each module (mandate validator, catalog,
# upsell engine, audit log, panels) is built.

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.audit.audit_log import log_decision
from app.audit.stress_run_log import get_latest_stress_run, log_stress_run
from app.catalog.catalog_service import get_catalog
from app.models.decision import Decision
from app.models.decision_request import DecisionRequest
from app.models.mandate import Mandate
from app.models.product import Product
from app.models.transaction import ProposedTransaction
from app.models.validation_result import ValidationRule
from app.razorpay_client.checkout import create_order
from app.registry.mandate_registry import get_mandate, issue_mandate, list_mandates, record_spend
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


class StressRunSubmission(BaseModel):
    """What the dashboard sends after grading a stress-test batch client-side.

    Grading itself stays in stress_test_view.py - this is just the record of
    what it concluded, kept loosely typed (plain dicts) since its only job
    is to persist and hand back exactly what was graded, not re-validate
    grading logic that already ran.
    """

    summary: Dict[str, Any]
    results: List[Dict[str, Any]]


@app.post("/stress-runs")
def create_stress_run(submission: StressRunSubmission):
    """Persist a graded stress-test run so it survives a page refresh.

    Streamlit's session state - where a run's results live the moment the
    batch finishes - is wiped by a reload or a lost connection. This is the
    only thing in the stress-test feature that needed real persistence; the
    cases themselves are regenerated fresh from the catalog every time.
    """
    log_stress_run(submission.summary, submission.results)
    return {"status": "recorded"}


@app.get("/stress-runs/latest")
def stress_runs_latest():
    """Return the most recently logged stress-test run, or null if none yet."""
    return get_latest_stress_run()


@app.post("/mandates")
def create_mandate(mandate: Mandate):
    """Issue a new mandate and persist it.

    A mandate issued here can be charged against by mandate_id on any
    number of later /decide calls, with its budget drawn down cumulatively
    across all of them - unlike an inline mandate (still what every demo
    scenario, the custom mandate builder's default, and the stress-test
    batch use), which gets a fresh, unlinked budget on every single call.
    """
    return issue_mandate(mandate)


@app.get("/mandates")
def mandates():
    """List every mandate ever issued through POST /mandates, each with its
    live status (active/exhausted/expired) and remaining budget computed
    against the current time.
    """
    return list_mandates()


@app.post("/decide", response_model=Decision)
def decide(request: DecisionRequest):
    """Run a transaction through the full decision pipeline.

    A request carries its mandate one of two ways (DecisionRequest enforces
    exactly one): inline, the original one-off shape, or by mandate_id,
    referencing a mandate already issued through POST /mandates. For the
    mandate_id path, the check is cumulative - what's being validated isn't
    just this transaction in isolation, but this mandate's total spend so
    far plus this transaction, against its real budget. A transaction that
    would individually fit can still be the one that pushes total spend
    past what the mandate actually authorized.

    Whichever path it came in on, everything downstream is identical:
    validate first (Step 3), reach the LLM upsell engine only on approval
    (Step 6), attempt a Razorpay test-mode order only on approval (Step 7),
    and write exactly one audit row either way (Step 8) - using the real,
    per-transaction amount, never the cumulative figure used for the check.
    """
    registry_mandate = None

    if request.mandate_id is not None:
        registry_mandate = get_mandate(request.mandate_id)
        if registry_mandate is None:
            raise HTTPException(status_code=404, detail=f"No mandate found with id '{request.mandate_id}'.")

        effective_mandate = Mandate(
            buyer_id=registry_mandate["buyer_id"],
            intent=registry_mandate["intent"],
            budget_max=registry_mandate["budget_max"],
            category_allowlist=registry_mandate["category_allowlist"],
            expiry=registry_mandate["expiry"],
        )
        # Checked against cumulative spend, not this purchase alone - the
        # real budget_max is unchanged, but the "amount" being weighed
        # against it is everything already spent on this mandate plus this
        # transaction. The upsell engine's candidate pre-filter benefits
        # from this too: it computes headroom the same way validate_mandate
        # does, so it correctly sees only what's left after this purchase,
        # not what would be left if this were the mandate's only purchase.
        cumulative_check_transaction = ProposedTransaction(
            sku=request.transaction.sku,
            category=request.transaction.category,
            amount=registry_mandate["budget_spent"] + request.transaction.amount,
        )
        decision = make_decision(effective_mandate, cumulative_check_transaction)

        if not decision.validation.approved and decision.validation.violated_rule == ValidationRule.BUDGET_EXCEEDED:
            # validate_mandate's generic message talks about "the
            # transaction amount" - correct, but confusing here since that
            # amount is the cumulative check total, not what the buyer
            # actually asked to spend just now. Worth a clearer message
            # since this exact string is what ends up on screen in the
            # Active Mandates tab.
            clearer_detail = (
                f"This purchase of ₹{request.transaction.amount:,.2f} would bring total spend on "
                f"mandate {request.mandate_id} to ₹{registry_mandate['budget_spent'] + request.transaction.amount:,.2f}, "
                f"exceeding its ₹{registry_mandate['budget_max']:,.2f} budget "
                f"(₹{registry_mandate['budget_remaining']:,.2f} remained before this attempt)."
            )
            decision = decision.model_copy(
                update={"validation": decision.validation.model_copy(update={"detail": clearer_detail})}
            )

        log_mandate = effective_mandate
    else:
        decision = make_decision(request.mandate, request.transaction)
        log_mandate = request.mandate

    razorpay_status = "skipped"
    razorpay_order_id = None
    razorpay_detail = None

    if decision.validation.approved:
        try:
            order = create_order(decision, log_mandate, request.transaction)
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

        if request.mandate_id is not None:
            # Drawn down by the real transaction amount, not the cumulative
            # check total used above - budget_spent should only ever hold
            # what was actually spent, never a running total of a running
            # total.
            record_spend(request.mandate_id, request.transaction.amount)

    log_decision(
        mandate=log_mandate,
        transaction=request.transaction,
        decision=decision,
        razorpay_status=razorpay_status,
        razorpay_order_id=razorpay_order_id,
        razorpay_detail=razorpay_detail,
    )

    return decision
