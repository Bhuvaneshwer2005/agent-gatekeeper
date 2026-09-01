# Tests for the Groq model selection logic in llm_client.py.
#
# Regression coverage for a real bug found via manual testing on a fresh
# install: .env.example ships with GROQ_MODEL= (present but empty), and
# python-dotenv sets that as an empty string rather than leaving the
# variable unset - so a plain os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
# doesn't fall back the way it looks like it should, since .get()'s default
# only applies when the key is missing, not when it's blank. The result was
# an empty string sent to Groq as a literal model name, which Groq
# rejected with a 404.

from app.upsell import llm_client


class FakeCompletions:
    def __init__(self):
        self.last_model = None

    def create(self, **kwargs):
        self.last_model = kwargs["model"]

        class FakeMessage:
            content = "{}"

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        return FakeResponse()


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeGroqClient:
    def __init__(self):
        self.chat = FakeChat()


def test_uses_default_model_when_groq_model_is_unset(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    fake_client = FakeGroqClient()
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    llm_client.complete_json("system", "user")

    assert fake_client.chat.completions.last_model == llm_client.DEFAULT_MODEL


def test_uses_default_model_when_groq_model_is_an_empty_string(monkeypatch):
    # This is the actual bug: .env.example's GROQ_MODEL= produces this, not
    # a missing variable.
    monkeypatch.setenv("GROQ_MODEL", "")
    fake_client = FakeGroqClient()
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    llm_client.complete_json("system", "user")

    assert fake_client.chat.completions.last_model == llm_client.DEFAULT_MODEL


def test_uses_the_override_when_groq_model_is_actually_set(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "some/other-model")
    fake_client = FakeGroqClient()
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    llm_client.complete_json("system", "user")

    assert fake_client.chat.completions.last_model == "some/other-model"
