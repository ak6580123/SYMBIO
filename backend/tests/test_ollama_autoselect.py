"""Symbio should work the moment Ollama is running, with no configuration.

`qwen2.5:3b` is the model this project is tuned for, but it is the *preferred*
tag, not a hard requirement: a machine that has Ollama installed with some other
chat model pulled should get a working LLM, not a silent fallback. These tests
pin that behaviour, and the two things that must stay true while it does:

  * the engine label tells the truth about which model answered;
  * an unusable setup produces advice that matches the actual problem, and
    OLLAMA_MODEL still pins the choice exactly for anyone who wants that.

Everything here patches `httpx.get` / `httpx.post` on the identification module
rather than binding a port, so the tests are fast and leave nothing running.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import pytest  # noqa: E402

from ai import identification  # noqa: E402

ANSWER = {
    "material": "Fly Ash",
    "confidence": 0.9,
    "category": "coal_combustion_residue",
    "properties": ["pozzolanic"],
    "composition": {"SiO2": "55%"},
    "alternatives": [],
    "reuse_categories": ["cement_supplementary_material"],
    "safety_level": "moderate",
    "requires_processing": True,
    "reasoning": "Siliceous combustion residue.",
}


class _Resp:
    """Just enough of an httpx.Response for the module's use."""

    def __init__(self, payload, status: int = 200, url: str = "http://ollama/api"):
        self._payload = payload
        self.status_code = status
        self.url = url

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise self._error()

    def _error(self) -> httpx.HTTPStatusError:
        req = httpx.Request("POST", self.url)
        return httpx.HTTPStatusError(
            f"{self.status_code}", request=req, response=httpx.Response(self.status_code, request=req)
        )


@pytest.fixture
def ollama(monkeypatch):
    """Stand in for the Ollama HTTP API and record what we were asked to run."""

    def install(models, *, chat_status: int = 200, chat_payload=None):
        asked: list[str] = []

        def _get(url, **_kwargs):
            assert url.endswith("/api/tags")
            return _Resp({"models": [{"name": name} for name in models]})

        def _post(url, json=None, **_kwargs):  # noqa: A002 - mirrors httpx's kwarg
            assert url.endswith("/api/chat")
            asked.append(json["model"])
            if chat_status != 200:
                raise _Resp({}, status=chat_status)._error()
            content = chat_payload if chat_payload is not None else json_content(ANSWER)
            return _Resp({"message": {"content": content}})

        monkeypatch.setattr(identification.httpx, "get", _get)
        monkeypatch.setattr(identification.httpx, "post", _post)
        monkeypatch.setattr(identification, "OLLAMA_MODEL_PINNED", False)
        monkeypatch.setattr(identification, "OLLAMA_MODEL", "qwen2.5:3b")
        return asked

    return install


def json_content(payload: dict) -> str:
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Which model gets chosen
# ---------------------------------------------------------------------------


def test_recommended_model_wins_when_present(ollama):
    assert identification.select_model(["qwen2.5:3b", "llama3.2:latest"]) == "qwen2.5:3b"


def test_any_pulled_chat_model_is_used_otherwise(ollama):
    """No qwen on the machine must not mean no LLM."""
    assert identification.select_model(["llama3.2:latest", "nomic-embed-text"]) == "llama3.2:latest"


def test_same_family_counts_as_present(ollama):
    assert identification.select_model(["qwen2.5:7b"]) == "qwen2.5:7b"


def test_models_it_cannot_drive_are_not_grabbed(ollama):
    """An embedding model would answer nonsense; better the honest fallback."""
    assert identification.select_model(["nomic-embed-text"]) is None
    assert identification.select_model([]) is None


def test_pinned_choice_is_never_silently_substituted(ollama, monkeypatch):
    monkeypatch.setattr(identification, "OLLAMA_MODEL_PINNED", True)
    monkeypatch.setattr(identification, "OLLAMA_MODEL", "qwen2.5:3b")
    assert identification.select_model(["llama3.2:latest"]) is None
    assert identification.select_model(["qwen2.5:3b"]) == "qwen2.5:3b"


# ---------------------------------------------------------------------------
# What identify() does with that choice
# ---------------------------------------------------------------------------


def test_identification_uses_an_auto_selected_model(ollama):
    asked = ollama(["llama3.2:latest"])
    warnings: list[str] = []
    ident = identification.identify("fly ash from a boiler", None, None, warnings)

    assert asked == ["llama3.2:latest"]  # inference really ran on it
    assert ident.engine == "ollama:llama3.2:latest"
    assert ident.material == "Fly Ash"
    assert warnings == []  # a working Ollama is not a warning condition


def test_no_usable_model_falls_back_without_lying(ollama):
    """Ollama IS running here, so 'start it with ollama serve' would be wrong."""
    ollama(["nomic-embed-text"])
    warnings: list[str] = []
    ident = identification.identify("fly ash from a boiler", "SiO2: 55%", None, warnings)

    assert ident.engine == "fallback_keyword"
    assert len(warnings) == 1
    text = warnings[0]
    assert "ollama pull qwen2.5:3b" in text
    assert "ollama serve" not in text


def test_empty_model_list_says_what_is_installed(ollama):
    ollama([])
    warnings: list[str] = []
    identification.identify("fly ash", None, None, warnings)
    assert "no models installed" in warnings[0]

    ollama(["nomic-embed-text"])
    warnings = []
    identification.identify("fly ash", None, None, warnings)
    assert "nomic-embed-text" in warnings[0]  # names what it found, not just the failure


def test_missing_model_reported_by_chat_endpoint(ollama):
    """A 404 means the tag is absent - advise a pull, not a restart."""
    ollama(["qwen2.5:3b"], chat_status=404)
    warnings: list[str] = []
    ident = identification.identify("fly ash", "SiO2: 55%", None, warnings)
    assert ident.engine == "fallback_keyword"
    assert "ollama pull qwen2.5:3b" in warnings[0]
    assert "not reachable" not in warnings[0]  # it is reachable - the tag is missing


# ---------------------------------------------------------------------------
# What the badge is allowed to claim
# ---------------------------------------------------------------------------


def test_health_distinguishes_running_from_usable(ollama):
    ollama(["llama3.2:latest"])
    status = identification.ollama_status()
    assert status["available"] and status["usable"]
    assert status["model"] == "llama3.2:latest"
    assert status["auto_selected"] is True
    assert status["requested_model"] == "qwen2.5:3b"
    assert status["model_present"] is False  # usable, but not the tuned model

    ollama(["qwen2.5:3b"])
    status = identification.ollama_status()
    assert status["model_present"] is True
    assert status["auto_selected"] is False

    ollama([])
    status = identification.ollama_status()
    assert status["available"] is True  # the server answered...
    assert status["usable"] is False  # ...but there is nothing to run


def test_active_model_never_raises(ollama):
    ollama(["mistral:7b"])
    assert identification.active_model() == "mistral:7b"


def test_chat_sends_the_resolved_model(ollama):
    """The assistant must not quietly ask for a model the user does not have."""
    from services import chat

    asked = ollama(["llama3.1:8b"])
    analysis = {
        "material": {
            "name": "Fly Ash",
            "category": "coal_combustion_residue",
            "compatible_sectors": ["cement_manufacturing"],
        },
        "identification": {"confidence": 0.9},
        "source": {"quantity_t_per_month": 5.0, "location": "Manali, Chennai"},
        "matches": [],
        "totals": {"allocated_t_per_month": 5.0, "available_t_per_month": 5.0},
    }
    result = chat._llm_answer(analysis, "what else could use this?")
    assert result is not None
    text, model = result
    assert asked == ["llama3.1:8b"]
    assert model == "llama3.1:8b"
    assert text == json.dumps(ANSWER)  # whatever the model said is passed through


def test_chat_stays_deterministic_when_nothing_is_usable(ollama, monkeypatch):
    from services import chat

    ollama([])
    assert chat._llm_answer({"material": {}}, "anything") is None
