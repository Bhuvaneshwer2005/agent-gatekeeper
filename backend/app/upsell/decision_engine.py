# Orchestrates a full decision: run the deterministic validator first,
# always, and only reach the LLM upsell engine if that validator approves.
#
# This ordering is the one hard rule the whole project depends on. It is
# enforced here in code - not by convention, not by trusting callers - so
# there is no path from an incoming transaction to an LLM call that skips
# validation.

from app.catalog.catalog_service import get_catalog
from app.models.decision import Decision
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.upsell.upsell_engine import propose_upsell
from app.validator.mandate_validator import validate_mandate


def make_decision(mandate: Mandate, transaction: ProposedTransaction) -> Decision:
    """Validate a transaction against its mandate, then decide on an upsell.

    A declined mandate returns immediately with no upsell and an empty
    llm_raw_responses list - there is nothing to upsell on a purchase that
    was never allowed to happen, and the LLM is never invoked to find out.
    """
    validation = validate_mandate(mandate, transaction)

    if not validation.approved:
        return Decision(validation=validation, upsell=None, llm_raw_responses=[])

    catalog = get_catalog()
    upsell, raw_responses = propose_upsell(mandate, transaction, catalog)
    return Decision(validation=validation, upsell=upsell, llm_raw_responses=raw_responses)
