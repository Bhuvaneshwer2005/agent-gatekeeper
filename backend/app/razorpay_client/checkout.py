# Wires an approved decision to a real Razorpay test-mode order.
#
# This is the only module that talks to Razorpay, and - like the LLM
# boundary in app/upsell - it treats "approved" as something it must verify
# itself, not something it trusts a caller to have already checked. A
# declined decision raises before a Razorpay client is even constructed,
# let alone before any network call is made.

import os
import time
from typing import Optional

import razorpay
from dotenv import load_dotenv

from app.models.decision import Decision
from app.models.mandate import Mandate
from app.models.transaction import ProposedTransaction

# Loaded once at import time, same reasoning as app/upsell/llm_client.py:
# whatever entry point reaches this module (the app, a script, a test) may
# not have loaded .env itself.
load_dotenv()

_client: Optional[razorpay.Client] = None


class DeclinedDecisionError(Exception):
    """Raised when create_order is called with anything but an approved decision.

    A plain `assert` statement can be compiled away entirely when Python
    runs with -O, which is not a risk worth taking on the one check that
    keeps a declined mandate from ever reaching a real payment call - so
    this is a normal, always-active exception instead.
    """


def _get_client() -> razorpay.Client:
    global _client
    if _client is None:
        key_id = os.environ.get("RAZORPAY_KEY_ID")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RuntimeError(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set. Copy "
                ".env.example to .env and add your Razorpay test-mode keys."
            )
        _client = razorpay.Client(auth=(key_id, key_secret))
    return _client


def create_order(
    decision: Decision, mandate: Mandate, transaction: ProposedTransaction
) -> dict:
    """Create a Razorpay test-mode order for an already-approved transaction.

    Only ever reaches Razorpay for a decision whose validation approved -
    anything else raises DeclinedDecisionError immediately. The order
    covers the base transaction amount only; a proposed upsell is a
    suggestion the LLM made, not a confirmed additional charge, so it is
    recorded in the order's notes for traceability but never silently
    folded into the amount.

    payment_capture=1 tells Razorpay to auto-capture any payment made
    against this order. There's no browser-based checkout in this
    agent-driven flow to produce a payment_id for a separate manual
    capture call, so auto-capture is what actually fulfills the "order +
    payment capture" requirement here rather than a second API call.
    """
    if not decision.validation.approved:
        raise DeclinedDecisionError(
            "Refusing to create a Razorpay order for a declined decision "
            f"(violated_rule={decision.validation.violated_rule})."
        )

    client = _get_client()
    amount_in_paise = int(round(transaction.amount * 100))
    # Razorpay caps receipt at 40 characters.
    receipt = f"ag-{transaction.sku}-{int(time.time())}"[:40]

    order_data = {
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,
        "notes": {
            "buyer_id": mandate.buyer_id,
            "sku": transaction.sku,
            "upsell_sku": decision.upsell.upsell_sku if decision.upsell else "",
        },
    }
    return client.order.create(order_data)
