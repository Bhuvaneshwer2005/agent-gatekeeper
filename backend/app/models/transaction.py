# Data contract for a transaction proposed on behalf of a buyer agent.
#
# Kept deliberately small: just enough to identify what's being bought and
# check it against a mandate. Fields no current step needs (e.g. a full
# line-item breakdown) don't belong here yet - they get added when a step
# actually needs them.

from pydantic import BaseModel, Field


class ProposedTransaction(BaseModel):
    """A specific purchase a buyer agent wants to make under its mandate."""

    sku: str = Field(
        ...,
        min_length=1,
        description="Catalog SKU identifying what's being purchased.",
    )
    category: str = Field(
        ...,
        min_length=1,
        description="Product category the SKU belongs to, checked against the mandate's category_allowlist.",
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Total cost of the transaction, in the same currency unit as the mandate's budget_max.",
    )
