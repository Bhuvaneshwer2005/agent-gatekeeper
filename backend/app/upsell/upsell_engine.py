# Upsell proposal engine.
#
# This is the only module in the project that calls an LLM, and it is only
# ever reached for a mandate that has already passed the deterministic
# validator (Step 3) - the decision engine enforces that ordering, not this
# file. Even so, everything here treats the LLM as untrusted: every numeric
# and category constraint is enforced in Python before the model ever sees
# a choice, and every response is schema-validated and re-checked before it
# can reach the audit log or a Razorpay call.

import json
import re
from typing import List, Tuple

from pydantic import ValidationError

from app.models.mandate import Mandate
from app.models.product import Product
from app.models.transaction import ProposedTransaction
from app.models.upsell_proposal import UpsellProposal
from app.upsell.llm_client import complete_json

# One retry beyond the first attempt. Enough to recover from an occasional
# malformed or ungrounded response without turning a demo into a long wait
# on a model that keeps failing the same check.
MAX_ATTEMPTS = 2

SYSTEM_PROMPT = (
    "You are a downstream upsell-proposal assistant for a merchant checkout "
    "system. A separate deterministic system has already approved the "
    "buyer's mandate and the requested purchase - your only job is to look "
    "at a short list of pre-approved candidate products and decide whether "
    "exactly one of them is worth suggesting alongside the purchase, based "
    "on what the buyer said they want.\n\n"
    "Rules:\n"
    "- You may propose at most one product from the candidate list, or none.\n"
    "- Proposing none is a good, correct answer when nothing in the list "
    "genuinely fits - do not force a suggestion just to seem helpful.\n"
    "- Never propose a product that is not in the candidate list.\n"
    "- Write exactly one sentence of plain-language justification that "
    "refers to what the buyer actually said they want: their stated "
    "intent, their allowed categories, or their budget.\n"
    '- Respond with a JSON object with exactly two keys: "upsell_sku" '
    '(a string from the candidate list, or null) and "justification" '
    "(a one-sentence string)."
)


def _select_candidates(
    mandate: Mandate, transaction: ProposedTransaction, catalog: List[Product]
) -> List[Product]:
    """Narrow the catalog to products the LLM is even allowed to see.

    This is where budget and category are actually enforced - by the time
    the LLM sees a candidate, it is already guaranteed to be affordable
    within the mandate's remaining budget and inside an allowed category.
    The LLM's only real decision is which one (if any) fits the buyer's
    stated intent; it never gets a chance to get a numeric or category
    check wrong, because it never makes one.
    """
    headroom = mandate.budget_max - transaction.amount
    return [
        product
        for product in catalog
        if product.upsell_eligible
        and product.sku != transaction.sku
        and product.category in mandate.category_allowlist
        and product.price <= headroom
    ]


def _references_mandate_field(justification: str, mandate: Mandate) -> bool:
    """Lightweight, deterministic check that a justification is grounded in
    something the buyer actually provided, not generic filler text.

    This is a substring/keyword check, not semantic understanding - its job
    is to catch obviously ungrounded output (a justification that could
    apply to any purchase), not to grade prose quality. A justification
    that mentions the buyer's stated intent, one of their allowed
    categories, or their budget figure passes.
    """
    text = justification.lower()
    intent_keywords = re.findall(r"[a-zA-Z]{4,}", mandate.intent)
    if any(keyword.lower() in text for keyword in intent_keywords):
        return True
    if any(category.lower() in text for category in mandate.category_allowlist):
        return True
    if str(int(mandate.budget_max)) in text:
        return True
    return False


def _build_user_prompt(
    mandate: Mandate, transaction: ProposedTransaction, candidates: List[Product]
) -> str:
    payload = {
        "buyer_intent": mandate.intent,
        "allowed_categories": mandate.category_allowlist,
        "budget_max": mandate.budget_max,
        "purchase_already_approved": {
            "sku": transaction.sku,
            "category": transaction.category,
            "amount": transaction.amount,
        },
        "candidate_upsells": [
            {
                "sku": product.sku,
                "name": product.name,
                "price": product.price,
                "category": product.category,
            }
            for product in candidates
        ],
    }
    return "Respond with JSON only. Here is the situation:\n" + json.dumps(
        payload, indent=2
    )


def propose_upsell(
    mandate: Mandate, transaction: ProposedTransaction, catalog: List[Product]
) -> Tuple[UpsellProposal, List[str]]:
    """Propose at most one upsell for an already-approved purchase.

    Returns the validated proposal alongside every raw LLM response that
    was attempted, so a rejected or hallucinated attempt stays visible in
    the audit trail even though it never becomes the final answer.

    Callers must only invoke this after `validate_mandate` has approved the
    transaction - this function trusts that has already happened and does
    not re-check budget/category/expiry itself.
    """
    candidates = _select_candidates(mandate, transaction, catalog)
    if not candidates:
        # Nothing safe to offer - skip the LLM call entirely rather than
        # asking it to choose from an empty list.
        return (
            UpsellProposal(
                upsell_sku=None,
                justification="No catalog item fits the remaining budget and allowed categories.",
            ),
            [],
        )

    user_prompt = _build_user_prompt(mandate, transaction, candidates)
    candidate_skus = {product.sku for product in candidates}
    raw_responses: List[str] = []

    for _ in range(MAX_ATTEMPTS):
        raw = complete_json(SYSTEM_PROMPT, user_prompt)
        raw_responses.append(raw)

        try:
            parsed = json.loads(raw)
            proposal = UpsellProposal(**parsed)
        except (json.JSONDecodeError, ValidationError, TypeError):
            continue  # malformed - retry

        if proposal.upsell_sku is not None and proposal.upsell_sku not in candidate_skus:
            continue  # hallucinated a SKU outside the candidate list - retry

        if proposal.upsell_sku is not None and not _references_mandate_field(
            proposal.justification, mandate
        ):
            continue  # ungrounded justification - retry

        return proposal, raw_responses

    # Exhausted retries without a trustworthy response - fail safe to "no
    # upsell" rather than ever passing an unverified proposal downstream.
    return (
        UpsellProposal(
            upsell_sku=None,
            justification="No upsell proposed - the model's output could not be verified.",
        ),
        raw_responses,
    )
