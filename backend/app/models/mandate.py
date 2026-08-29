# Data contract for a buyer agent's spending mandate.
#
# This module only defines the shape of a mandate. It does not contain any
# business rules - whether a mandate is currently valid, whether a category
# is one the merchant actually sells, whether the budget is reasonable - all
# of that belongs to the validator (app/validator), which will consume this
# schema in the next step. Keeping the two separate means the schema stays
# stable even as the business rules around it change.

from typing import List

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class Mandate(BaseModel):
    """A buyer agent's spending mandate, as declared by the agent itself.

    Every field here is validated structurally only: required-ness, type,
    and basic shape (non-empty strings/lists, positive amounts). Whether the
    mandate is actually acceptable - budget within range, category
    permitted, not expired - is decided by the validator, not here.
    """

    buyer_id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier for the buyer agent presenting this mandate.",
    )
    intent: str = Field(
        ...,
        min_length=1,
        description="Plain-language description of what the buyer agent intends to purchase.",
    )
    budget_max: float = Field(
        ...,
        gt=0,
        description=(
            "Upper bound the buyer agent is authorized to spend, expressed in the "
            "merchant's base currency unit (e.g. rupees), not paise. Conversion to "
            "Razorpay's paise-based amounts happens at the checkout integration "
            "boundary, not here."
        ),
    )
    category_allowlist: List[str] = Field(
        ...,
        min_length=1,
        description="Product categories the buyer agent is authorized to purchase from.",
    )
    # AwareDatetime rejects naive datetimes outright, so a mandate can never
    # carry an expiry with an ambiguous timezone - important because the
    # validator will later compare this directly against the current time.
    expiry: AwareDatetime = Field(
        ...,
        description="Timestamp after which this mandate is no longer valid.",
    )

    @field_validator("category_allowlist")
    @classmethod
    def categories_not_blank(cls, value: List[str]) -> List[str]:
        # A list that is non-empty but full of blank strings still passes
        # min_length - this catches that shape defect without judging
        # whether the categories named are ones the merchant recognizes.
        if any(not category.strip() for category in value):
            raise ValueError("category_allowlist entries must not be blank")
        return value
