"""Evidence tags and the material intelligence card (Features 3 and 7).

The rule these tests hold the product to: every number a user is shown carries
the origin it really came from. A demo calculation must be labelled a demo
calculation, and the intelligence card must be the knowledge-base record - not a
summary written by a model.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from conftest import FLY_ASH_REQUEST  # noqa: E402

from services import explain  # noqa: E402

CARDBOARD_REQUEST = {
    "source_type": "household",
    "material_description": "Household cardboard boxes, flattened and kept dry, one pickup a week.",
    "quantity": 0.9,
    "unit": "tonnes",
    "location": "Anna Nagar, Chennai",
    "frequency": "monthly",
}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def fly_ash(client):
    return client.post("/api/analyze", json=FLY_ASH_REQUEST).json()["analysis"]


@pytest.fixture(scope="module")
def match_detail(client, fly_ash):
    top = fly_ash["matches"][0]
    resp = client.get(f"/api/matches/{fly_ash['id']}/{top['recipient']['id']}")
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Feature 3 - provenance
# ---------------------------------------------------------------------------


def test_every_why_row_states_its_origin(match_detail):
    rows = match_detail["provenance"]
    assert len(rows) >= 8
    # Derived from the registry rather than a second copy of it, so a new origin has to
    # be added in the one place the UI reads - and cannot be forgotten there.
    allowed = set(explain.ORIGINS)
    for row in rows:
        assert row["origin"] in allowed, row
        assert row["origin_label"] and row["origin_note"], row
        assert row["value"] not in (None, ""), row


def test_the_user_input_and_the_machine_numbers_are_kept_apart(match_detail):
    by_field = {row["field"]: row["origin"] for row in match_detail["provenance"]}
    assert by_field["Waste description and quantity"] == "user"
    assert by_field["Reported composition"] == "user"
    assert by_field["Distance"] == "calculated"
    assert by_field["Match score"] == "calculated"
    assert by_field["Materials this partner accepts"] == "recipient"
    assert by_field["Safety classification and use category"] == "knowledge_base"
    assert by_field["Reuse pathway"] == "knowledge_base"


def test_demo_estimates_are_labelled_as_estimates(match_detail):
    """The two numbers most likely to be mistaken for facts - money and CO2e."""
    rows = {row["field"]: row for row in match_detail["provenance"]}
    for field in ("Estimated economic value", "Estimated CO₂e avoided"):
        row = rows[field]
        assert row["origin"] == "estimate"
        assert row["origin_label"] == "DEMO ESTIMATE"
        assert "demo" in row["detail"].lower() or "not a" in row["detail"].lower()


def test_identification_origin_matches_the_engine_that_ran(match_detail, fly_ash):
    row = next(r for r in match_detail["provenance"] if r["field"] == "Material identification")
    engine = fly_ash["identification"]["engine"]
    if engine.startswith("ollama"):
        assert row["origin"] == "ai"
    elif engine == "user_correction":
        assert row["origin"] == "user"
    else:
        assert row["origin"] == "calculated"
    assert engine in row["detail"]


def test_the_weights_shown_are_the_ones_the_engine_used(match_detail):
    from matching.engine import WEIGHTS

    assert match_detail["weights_used"] == WEIGHTS
    assert sum(match_detail["weights_used"].values()) == pytest.approx(1.0)


def test_an_unknown_material_says_so_instead_of_inventing_provenance(client):
    analysis = client.post(
        "/api/analyze",
        json={
            "source_type": "other",
            "material_description": "Some leftover we do not want any more.",
            "quantity": 2.0,
            "unit": "tonnes",
            "location": "Chennai",
            "frequency": "monthly",
        },
    ).json()["analysis"]
    assert analysis["material"]["id"] == "unknown_material"
    # Unidentified streams are not sold: no reuse value is claimed for them.
    assert analysis["totals"]["estimated_value_inr_per_month"] == 0.0
    for match in analysis["matches"]:
        assert match["estimated_value_inr_per_month"] == 0.0
    detail = client.get(f"/api/matches/{analysis['id']}/{analysis['matches'][0]['recipient']['id']}").json()
    ident = next(r for r in detail["provenance"] if r["field"] == "Material identification")
    assert "Unidentified" in ident["value"]
    assert analysis["identification"]["confidence"] < 0.5
    # The low-confidence restriction is told to the user, not silently applied.
    assert any("licensed waste processor" in w for w in analysis["warnings"])


# ---------------------------------------------------------------------------
# Feature 7 - material intelligence
# ---------------------------------------------------------------------------


def test_intelligence_card_lists_the_checks_that_were_actually_made(fly_ash, client):
    card = client.get(f"/api/intelligence?analysis_id={fly_ash['id']}").json()
    checks = {row["check"]: row for row in card["evidence"]}
    assert len(checks) == len(card["evidence"])
    assert any(row["passed"] for row in card["evidence"])
    for row in card["evidence"]:
        assert row["origin"] == "calculated"
        assert row["origin_label"] == "CALCULATED"
        assert row["detail"]


def test_composition_check_reports_the_numbers_the_user_gave(fly_ash, client):
    card = client.get(f"/api/intelligence?analysis_id={fly_ash['id']}").json()
    composition = next(row for row in card["evidence"] if "composition" in row["check"].lower())
    assert "sio2" in composition["detail"].lower()
    assert card["sections"][2]["value"]["sio2"] == "55%"
    assert card["sections"][2]["origin"] == "user"


def test_composition_check_admits_when_nothing_was_stated(client):
    analysis = client.post("/api/analyze", json=CARDBOARD_REQUEST).json()["analysis"]
    card = client.get(f"/api/intelligence?analysis_id={analysis['id']}").json()
    composition = next(row for row in card["evidence"] if "composition" in row["check"].lower())
    assert composition["passed"] is False
    assert "no composition" in composition["detail"].lower()


def test_intelligence_sections_are_the_knowledge_base_record(fly_ash, client):
    from knowledge_base.materials import MATERIALS_BY_ID

    card = client.get(f"/api/intelligence?analysis_id={fly_ash['id']}").json()
    record = MATERIALS_BY_ID["fly_ash"]
    titles = [section["title"] for section in card["sections"]]
    assert titles[:3] == ["What is it?", "Physical properties", "Typical composition"]
    for expected in ["Potential applications", "Compatible sectors", "Processing requirements", "Safety classification",
                     "Restrictions and routing rules", "Environmental note", "Economic note"]:
        assert expected in titles, expected

    by_title = {section["title"]: section for section in card["sections"]}
    assert by_title["What is it?"]["value"] == record["description"]
    assert by_title["Physical properties"]["value"] == record["properties"]
    assert by_title["Safety classification"]["value"].startswith(record["safety_level"].title())
    assert by_title["Notes from the knowledge base"]["value"] == record["notes"]
    assert card["verification"] == "demo"


def test_intelligence_card_changes_with_the_material(fly_ash, client):
    cardboard = client.post("/api/analyze", json=CARDBOARD_REQUEST).json()["analysis"]
    a = client.get(f"/api/intelligence?analysis_id={fly_ash['id']}").json()
    b = client.get(f"/api/intelligence?analysis_id={cardboard['id']}").json()
    assert a["material"]["id"] != b["material"]["id"]
    assert str(a["sections"]) != str(b["sections"])
    assert a["material"]["gate_rules"] != b["material"]["gate_rules"]
    assert "Fly Ash" not in str(b["sections"])
    assert b["material"]["name"] == "Cardboard / OCC"


def test_gate_rules_are_published_from_the_code_that_enforces_them(fly_ash, client):
    from matching.engine import gate_rules_for

    card = client.get(f"/api/intelligence?analysis_id={fly_ash['id']}").json()
    from knowledge_base.materials import MATERIALS_BY_ID

    assert card["material"]["gate_rules"] == gate_rules_for(MATERIALS_BY_ID["fly_ash"])


def test_analyze_response_carries_the_same_card(client):
    """No second source of truth: the analysis response ships the card inline."""
    body = client.post("/api/analyze", json=CARDBOARD_REQUEST).json()
    card = client.get(f"/api/intelligence?analysis_id={body['analysis']['id']}").json()
    inline = body["intelligence"]
    # The endpoint adds routing metadata; the card content is identical.
    skip = {"analysis_id", "demo_data"}
    assert {k: v for k, v in inline.items() if k not in skip} == {k: v for k, v in card.items() if k not in skip}
