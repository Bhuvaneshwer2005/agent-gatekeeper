# Result of running a proposed transaction through the mandate validator.
#
# Kept separate from the validator itself so downstream modules (the audit
# log, the decision engine) can depend on the result shape without pulling
# in the validation logic.

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ValidationRule(str, Enum):
    """Rules the validator checks. Values double as the audit-log reason code."""

    MANDATE_EXPIRED = "mandate_expired"
    CATEGORY_NOT_ALLOWED = "category_not_allowed"
    BUDGET_EXCEEDED = "budget_exceeded"


class ValidationResult(BaseModel):
    """Outcome of validating one transaction against one mandate."""

    approved: bool
    violated_rule: Optional[ValidationRule] = Field(
        default=None,
        description="Which rule caused a decline. Always None when approved.",
    )
    detail: str = Field(
        ...,
        description="Human-readable explanation of the decision, for logs and audit trail.",
    )
