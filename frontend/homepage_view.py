# Landing-page copy for the dashboard's homepage, kept as plain data (no
# Streamlit calls) so it's testable the same way as audit_view/growth_view -
# dashboard.py is the only place that actually renders it.
#
# Icons are referenced by name (icons.py), not embedded as emoji - the
# homepage is one of the few surfaces that renders its own HTML directly,
# so it's one of the few places a genuinely custom vector icon can go at
# all (Streamlit's own widgets only accept an emoji or a Material Symbols
# shortcode for their icon slots, not arbitrary SVG).

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
        "icon": "robot",
        "title": "Buyer agent",
        "detail": "Presents a mandate - budget, allowed categories, expiry - and asks to buy something.",
    },
    {
        "icon": "shield",
        "title": "Agent Gatekeeper",
        "detail": "Validates the mandate deterministically, then lets an LLM propose at most one bounded upsell.",
    },
    {
        "icon": "credit-card",
        "title": "Razorpay checkout",
        "detail": "Only an approved purchase ever reaches a real order - every step logged to the audit trail.",
    },
]

FEATURES = [
    {
        "icon": "scale",
        "title": "Deterministic, not model judgment",
        "detail": (
            "Budget, category, and expiry are enforced by plain Python rules. Nothing written into a "
            "mandate's free-text fields can talk the gate out of a decision."
        ),
    },
    {
        "icon": "tag",
        "title": "Bounded, explainable upsells",
        "detail": (
            "An LLM may propose at most one upsell, chosen only from candidates the system already "
            "pre-filtered for budget and category - never the numbers, only the pitch."
        ),
    },
    {
        "icon": "clipboard",
        "title": "Every decision, on the record",
        "detail": (
            "Approved, upsold, or refused - each decision is logged and shown live in the Trust and "
            "Growth panels, not summarized after the fact."
        ),
    },
]

# One card per dashboard tab, in the same order they appear once inside -
# the homepage's "What it does" section above sells the core trust-layer
# concept, this section is the actual product tour, so a visitor knows
# what all five tabs are for before clicking in.
PLATFORM_FEATURES = [
    {
        "icon": "shield",
        "title": "Trust Panel",
        "detail": "Every decision the gate has made, read live from the audit log - refusals visually distinct, raw LLM output visible even when rejected.",
    },
    {
        "icon": "trending-up",
        "title": "Growth Panel",
        "detail": "Upsell acceptance rate, AOV lift, top proposed upsells, and revenue by category - all computed from the same decisions the Trust panel shows.",
    },
    {
        "icon": "play",
        "title": "Live Demo",
        "detail": "Run any of five scenarios, a mandate you build by hand, or a purchase against an issued mandate - and watch the gate's decision step by step.",
    },
    {
        "icon": "flask",
        "title": "Stress Test",
        "detail": "Fires 74 structured legitimate-and-adversarial cases - built from every catalog item - at the live gate and grades the result.",
    },
    {
        "icon": "folder",
        "title": "Active Mandates",
        "detail": "Issue a mandate once and charge several purchases against it - its budget draws down cumulatively, closing the gap a fresh mandate per call can't.",
    },
]

CTA_LABEL = "Enter Dashboard"
