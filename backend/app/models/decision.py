# Combined result of running the mandate validator and, if it approves, the
# upsell engine on a proposed transaction. This is what /decide returns,
# and what Step 7 (Razorpay) and Step 8 (audit log) will both consume.

from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.upsell_proposal import UpsellProposal
from app.models.validation_result import ValidationResult


class Decision(BaseModel):
    validation: ValidationResult
    upsell: Optional[UpsellProposal] = Field(
        default=None,
        description=(
            "Set only when the mandate was approved and a candidate genuinely "
            "fit. None means either the mandate was declined or no upsell fit."
        ),
    )
    llm_raw_responses: List[str] = Field(
        default_factory=list,
        description=(
            "Every raw response the LLM returned while proposing an upsell, "
            "including any rejected by the schema or second-pass check - kept "
            "so a hallucination caught by validation stays visible evidence in "
            "the audit trail, not just a claim. Empty when the mandate was "
            "declined (the LLM is never called) or when no candidates existed."
        ),
    )
