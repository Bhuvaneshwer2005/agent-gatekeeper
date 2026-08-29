# Request body for the decision endpoint.
#
# Bundles a mandate with the specific transaction proposed against it. This
# is the shape the buyer agent simulator sends, and the shape the real
# decision engine (built in the next step) will act on - for now the
# endpoint that accepts this is only a stub.

from pydantic import BaseModel

from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction


class DecisionRequest(BaseModel):
    mandate: Mandate
    transaction: ProposedTransaction
