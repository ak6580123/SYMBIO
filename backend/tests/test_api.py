"""End-to-end tests for the analysis pipeline and the HTTP API."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import analysis as analysis_service  # noqa: E402
from tests.conftest import FLY_ASH_REQUEST  # noqa: E402


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------


def test_fly_ash_is_identified(fly_ash_analysis):
    ident = fly_ash_analysis["identification"]
    assert ident["material_id"] == "fly_ash"
    assert ident["confidence"] >= 0.6
    assert ident["category"] == "coal_combustion_residue"
    assert ident["requires_processing"] is True


def test_composition_is_parsed_from_text(fly_ash_analysis):
    comp = fly_ash_analysis["identification"]["composition"]
    assert comp.get("sio2") == "55%"
    assert comp.get("al2o3") == "25%"
    assert comp.get("cao") == "8%"
    assert comp.get("fe2o3") == "6%"


def test_vague_input_yields_low_confidence_and_unknown_material():
    analysis = analysis_service.build_analysis(
        {
            "source_type": "other",
            "material_description": "some stuff we do not want any more",
            "quantity": 2.0,
            "unit": "tonnes",
            "location": "Chennai",
            "frequency": "monthly",
            "composition": None,
        }
    )
    assert analysis["material"]["id"] == "unknown_material"
    assert analysis["identification"]["confidence"] < 0.5
    assert analysis["identification"]["uncertainty_note"]
    assert any(m["recipient"]["sector"] == "waste_processor" for m in analysis["matches"])


def test_llm_cannot_downgrade_a_hazard_rating():
    from ai.identification import _ground

    grounded = _ground(
        {"material": "E-Waste", "confidence": 0.9, "safety_level": "low", "requires_processing": False},
        engine="test",
    )
    assert grounded.material_id == "ewaste"
    assert grounded.safety_level.value == "hazardous"
    assert grounded.requires_processing is True


def test_llm_cannot_invent_reuse_categories():
    from ai.identification import _ground

    grounded = _ground(
        {
            "material": "Cardboard / OCC",
            "confidence": 0.9,
            "reuse_categories": ["animal_feed", "soil_amendment", "fibre_pulping"],
        },
        engine="test",
    )
    # animal_feed and soil_amendment are real categories but not valid for cardboard,
    # so only the KB-sanctioned intersection survives.
    assert grounded.reuse_categories == ["fibre_pulping"]


def test_unknown_model_material_maps_to_unknown_record():
    from ai.identification import _ground

    grounded = _ground({"material": "Unobtainium Slag", "confidence": 0.9}, engine="test")
    assert grounded.material_id == "unknown_material"
    assert grounded.confidence <= 0.35


# ---------------------------------------------------------------------------
# Units and the primary demo scenario
# ---------------------------------------------------------------------------


def test_unit_conversion():
    assert analysis_service.to_tonnes_per_month(1000, "kg", analysis_service.Frequency.monthly) == 1.0
    assert analysis_service.to_tonnes_per_month(0.2, "tonnes", analysis_service.Frequency.daily) == 6.0
    assert analysis_service.to_tonnes_per_month(7, "tonnes", analysis_service.Frequency.weekly) == 30.0
    assert analysis_service.to_tonnes_per_month(5, "tonnes", analysis_service.Frequency.continuous) == 5.0


def test_primary_demo_scenario_matches_the_spec(fly_ash_analysis):
    """Fly ash, 5 t/month, Chennai -> cement first, then brick/RMC/construction/processor."""
    sectors = [m["recipient"]["sector"] for m in fly_ash_analysis["matches"]]
    assert sectors[0] == "cement_manufacturing"
    assert "brick_manufacturing" in sectors[:4]
    for expected in ["construction_company", "waste_processor"]:
        assert expected in sectors, f"{expected} missing from ranked matches"

    top = fly_ash_analysis["matches"][0]
    assert top["overall_score"] >= 70
    assert 8.0 <= top["distance_km"] <= 12.0
    assert top["estimated_value_inr_per_month"] == 9750.0
    assert top["estimated_co2e_t_per_month"] == 1.8
    assert top["reuse_pathway"]["steps"][0] == "Industrial Waste"
    assert top["reuse_pathway"]["steps"][1] == "Fly Ash"
    assert top["reuse_pathway"]["steps"][-1] == "Blended Cement / Concrete"


def test_reasons_explain_every_scored_component(fly_ash_analysis):
    top = fly_ash_analysis["matches"][0]
    assert len(top["reasons"]) >= 5
    assert any("explicitly accepts" in r for r in top["reasons"])
    assert any("km" in r for r in top["reasons"])


def test_allocation_never_exceeds_available_quantity(fly_ash_analysis):
    allocated = sum(m["allocated_t_per_month"] for m in fly_ash_analysis["matches"])
    assert allocated <= fly_ash_analysis["source"]["quantity_t_per_month"] + 1e-6
    assert fly_ash_analysis["totals"]["allocated_t_per_month"] <= 5.0
    assert fly_ash_analysis["totals"]["diversion_rate"] <= 1.0


def test_per_route_values_survive_allocation(fly_ash_analysis):
    """A lower-ranked match must still show its standalone value, not zero."""
    assert len(fly_ash_analysis["matches"]) > 2
    for match in fly_ash_analysis["matches"][1:5]:
        assert match["estimated_value_inr_per_month"] > 0
        assert match["matched_quantity_t_per_month"] > 0


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["demo_data"] is True
    assert body["materials"] >= 20
    assert body["recipients"] >= 30
    assert "available" in body["ollama"]


def test_startup_seeds_the_demo_scenario(client):
    resp = client.get("/api/analyses")
    assert resp.status_code == 200
    rows = resp.json()["analyses"]
    assert any(r["material"] == "Fly Ash" for r in rows)


def test_analyze_endpoint(client):
    resp = client.post("/api/analyze", json=FLY_ASH_REQUEST)
    assert resp.status_code == 200
    body = resp.json()
    assert body["demo_data"] is True
    assert body["analysis"]["material"]["name"] == "Fly Ash"
    assert len(body["matches"]) > 3
    assert body["totals"]["estimated_co2e_avoided_t_per_month"] == 1.8


def test_analyze_rejects_bad_payload(client):
    resp = client.post("/api/analyze", json={"material_description": "fly ash", "quantity": -5})
    assert resp.status_code == 422
    assert "errors" in resp.json()


def test_matches_filters_work(client):
    created = client.post("/api/analyze", json=FLY_ASH_REQUEST).json()
    analysis_id = created["analysis"]["id"]

    all_matches = client.post("/api/matches", params={"analysis_id": analysis_id}).json()
    assert all_matches["count"] >= 5

    filtered = client.post(
        "/api/matches",
        params={"analysis_id": analysis_id, "sector": "brick_manufacturing"},
    ).json()
    assert filtered["count"] > 0
    assert all(m["sector"] == "brick_manufacturing" for m in filtered["matches"])

    near = client.post("/api/matches", params={"analysis_id": analysis_id, "max_distance_km": 12}).json()
    assert all(m["distance_km"] <= 12 for m in near["matches"])
    assert near["count"] < all_matches["count"]

    high = client.post("/api/matches", params={"analysis_id": analysis_id, "min_match_score": 77}).json()
    assert all(m["score"] >= 77 for m in high["matches"])

    valuable = client.post(
        "/api/matches", params={"analysis_id": analysis_id, "min_estimated_value": 9500}
    ).json()
    assert all(m["estimated_value_inr_per_month"] >= 9500 for m in valuable["matches"])

    processing = client.post(
        "/api/matches", params={"analysis_id": analysis_id, "processing": "processing_required"}
    ).json()
    assert all(m["reuse_type"] != "DIRECT_REUSE" for m in processing["matches"])


def test_match_detail_endpoint(client):
    created = client.post("/api/analyze", json=FLY_ASH_REQUEST).json()
    analysis_id = created["analysis"]["id"]
    recipient_id = created["matches"][0]["recipient"]["id"]

    resp = client.get(f"/api/matches/{analysis_id}/{recipient_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["match"]["recipient"]["id"] == recipient_id
    assert abs(sum(body["weights_used"].values()) - 1.0) < 1e-9
    assert body["analysis"]["material"]["name"] == "Fly Ash"


def test_unknown_match_returns_404(client):
    assert client.get("/api/matches/an_doesnotexist/rec_cement_01").status_code == 404
    assert client.get("/api/analyses/an_doesnotexist").status_code == 404


def test_materials_and_recipients_endpoints(client):
    materials = client.get("/api/materials").json()
    assert materials["count"] >= 20
    assert all("keywords" not in m for m in materials["materials"])

    recipients = client.get("/api/recipients").json()
    assert recipients["count"] >= 30
    assert recipients["demo_data"] is True

    filtered = client.get("/api/recipients", params={"sector": "cement_manufacturing"}).json()
    assert filtered["count"] > 0
    assert all(r["sector"] == "cement_manufacturing" for r in filtered["recipients"])


def test_dashboard_endpoint(client):
    body = client.get("/api/dashboard").json()
    assert body["demo_data"] is True
    assert len(body["recent_analyses"]) > 0
    assert len(body["top_matches"]) > 0
    assert body["impact"]["label"].startswith("Estimated impact")
    assert body["impact"]["tonnes_diverted"] <= body["impact"]["tonnes_analysed"]
    for card in body["top_matches"]:
        assert card["score"] > 0
        assert card["matched_quantity_t_per_month"] > 0


def test_impact_endpoint_exposes_its_formulae(client):
    body = client.get("/api/impact").json()
    assert "disclaimer" in body
    assert body["formulae"]["estimated_co2e_t_per_month"]
    assert body["demo_data"] is True
    assert body["totals"]["tonnes_diverted"] <= body["totals"]["tonnes_analysed"]


def test_map_endpoint_network_view(client):
    body = client.get("/api/map").json()
    assert body["demo_data"] is True
    kinds = {n["kind"] for n in body["nodes"]}
    assert kinds == {"source", "recipient"}
    assert len(body["links"]) > 0
    node_ids = {n["id"] for n in body["nodes"]}
    for link in body["links"]:
        assert link["source"] in node_ids
        assert link["target"] in node_ids


def test_map_endpoint_for_an_analysis(client):
    created = client.post("/api/analyze", json=FLY_ASH_REQUEST).json()
    analysis_id = created["analysis"]["id"]
    body = client.get("/api/map", params={"analysis_id": analysis_id}).json()
    assert body["analysis_id"] == analysis_id
    sources = [n for n in body["nodes"] if n["kind"] == "source"]
    assert len(sources) == 1
    assert len(body["links"]) == len(body["nodes"]) - 1


def test_chat_answers_are_grounded(client):
    created = client.post("/api/analyze", json=FLY_ASH_REQUEST).json()
    analysis_id = created["analysis"]["id"]
    match_id = created["matches"][0]["id"]

    resp = client.post(
        "/api/chat",
        json={"analysis_id": analysis_id, "question": "Why was this company recommended?", "match_id": match_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine"] == "deterministic"
    assert "Compatibility" in body["answer"]
    assert body["grounded_in"]

    processing = client.post(
        "/api/chat",
        json={"analysis_id": analysis_id, "question": "Does this material require processing?"},
    ).json()
    assert "True" in processing["answer"] or "requires processing" in processing["answer"].lower()

    sectors = client.post(
        "/api/chat", json={"analysis_id": analysis_id, "question": "Are there other sectors that could use it?"}
    ).json()
    assert "Cement" in sectors["answer"]

    impact = client.post(
        "/api/chat", json={"analysis_id": analysis_id, "question": "What is the estimated CO2 benefit?"}
    ).json()
    assert "demo calculation" in impact["answer"].lower()


def test_chat_admits_when_it_does_not_know(client):
    created = client.post("/api/analyze", json=FLY_ASH_REQUEST).json()
    body = client.post(
        "/api/chat",
        json={"analysis_id": created["analysis"]["id"], "question": "zzz qqq flurb"},
    ).json()
    assert "I don't have enough information to determine that." in body["answer"]
    assert body["confident"] is False


def test_chat_requires_a_known_analysis(client):
    resp = client.post("/api/chat", json={"analysis_id": "an_missing", "question": "why?"})
    assert resp.status_code == 404


def test_upload_rejects_unsupported_type(client):
    body = client.post("/api/upload", files={"file": ("report.exe", b"MZ\x90\x00", "application/octet-stream")}).json()
    assert body["ok"] is False
    assert "Unsupported" in body["message"]


def test_upload_extracts_text(client):
    body = client.post(
        "/api/upload",
        files={"file": ("report.txt", b"Fly ash, SiO2 55%, Al2O3 25%, from ESP hoppers", "text/plain")},
    ).json()
    assert body["ok"] is True
    assert "Fly ash" in body["extracted_text"]

    # and the extracted text can drive the pipeline
    analysis = analysis_service.build_analysis(
        {
            "source_type": "industry",
            "material_description": "see attached report",
            "quantity": 4.0,
            "unit": "tonnes",
            "location": "Chennai",
            "frequency": "monthly",
            "composition": None,
            "attached_text": body["extracted_text"],
            "attached_filename": "report.txt",
        }
    )
    assert analysis["material"]["id"] == "fly_ash"


def test_upload_failure_leaves_a_usable_message(client):
    body = client.post("/api/upload", files={"file": ("scan.pdf", b"%PDF-1.4 broken", "application/pdf")}).json()
    assert body["ok"] is False
    assert "instead" in body["message"]
