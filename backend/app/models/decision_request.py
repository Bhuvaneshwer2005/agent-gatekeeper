# Request body for the decision endpoint.
#
# Bundles a mandate with the specific transaction proposed against it. This
# is the shape the buyer agent simulator sends, and the shape the decision
# engine acts on.
#
# A request carries the mandate one of two ways: inline (mandate), the
# original shape every demo scenario, the custom mandate builder, and the
# whole stress-test batch still use - a fresh, one-off mandate presented and
# spent in the same call. Or by mandate_id, referencing a mandate already
# issued through POST /mandates, whose budget is checked and drawn down
# cumulatively across however many calls reference it. Exactly one of the
# two must be present; mixing them (or providing neither) doesn't parse.

from typing import Optional

from pydantic import BaseModel, model_validator

from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction


class DecisionRequest(BaseModel):
    mandate: Optional[Mandate] = None
    mandate_id: Optional[str] = None
    transaction: ProposedTransaction

    @model_validator(mode="after")
    def exactly_one_mandate_source(self) -> "DecisionRequest":
        if (self.mandate is None) == (self.mandate_id is None):
            raise ValueError("Provide exactly one of 'mandate' or 'mandate_id', not both or neither.")
        return self
