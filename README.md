# Agent Gatekeeper

**A merchant-side trust layer for agentic commerce.** Built for Track 01
(AI Growth & Agentic Commerce) of the Razorpay hackathon.

## The problem

AI buyer agents are starting to shop on people's behalf — given a budget,
a category, and an expiry, and told to go make a purchase. That's a real
opportunity for merchants, and a real liability: an agent is only as
trustworthy as whatever is enforcing its limits. If that enforcement is
"ask the LLM nicely," a well-crafted prompt is all it takes to blow past a
budget, buy from an unauthorized category, or get talked into an upsell
that was never supposed to happen.

Agent Gatekeeper sits between an incoming buyer agent and a merchant's
Razorpay checkout and answers one question deterministically, every time:
**is this specific purchase actually allowed?** An LLM is involved — but
only downstream of that answer, and only for a task with a hard ceiling:
propose at most one upsell from the real catalog, or none at all.

## What it does

1. **Validates the buyer agent's spending mandate** against hard-coded
   rules — budget, category, expiry. This check is pure Python. It is
   never delegated to model judgment, and it cannot be talked out of a
   decision by anything written in the mandate's free-text fields.
2. **Proposes at most one bounded upsell**, with a plain-language
   justification, but only after the mandate has already passed the
   deterministic check — and only from a candidate list the system itself
   pre-filtered for budget and category, so the model is never in a
   position to get the numbers wrong.
3. **Logs every decision** — approved, upsold, or refused — to an audit
   trail as a single structured row, and surfaces two live dashboards: a
   **Trust panel** (every decision, refusals visually distinct, raw LLM
   output visible even when rejected) and a **Growth panel** (upsell
   acceptance rate, AOV lift).

## Architecture

```text
Buyer Agent
  |  POST /decide  (mandate + transaction)
  v
FastAPI /decide
  |
  v
Deterministic Validator
  expiry -> category -> budget
  |
  +-- declined ---------------------------------+
  |   no LLM call, no Razorpay call              |
  |                                              |
  +-- approved                                   |
       |                                         |
       v                                         |
      Upsell Engine (LLM)                        |
      candidate pre-filter -> propose -> verify   |
       |                                         |
       v                                         |
      Razorpay test-mode order (auto-capture)    |
       |                                         |
       v                                         v
      --------------- SQLite audit log ----------------
                  one row per decision
                          |
              +-----------+-----------+
              v                       v
        Trust panel              Growth panel
        (Streamlit)               (Streamlit)
```

The one architectural decision everything else follows from: **a declined
mandate has no path to the LLM or to Razorpay.** Not "the LLM is trained
not to," not "the prompt says don't" — there is no code path connecting
them. It's tested directly: one test makes the Razorpay client raise if
it's even constructed for a declined decision, and confirms it never is.

### LLM guardrails

The upsell engine is the only place in the codebase that calls an LLM
(Groq, `openai/gpt-oss-20b`, temperature 0), and it's built to treat the
model as untrusted at every step:

- Candidates are filtered deterministically — eligible, right category,
  price within remaining budget — **before** the model ever sees them. It
  can only pick from what's already been vetted, or say none.
- Output is constrained to a strict schema (`{upsell_sku, justification}`)
  and re-validated: the SKU must be one of the pre-filtered candidates,
  and the justification must reference something the buyer actually
  provided (their intent, an allowed category, or their budget figure).
- Malformed output, a hallucinated SKU, an ungrounded justification, or
  the API call itself failing are all retried once, then fail safe to "no
  upsell" — never passed through unverified.
- The raw response is logged alongside the validated result, so a
  rejected attempt is visible evidence in the audit trail, not just a
  claim that a guardrail exists.

## Project layout

```
backend/
  app/
    main.py               FastAPI app: /health, /catalog, /decide
    models/                 Mandate, Product, ProposedTransaction, ValidationResult, Decision, ...
    validator/               Deterministic mandate validator (budget/category/expiry)
    upsell/                   LLM client, upsell engine, decision engine
    audit/                    SQLite audit log
    catalog/                  Merchant product catalog
    razorpay_client/          Razorpay test-mode order creation
  data/
    catalog.json               Product catalog — source of truth for the upsell engine
    audit_log.db                Generated at runtime, gitignored
  scripts/
    buyer_agent_simulator.py  Queries the catalog, runs 5 demo scenarios against /decide
  tests/                       48 tests
frontend/
  dashboard.py                Streamlit app: Trust panel + Growth panel (tabs)
  audit_view.py                 Trust panel data layer
  growth_view.py                Growth panel data layer
  tests/                       12 tests
```

## Setup

Use a virtual environment for each of `backend/` and `frontend/` — both
have their own `requirements.txt`, and installing globally means `pip`
won't upgrade a package you already happen to have installed from an
unrelated project, even if this repo needs a newer version.

**Backend:**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # Windows cmd.exe: copy ..\.env.example .env
# add a free GROQ_API_KEY from console.groq.com to the .env you just created
python -m uvicorn app.main:app --reload
```

`python -m uvicorn` rather than bare `uvicorn` — pip installs the
`uvicorn` command into Python's `Scripts` folder, which isn't always on
`PATH` (especially on a fresh Windows setup). Running it as a module
sidesteps that entirely.

Razorpay test-mode keys (`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`) are
optional — without them, an approved decision still works end to end, it
just logs a `razorpay_status: "failed"` with a clear reason instead of
creating a real test-mode order.

**Frontend (dashboard):**

```bash
cd frontend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run dashboard.py
```

**Try it end to end:**

```bash
cd backend
python scripts/buyer_agent_simulator.py
```

This queries `/catalog` and runs five scenarios against `/decide`:

| Scenario | What it proves |
|---|---|
| `clean_purchase` | Straightforward approve, no upsell headroom |
| `upsell_eligible_purchase` | Approve + a real, grounded LLM upsell proposal |
| `mandate_violation` | Clean refusal on `budget_exceeded` — Razorpay and the LLM are never touched |
| `adversarial_upsell_attempt` | An out-of-category item can't sneak through framed as an upsell, even with enough combined budget |
| `social_engineering_attempt` | A live prompt-injection payload aimed at the upsell LLM — blocked by the deterministic candidate filter, not by the model's good behavior |

## Testing

```bash
cd backend && pytest    # 48 tests
cd frontend && pytest   # 12 tests
```

Every LLM and Razorpay call in the test suite is mocked — the tests run
offline, deterministically, with no API keys required. Live behavior
against the real Groq and Razorpay APIs is verified separately, by
actually running the app (see below).

## What broke, and how it got fixed

Genuine issues hit while building this, not a hypothetical list:

- **The planned Groq model didn't exist.** `llama-3.3-70b-versatile` was
  the original choice — gone from Groq's catalog by the time the LLM
  integration was live-tested, discovered via a 404 on the first real
  call. Fixed by querying Groq's own `/models` endpoint for what was
  actually available and switching to `openai/gpt-oss-20b`.
- **A `NULL` column silently flipped a status label.** `NULL` values come
  back from SQLite through pandas as `NaN`, not `None` — and `NaN` is
  truthy in Python. A plain `if upsell_sku:` check in the dashboard's
  status classifier mislabeled every plain-approved decision as "Upsold."
  Only visible by looking at the actual rendered table, not by running
  the test suite. Fixed with an explicit `pd.notna()` check everywhere a
  nullable column is tested for presence, plus a regression test that
  round-trips through real SQLite instead of a hand-built DataFrame.
- **Refusal rows were unreadable in dark mode.** Row background colors
  were set without an explicit text color, so the dashboard's dark-theme
  default light-gray text nearly disappeared against the light status
  colors. Fixed by forcing an explicit dark text color alongside every
  background color, confirmed legible in both themes.
- **The demo script crashed on its own output.** Printing an
  LLM-generated justification containing a smart hyphen character to a
  Windows console (cp1252 codepage) raised an unhandled
  `UnicodeEncodeError`. Fixed by serializing with `ensure_ascii=True`
  before printing.
- **A refusal message was technically correct and practically unreadable.**
  The budget-exceeded message reported raw floats
  ("`amount 2499.0 exceeds budget of 1999.0`"). Reformatted as currency,
  since that exact string is what ends up on screen in the dashboard.
- **An LLM correctly refusing a prompt injection crashed the API.** While
  testing the upsell engine against a real adversarial prompt in the
  buyer's stated intent, the model did the right thing and declined to
  comply — but Groq's strict JSON mode rejects a plain-prose refusal with
  an HTTP 400 instead of returning it as text. The upsell engine only
  handled malformed *JSON content*, not the API call itself raising, so
  this took down `/decide` with a 500. Fixed by wrapping the LLM call in
  its own retry-eligible error handling: an API-level failure is now
  treated exactly like malformed output, retried, and falls back safely
  to "no upsell" if it keeps happening — with the failure preserved in
  the audit trail either way.
- **A key-presence check echoed the key.** Verifying that an API key was
  set in `.env` with a shell command that inspected file contents
  accidentally printed part of the raw key to the terminal. `.env` is
  gitignored, so it was never at risk of being committed, but the key was
  rotated as a precaution. Since then, secret presence is checked with
  boolean match commands only (`grep -q`), never anything that could echo
  matched content.
- **The setup instructions didn't actually work on a fresh Windows
  machine.** Found by someone following this exact README on a clean
  download, not by the person who wrote it. Bare `uvicorn app.main:app`
  and `streamlit run dashboard.py`, as originally documented, both raise
  `'X' is not recognized as an internal or external command` on a stock
  `cmd.exe` — `pip install` puts those commands in Python's `Scripts`
  folder, which isn't reliably on `PATH`. Fixed by documenting
  `python -m uvicorn` / `python -m streamlit run` instead, which resolve
  the installed package directly regardless of `PATH`. Also caught in the
  same pass: the `.env` copy step pointed at the project root while every
  other instruction (and every test throughout the build) assumed
  `backend/.env` — fixed to copy directly into `backend/`.
- **The Trust panel crashed with `'str' object cannot be interpreted as
  an integer`** on a machine that already had an older Streamlit
  installed globally from an unrelated project. `requirements.txt`
  listed `streamlit` with no version pin, and without a virtual
  environment, `pip install` doesn't upgrade a package that's already
  present — so `st.dataframe(..., width="stretch")`, valid only on newer
  Streamlit releases, got a version where `width` still meant
  pixels-only. Fixed by reverting to the older, more broadly-supported
  `use_container_width=True`, adding a `streamlit>=1.30` floor as a
  backstop, and adding virtual-environment creation to the setup steps
  above so a stale global install can't shadow this project's
  dependencies again.
