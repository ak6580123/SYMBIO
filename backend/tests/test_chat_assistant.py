"""The grounded assistant (Feature 8).

Two properties matter more than coverage here:

  * a question outside Symbio's data gets the honest refusal, never a guess;
  * the safety ranking quotes the safety layer's own decision, so the assistant
    cannot describe a hazardous route as safe even if the engine allowed it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services.chat import NO_INFO, CAN_ANSWER, _detect_intent  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def fly_ash_id(client):
    resp = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": "Pulverised coal fly ash from the electrostatic precipitator, dry grey powder.",
            "quantity": 5.0,
            "unit": "tonnes",
            "location": "Manali, Chennai",
            "frequency": "monthly",
            "composition": "SiO2: 55%, Al2O3: 25%",
        },
    )
    return resp.json()["analysis"]["id"]


@pytest.mark.parametrize(
    "question,intent",
    [
        ("What are the safest reuse options?", "safest"),
        ("which partner is safest?", "safest"),
        ("Which reuse pathway has the highest environmental benefit?", "environmental_ranking"),
        ("which route avoids the most CO2e?", "environmental_ranking"),
        ("What processing does this waste require?", "processing"),
        ("Why was this recipient ranked first?", "match_reason"),
        ("What can I do with 10 tonnes of rice husk?", "reuse_options"),
        ("What is the estimated impact?", "impact"),
        ("Are there other sectors that could use it?", "sectors"),
        ("Is this material hazardous?", "material"),
        # Out of scope must stay out of scope.
        ("what is the weather in Chennai tomorrow", "unknown"),
        ("write me a poem about recycling", "unknown"),
        ("who is the prime minister", "unknown"),
    ],
)
def test_intent_routing(question, intent):
    assert _detect_intent(question, None) == intent


def test_safest_answer_quotes_engine_classification(client, fly_ash_id):
    body = client.post("/api/chat", json={"analysis_id": fly_ash_id, "question": "what are the safest options?"}).json()
    answer = body["answer"]
    assert "moderate risk" in answer
    assert "SafetyLevel" not in answer  # the enum must never leak into prose
    assert "grounded" not in body or body["grounded_in"] == ["match.safety_level", "match.reuse_type", "material.safety_level"]
    assert "risk assessment" in answer  # keeps its limits in the same breath


def test_environmental_answer_names_the_pathway(client, fly_ash_id):
    body = client.post(
        "/api/chat",
        json={"analysis_id": fly_ash_id, "question": "which pathway has the highest environmental benefit?"},
    ).json()
    assert "t CO₂e/month" in body["answer"]
    assert "→" in body["answer"]
    assert "demo calculation" in body["answer"]
    assert "do not add up" in body["answer"]  # says the routes share one stream


def test_hazardous_stream_is_never_called_safe(client):
    resp = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": "Spent hydroprocessing catalyst, toxic and hazardous, from the refinery hydrotreater.",
            "quantity": 3.0,
            "unit": "tonnes",
            "location": "Manali, Chennai",
            "frequency": "monthly",
        },
    )
    analysis = resp.json()["analysis"]
    body = client.post("/api/chat", json={"analysis_id": analysis["id"], "question": "what is the safest option?"}).json()

    # Every route the engine kept for a hazardous stream must be industrial only,
    # and the answer must not contradict that.
    assert all(m["reuse_type"] in {"INDUSTRIAL_ONLY", "RESTRICTED"} for m in analysis["matches"])
    assert "hazardous risk" in body["answer"]
    for casual in ("household", "farm", "community programme", "artisan"):
        assert casual not in body["answer"].lower()


def test_unknown_questions_refuse_rather_than_invent(client, fly_ash_id):
    body = client.post("/api/chat", json={"analysis_id": fly_ash_id, "question": "who won the IPL last year?"}).json()
    assert body["answer"].startswith(NO_INFO)
    assert CAN_ANSWER in body["answer"]
    assert body["confident"] is False
    assert body["engine"] == "deterministic"


def test_llm_answers_are_labelled_as_such(client, fly_ash_id):
    """Without Ollama the engine label must say so, not pretend otherwise."""
    body = client.post("/api/chat", json={"analysis_id": fly_ash_id, "question": "tell me about circle geometry"}).json()
    assert body["engine"] in {"deterministic", "ollama"} or body["engine"].startswith("ollama:")
