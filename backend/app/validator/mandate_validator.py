# Deterministic mandate validator.
#
# This is the hard boundary the rest of the system depends on: given a
# mandate and a transaction proposed against it, this module decides
# approve/decline using fixed rules only. No LLM call happens anywhere in
# this file, now or ever - if a rule needs to change, it changes here, in
# code that runs the same way on every input, not in a prompt.

from datetime import datetime, timezone

from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction
from app.models.validation_result import ValidationResult, ValidationRule


def validate_mandate(
    mandate: Mandate, transaction: ProposedTransaction
) -> ValidationResult:
    """Check a proposed transaction against a mandate's rules.

    Checks run in a fixed order - expiry, then category, then budget - so
    that a transaction failing more than one rule always reports the same
    reason for the same inputs, rather than depending on incidental
    ordering. Expiry is checked first because an expired mandate has no
    meaningful budget or category to check against.
    """
    now = datetime.now(timezone.utc)

    if mandate.expiry <= now:
        return ValidationResult(
            approved=False,
            violated_rule=ValidationRule.MANDATE_EXPIRED,
            detail=(
                f"Mandate expired at {mandate.expiry.isoformat()}; "
                f"current time is {now.isoformat()}."
            ),
        )

    # Exact, case-sensitive match against the allowlist - the mandate and
    # the catalog are expected to agree on category spelling. Normalizing
    # or fuzzy-matching categories is a business decision for later, not
    # something this boundary should decide silently.
    if transaction.category not in mandate.category_allowlist:
        return ValidationResult(
            approved=False,
            violated_rule=ValidationRule.CATEGORY_NOT_ALLOWED,
            detail=(
                f"Category '{transaction.category}' is not in the mandate's "
                f"allowed categories: {mandate.category_allowlist}."
            ),
        )

    if transaction.amount > mandate.budget_max:
        return ValidationResult(
            approved=False,
            violated_rule=ValidationRule.BUDGET_EXCEEDED,
            detail=(
                f"Transaction amount {transaction.amount} exceeds mandate "
                f"budget of {mandate.budget_max}."
            ),
        )

    return ValidationResult(
        approved=True,
        violated_rule=None,
        detail="Transaction is within budget, category, and expiry limits.",
    )
