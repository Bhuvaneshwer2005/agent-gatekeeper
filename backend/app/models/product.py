# Data contract for a single item in the merchant's product catalog.
#
# This is the only source of truth for product info that later steps (the
# buyer agent simulator, the upsell engine) are allowed to use - the upsell
# engine in particular must never rely on general knowledge about typical
# prices or products, only on entries that actually appear here.

from pydantic import BaseModel, Field


class Product(BaseModel):
    """A single catalog entry a buyer agent can purchase or be upsold."""

    sku: str = Field(
        ...,
        min_length=1,
        description="Unique catalog identifier for this product.",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Human-readable product name.",
    )
    price: float = Field(
        ...,
        gt=0,
        description=(
            "Price in the merchant's base currency unit (e.g. rupees), matching "
            "the units used by Mandate.budget_max and ProposedTransaction.amount."
        ),
    )
    category: str = Field(
        ...,
        min_length=1,
        description="Product category, matched against a mandate's category_allowlist.",
    )
    stock: int = Field(
        ...,
        ge=0,
        description="Units currently available.",
    )
    upsell_eligible: bool = Field(
        ...,
        description="Whether this product may be proposed as an upsell alongside another purchase.",
    )
