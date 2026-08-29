# Strict schema for the LLM's upsell proposal.
#
# This is the exact shape the LLM is constrained to produce. Nothing about
# budget, category, or expiry appears here on purpose - the LLM's only
# decision is which catalog item (if any) to suggest and why, never whether
# it's allowed.

from typing import Optional

from pydantic import BaseModel, Field


class UpsellProposal(BaseModel):
    """The LLM's proposed upsell, already validated against this schema."""

    upsell_sku: Optional[str] = Field(
        default=None,
        description="SKU of the proposed upsell, or null if none fits.",
    )
    justification: str = Field(
        ...,
        min_length=1,
        description="One-sentence, plain-language explanation grounded in the buyer's mandate.",
    )
