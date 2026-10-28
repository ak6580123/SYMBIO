"""Human-in-the-loop correction and the What-If simulator (Features 5 and 6).

Both features have to be provably *not* side doors:

  * a correction changes the identification for one analysis, re-runs the normal
    engine, and leaves the knowledge base and every other analysis alone;
  * a What-If re-runs the same engine on a temporary record - the stored analysis
    is byte-for-byte unchanged, the result is never saved, and the safety layer
    still applies at the new quantity or location.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

VAGUE_REQUEST = {
    "source_type": "industry",
    "material_description": "Grey powder left over from our boiler, stored in drums behind the turbine hall.",
    "quantity": 5.0,
    "unit": "tonnes",
    "location": "Manali, Chennai",
    "frequency": "monthly",
    "composition": None,
}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Feature 5 - correction
# ---------------------------------------------------------------------------


def test_unidentified_stream_can_be_corrected_to_a_known_material(client):
    before = client.post("/api/analyze", json=VAGUE_REQUEST).json()["analysis"]
    assert before["material"]["id"] != "fly_ash"
    assert before["user_corrected"] is False

    after = client.post("/api/analyze", json={**VAGUE_REQUEST, "material_override_id": "fly_ash"}).json()["analysis"]
    assert after["material"]["id"] == "fly_ash"
    assert after["identification"]["engine"] == "user_correction"
    assert after["identification"]["confidence"] == 1.0
    assert after["user_corrected"] is True
    assert any("manually corrected by user" in w for w in after["warnings"])
    # The model's original reading is kept so the record shows what was changed.
    assert "Unidentified Material" in after["identification"]["reasoning"]


def test_correction_feeds_the_same_engine_not_a_bypass(client):
    """A corrected analysis must reach the same routes as a genuine fly-ash run."""
    corrected = client.post("/api/analyze", json={**VAGUE_REQUEST, "material_override_id": "fly_ash"}).json()["analysis"]
    honest = client.post(
        "/api/analyze",
        json={
            **VAGUE_REQUEST,
            "material_description": "Pulverised coal fly ash collected from the electrostatic precipitator of our plant.",
        },
    ).json()["analysis"]

    # Same material record in, same routes out. Order may differ, because
    # identification confidence is an input to the compatibility component.
    assert {m["recipient"]["id"] for m in corrected["matches"]} == {m["recipient"]["id"] for m in honest["matches"]}
    assert len(corrected["matches"]) == len(honest["matches"])
    assert {m["reuse_type"] for m in corrected["matches"]} == {m["reuse_type"] for m in honest["matches"]}
    # The score may differ, because identification confidence is an input to it.
    assert corrected["totals"]["available_t_per_month"] == honest["totals"]["available_t_per_month"]


def test_correction_cannot_open_a_route_the_safety_layer_refuses(client):
    """Selecting a hazardous material does not buy access to community or farm use."""
    analysis = client.post(
        "/api/analyze",
        json={**VAGUE_REQUEST, "source_type": "household", "material_override_id": "spent_catalyst"},
    ).json()["analysis"]
    from knowledge_base.materials import MATERIALS_BY_ID

    assert MATERIALS_BY_ID["spent_catalyst"]["safety_level"] == "hazardous"
    assert analysis["matches"], "expected the licensed routes to survive"
    for match in analysis["matches"]:
        assert match["recipient"]["sector"] not in {
            "community_programme",
            "agriculture_farm",
            "artisan_sme",
        }, match["recipient"]["company_name"]


def test_correction_does_not_touch_the_knowledge_base_or_other_analyses(client):
    kb_before = client.get("/api/materials").json()
    corrected = client.post("/api/analyze", json={**VAGUE_REQUEST, "material_override_id": "fly_ash"}).json()
    kb_after = client.get("/api/materials").json()
    assert kb_before == kb_after
    assert any(m["id"] == "fly_ash" for m in kb_after["materials"])

    # A later analysis of the same words, without a correction, is unaffected:
    # the override is a property of one analysis, not a global setting.
    again = client.post("/api/analyze", json=VAGUE_REQUEST).json()["analysis"]
    assert again["identification"]["engine"] != "user_correction"
    assert again["user_corrected"] is False
    assert again["material"]["id"] != "fly_ash"


def test_correction_must_name_a_knowledge_base_material(client):
    resp = client.post("/api/analyze", json={**VAGUE_REQUEST, "material_override_id": "unobtainium"})
    assert resp.status_code == 422
    assert "knowledge base" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Feature 6 - What-If
# ---------------------------------------------------------------------------


@pytest.fixture()
def analysis_id(client):
    """A correctly identified fly ash stream, so value and ranking can move."""
    resp = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": (
                "Pulverised coal fly ash collected from the electrostatic precipitator of our "
                "thermal power station. Dry, fine grey powder, consistent quality."
            ),
            "quantity": 5.0,
            "unit": "tonnes",
            "location": "Manali, Chennai",
            "frequency": "monthly",
            "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
        },
    )
    assert resp.status_code == 200
    return resp.json()["analysis"]["id"]


@pytest.fixture()
def unknown_analysis_id(client):
    resp = client.post("/api/analyze", json=VAGUE_REQUEST)
    assert resp.status_code == 200
    return resp.json()["analysis"]["id"]


def _stored(client, analysis_id):
    return client.get(f"/api/analyses/{analysis_id}").json()


def test_scenario_uses_the_same_engine_for_a_new_quantity(client, analysis_id):
    before = _stored(client, analysis_id)
    resp = client.post("/api/scenario", json={"analysis_id": analysis_id, "quantity": 40, "unit": "tonnes"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["scenario"]["changed"]["quantity"]["to"] == "40.0 t/month"
    assert body["totals"]["available_t_per_month"] == 40.0
    assert body["totals"]["allocated_t_per_month"] <= 40.0
    assert body["totals"]["estimated_value_inr_per_month"] != before["totals"]["estimated_value_inr_per_month"]
    assert body["totals_change"]["estimated_value_inr_per_month"] == round(
        body["totals"]["estimated_value_inr_per_month"] - before["totals"]["estimated_value_inr_per_month"], 2
    )


def test_scenario_never_mutates_or_persists_anything(client, analysis_id):
    before = _stored(client, analysis_id)
    listed_before = client.get("/api/analyses").json()["analyses"]

    for payload in (
        {"quantity": 500, "unit": "tonnes"},
        {"location": "Sriperumbudur"},
        {"frequency": "weekly"},
    ):
        assert client.post("/api/scenario", json={"analysis_id": analysis_id, **payload}).status_code == 200

    assert _stored(client, analysis_id) == before
    assert client.get("/api/analyses").json()["analyses"] == listed_before


def test_scenario_reports_how_partners_moved(client, analysis_id):
    body = client.post("/api/scenario", json={"analysis_id": analysis_id, "location": "Chengalpattu, Chennai"}).json()
    assert body["scenario"]["changed"]["location"] == {"from": "Manali, Chennai", "to": "Chengalpattu, Chennai"}
    # A known place resolves to real coordinates, so no approximation warning.
    assert body["scenario"]["warnings"] == []
    moved = [m for m in body["matches"] if m["rank_change"]]
    assert moved, "moving the source across the city has to change somebody's standing"
    assert all(m["original_rank"] is not None for m in body["matches"])
    # Only the component the change could touch may move: this is the same engine
    # re-run, not a new estimate.
    stored = _stored(client, analysis_id)
    by_id = {m["id"]: m for m in stored["matches"]}
    from matching.engine import WEIGHTS

    location_moved = False
    for card in body["matches"]:
        original = by_id[card["id"]]
        for component, value in card["breakdown"].items():
            if component == "location":
                location_moved = location_moved or value != original["breakdown"]["location"]
            elif component == "weighted_total":
                # Re-derived from the components, with the fixed weights - not a
                # new number invented by the scenario.
                assert abs(value - sum(card["breakdown"][k] * w for k, w in WEIGHTS.items())) < 0.01
            else:
                assert value == original["breakdown"][component], (card["company_name"], component)
        assert card["distance_km"] != original["distance_km"]
    assert location_moved


def test_scenario_shows_ranks_that_are_not_in_the_original(client, analysis_id):
    """A quantity change can make an excluded partner viable; that must be visible."""
    small = client.post("/api/scenario", json={"analysis_id": analysis_id, "quantity": 0.2, "unit": "tonnes"}).json()
    assert small["matches"]
    assert all(card["rank_change"] is not None or card["is_new"] for card in small["matches"])


def test_frequency_only_change_is_not_a_no_op(client, analysis_id):
    monthly = client.post("/api/scenario", json={"analysis_id": analysis_id, "frequency": "monthly"}).json()
    weekly = client.post("/api/scenario", json={"analysis_id": analysis_id, "frequency": "weekly"}).json()
    assert weekly["totals"]["available_t_per_month"] > monthly["totals"]["available_t_per_month"]
    assert "frequency" in weekly["scenario"]["changed"]


def test_scenario_warns_when_a_place_is_not_in_the_gazetteer(client, analysis_id):
    body = client.post("/api/scenario", json={"analysis_id": analysis_id, "location": "Nowhere Land"}).json()
    assert any("centroid" in w or "gazetteer" in w for w in body["scenario"]["warnings"]), body["scenario"]["warnings"]


def test_safety_layer_still_gates_the_scenario(client, unknown_analysis_id):
    """More tonnes of an unidentified stream must not create reuse routes."""
    analysis_id = unknown_analysis_id
    stored = _stored(client, analysis_id)
    assert stored["identification"]["confidence"] < 0.5
    assert stored["material"]["id"] == "unknown_material"

    body = client.post("/api/scenario", json={"analysis_id": analysis_id, "quantity": 900, "unit": "tonnes"}).json()
    assert body["matches"], "the licensed assessment routes should remain"
    for card in body["matches"]:
        assert card["sector"] == "waste_processor", card
        # No reuse value is claimed for a stream nobody has identified.
        assert card["estimated_value_inr_per_month"] == 0.0
    assert body["totals"]["estimated_value_inr_per_month"] == 0.0
    assert body["count"] <= len(stored["matches"]) + 2


def test_scenario_reuses_the_shared_filters_and_modes(client, analysis_id):
    near = client.post(
        f"/api/scenario?analysis_id={analysis_id}",
        json={"analysis_id": analysis_id, "quantity": 40, "unit": "tonnes"},
    )
    assert near.status_code == 200
    body = client.post("/api/scenario", json={"analysis_id": analysis_id, "quantity": 40, "unit": "tonnes"}).json()
    assert body["sort"] == "score"

    sorted_value = client.post(
        "/api/scenario?sort=value", json={"analysis_id": analysis_id, "quantity": 40, "unit": "tonnes"}
    ).json()
    values = [c["estimated_value_inr_per_month"] for c in sorted_value["matches"]]
    assert values == sorted(values, reverse=True)


def test_scenario_for_unknown_analysis_id_is_404(client):
    assert client.post("/api/scenario", json={"analysis_id": "an_nope", "quantity": 3}).status_code == 404
