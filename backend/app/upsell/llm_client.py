# Thin wrapper around the Groq chat completions API.
#
# Isolated in its own file so the rest of the upsell engine doesn't need to
# know which provider is behind it - swapping providers later only touches
# this file, not the prompt logic or the second-pass checks in
# upsell_engine.py.

import os

from dotenv import load_dotenv
from groq import Groq

# Loaded once at import time so GROQ_API_KEY is available whether this
# module is reached through the FastAPI app, the buyer agent simulator, or
# a test run - none of which are guaranteed to have loaded .env themselves.
load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-20b"

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add a "
                "free key from https://console.groq.com."
            )
        _client = Groq(api_key=api_key)
    return _client


def complete_json(system_prompt: str, user_prompt: str) -> str:
    """Send a chat completion request constrained to JSON output.

    Temperature is fixed at 0 - the project's rule that upsell proposals
    must be deterministic and repeatable applies to every LLM call, not
    just this one, so there is no parameter to override it.
    """
    client = _get_client()
    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content
