# Landing-page copy for the dashboard's homepage, kept as plain data (no
# Streamlit calls) so it's testable the same way as audit_view/growth_view -
# dashboard.py is the only place that actually renders it.

APP_NAME = "Agent Gatekeeper"
TAGLINE = "A merchant-side trust layer for agentic commerce."

PITCH = (
    "AI buyer agents are starting to shop on people's behalf - given a budget, a "
    "category, and an expiry, then told to go make a purchase. Agent Gatekeeper "
    "sits between an incoming buyer agent and a merchant's Razorpay checkout and "
    "answers one question the same way every time, by rule rather than by asking "
    "a model nicely: is this specific purchase actually allowed?"
)

FLOW_STEPS = [
    {
        "icon": "\U0001F916",
        "title": "Buyer agent",
        "detail": "Presents a mandate - budget, allowed categories, expiry - and asks to buy something.",
    },
    {
        "icon": "\U0001F6E1",
        "title": "Agent Gatekeeper",
        "detail": "Validates the mandate deterministically, then lets an LLM propose at most one bounded upsell.",
    },
    {
        "icon": "\U0001F4B3",
        "title": "Razorpay checkout",
        "detail": "Only an approved purchase ever reaches a real order - every step logged to the audit trail.",
    },
]

FEATURES = [
    {
        "icon": "⚖️",
        "title": "Deterministic, not model judgment",
        "detail": (
            "Budget, category, and expiry are enforced by plain Python rules. Nothing written into a "
            "mandate's free-text fields can talk the gate out of a decision."
        ),
    },
    {
        "icon": "\U0001F3F7️",
        "title": "Bounded, explainable upsells",
        "detail": (
            "An LLM may propose at most one upsell, chosen only from candidates the system already "
            "pre-filtered for budget and category - never the numbers, only the pitch."
        ),
    },
    {
        "icon": "\U0001F4CA",
        "title": "Every decision, on the record",
        "detail": (
            "Approved, upsold, or refused - each decision is logged and shown live in the Trust and "
            "Growth panels, not summarized after the fact."
        ),
    },
]

CTA_LABEL = "Enter Dashboard →"
