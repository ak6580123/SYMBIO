"""§16: the acceptance walkthrough, as one test.

Twenty steps, in the order somebody would actually do them. It is written as a single
flow rather than twenty tests because the thing being accepted is the *flow*: that a
person can sign up, say who they are, publish, analyse, find it again next week, and that
none of it leaks to the organisation down the hall - and that the public demo still works
when every optional thing is switched off.

Run on its own with:  pytest tests/test_acceptance_walkthrough.py -q
"""

from __future__ import annotations

import pytest

from conftest import TEST_PASSWORD, sign_up

COIMBATORE = {
    "source_type": "industry",
    "material_description": (
        "Pulverised coal fly ash from our captive boiler in Coimbatore, dry, consistent quality"
    ),
    "quantity": 20,
    "unit": "tonnes",
    "frequency": "monthly",
    "location": "Coimbatore, Tamil Nadu",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}

MANALI = {
    "source_type": "industry",
    "material_description": (
        "Pulverised coal fly ash collected from the electrostatic precipitator of our "
        "thermal power station. Dry, fine grey powder, consistent quality."
    ),
    "quantity": 5.0,
    "unit": "tonnes",
    "frequency": "monthly",
    "location": "Manali, Chennai",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}

SUPPLY = {
    "kind": "supply",
    "material_ids": ["fly_ash"],
    "quantity_t_per_month": 20.0,
    "asking_price_inr_per_tonne": 900,
    "location": "Coimbatore, Tamil Nadu",
    "max_distance_km": 60,
    "frequency": "monthly",
    "notes": "Tipper loading at the yard gate.",
}

DEMAND = {
    "kind": "demand",
    "material_ids": ["fly_ash"],
    "quantity_t_per_month": 35.0,
    "offer_price_inr_per_tonne": 1100,
    "location": "Salem, Tamil Nadu",
    "max_distance_km": 150,
    "frequency": "monthly",
    "notes": "Two block presses, steady offtake.",
}

PROFILE = {
    "sector": "building_materials",
    "products_produced": ["Fly ash bricks", "Paving blocks", "Curbs"],
    "materials_required": [{"material_id": "fly_ash", "quantity_t_per_month": 30}],
    "waste_streams": [{"material_id": "marble_slurry", "quantity_t_per_month": 6}],
    "processing_capabilities": ["Block press", "Curing yard"],
    "certifications": ["ISO 9001:2015"],
    "contact": {"name": "Anitha R", "email": "yard@aashirwad.test", "phone": "+91 98400 00000"},
}


def test_acceptance_walkthrough(temp_sqlite, client, second_client, monkeypatch):
    # 1. A person signs up, and the organisation they belong to is created with them.
    signed_up = client.post(
        "/api/auth/signup",
        json={
            "email": "anitha@aashirwad.test",
            "password": TEST_PASSWORD,
            "display_name": "Anitha R",
            "organization_name": "Aashirwad Blocks",
            "sector": "building_materials",
            "location": "Coimbatore, Tamil Nadu",
        },
    )
    assert signed_up.status_code == 201, signed_up.text
    session = signed_up.json()["session"]
    assert session["role"] == "organization_admin"

    # 2. The application can ask who it is talking to, and gets the same answer.
    me = client.get("/api/auth/me").json()
    assert me["signed_in"] is True
    assert me["session"]["user"]["email"] == "anitha@aashirwad.test"
    assert me["session"]["organization"]["name"] == "Aashirwad Blocks"

    # 3. The organisation states who it is: the profile the polished screens read.
    assert client.put("/api/org/profile", json=PROFILE).status_code == 200
    profile = client.get("/api/org").json()["profile"]
    for field in ("sector", "products_produced", "waste_streams", "processing_capabilities", "certifications"):
        if field in ("waste_streams",):
            assert [row["material_id"] for row in profile[field]] == ["marble_slurry"], field
            assert profile[field][0]["name"], "the material's name comes from the knowledge base"
        else:
            assert profile[field] == PROFILE[field], field
    assert profile["materials_required"][0]["quantity_t_per_month"] == 30.0
    assert profile["contact"]["email"] == "yard@aashirwad.test"

    # 4. It is on disk, not in the process: a fresh connection to the file says the same.
    org_id = client.get("/api/org").json()["organization"]["id"]
    from db import repositories as repo

    on_disk = _reopen(temp_sqlite)
    assert repo.get_profile(on_disk, org_id)["certifications"] == ["ISO 9001:2015"]

    # 5. A facility is added at the place somebody typed. A place nobody can find stays
    #    as typed text rather than being moved to another city.
    good = client.post("/api/org/facilities", json={"name": "Yard 1", "location": "Coimbatore, Tamil Nadu"})
    assert good.status_code == 201
    stray = client.post("/api/org/facilities", json={"name": "Site 9", "location": "Nowhere Village"})
    assert stray.json()["facility"]["location"] == "Nowhere Village"
    assert stray.json()["facility"]["location_resolved"] is False
    assert stray.json()["facility"]["latitude"] is None

    # 6. A supply listing is published, and it is saved rather than remembered.
    supply = client.post("/api/listings", json=SUPPLY)
    assert supply.status_code == 201
    assert supply.json()["persisted"] is True
    listing_id = supply.json()["listing"]["id"]

    # 7. So is a demand listing, on the same route, with its own validation.
    demand = client.post("/api/listings", json=DEMAND)
    assert demand.json()["persisted"] is True
    assert demand.json()["listing"]["offer_price_inr_per_tonne"] == 1100

    # 8. Both are on the marketplace - for a signed-in neighbour and for a visitor with no
    #    account - as advertisements, and not as internal records.
    visitor = _anonymous_client(temp_sqlite)
    public_rows = visitor.get("/api/listings").json()["listings"]
    mine = [row for row in public_rows if row["id"] in (listing_id, demand.json()["listing"]["id"])]
    assert len(mine) == 2
    assert all(row["party_name"] == "Aashirwad Blocks" for row in mine)
    assert all("provenance" not in row and "created_by" not in row for row in mine)

    # 9. The listing is edited, and the edit is what a re-read shows.
    edited = client.patch(f"/api/org/listings/{listing_id}", json={"quantity_t_per_month": 24, "notes": "Weighbridge."})
    assert edited.json()["listing"]["quantity_t_per_month"] == 24.0
    assert repo.get_listing(on_disk, org_id, listing_id)["notes"] == "Weighbridge."

    # 10. Paused, it stops being offered but does not stop being theirs.
    client.post(f"/api/org/listings/{listing_id}/status", json={"status": "paused"})
    assert listing_id not in [row["id"] for row in visitor.get("/api/listings").json()["listings"]]
    assert listing_id in [row["id"] for row in client.get("/api/org/listings/mine").json()["listings"]]

    # 11. And back on when it is resumed.
    client.post(f"/api/org/listings/{listing_id}/status", json={"status": "active"})
    assert listing_id in [row["id"] for row in visitor.get("/api/listings").json()["listings"]]

    # 12. An analysis at a place that is not Chennai: the location survives as typed, the
    #     geography is whatever the record or a geocoder can actually support.
    run = client.post("/api/analyze", json=COIMBATORE)
    assert run.status_code == 200, run.text
    analysis = run.json()["analysis"]
    assert analysis["source"]["location"] == "Coimbatore, Tamil Nadu"
    assert analysis["material"]["name"] == "Fly Ash"
    assert analysis["identification"]["confidence"] == pytest.approx(0.78, abs=0.001)
    if analysis["source"]["location_resolved"]:
        assert abs(analysis["source"]["latitude"] - 11.001812) < 0.01
    else:
        assert analysis["source"]["latitude"] is None
        assert any("distance" in warning.lower() for warning in analysis.get("warnings") or [])

    # 13. The seeded Chennai demonstration still answers exactly as it always did.
    baseline = _anonymous_client(temp_sqlite).post("/api/analyze", json=MANALI)
    base = baseline.json()
    assert base["analysis"]["matches"][0]["overall_score"] == pytest.approx(77.5, abs=0.05)
    assert base["analysis"]["matches"][0]["distance_km"] == pytest.approx(9.9, abs=0.05)
    assert base["analysis"]["matches"][0]["estimated_value_inr_per_month"] == pytest.approx(9750, abs=1)

    # 14. The stored analysis carries completeness, safety and the provenance rows.
    top = run.json()["matches"][0]
    detail = client.get(f"/api/matches/{analysis['id']}/{top['recipient']['id']}").json()
    assert detail["weights_used"]
    assert len(detail["provenance"]) >= 12
    assert {row["origin"] for row in detail["provenance"]} <= {
        "user",
        "knowledge_base",
        "recipient",
        "calculated",
        "estimate",
        "ai",
        "external",
    }
    completeness = client.get(f"/api/analyses/{analysis['id']}/completeness").json()
    assert completeness["percent"] == analysis["completeness"]["percent"]

    # 15. Transport is an estimate with its assumptions, never a quotation. It is read
    #     from the Chennai run, because that is the one with a distance to price: the
    #     Coimbatore analysis above has no coordinates in a build with no geocoder, and
    #     an unpriced route is the correct answer there rather than a figure.
    base_detail = client.get(
        f"/api/matches/{base['analysis']['id']}/{base['analysis']['matches'][0]['recipient']['id']}"
    ).json()
    transport = base_detail["transport"]
    assert transport["estimate"] is True
    assert "not a quotation" in transport["disclaimer"].lower()
    assert transport["assumptions"]
    assert transport["distance_km"] == base["analysis"]["matches"][0]["distance_km"] == pytest.approx(9.9, abs=0.05)

    # 16. It was saved with a reference; the history lists it; opening the reference gives
    #     back the same ranking rather than a fresh one.
    reference = run.json()["reference"]
    assert reference.startswith("SYM-2026-")
    row = client.get("/api/org/history").json()["analyses"][0]
    assert row["reference"] == reference
    assert row["material"] == "Fly Ash"
    assert row["quantity_t_per_month"] == 20.0
    assert row["location"] == "Coimbatore, Tamil Nadu"
    assert row["best_match"] == top["recipient"]["company_name"]
    reopened = client.get(f"/api/analyses/{reference}").json()
    assert [m["overall_score"] for m in reopened["matches"]] == [
        m["overall_score"] for m in run.json()["matches"]
    ]

    # 17. A second organisation on the same database sees none of it.
    sign_up(second_client, "vikram@greenbrick.test", "Vikram S", "GreenBrick Clay")
    assert second_client.get("/api/org/listings/mine").json()["listings"] == []
    assert second_client.get("/api/org/history").json()["analyses"] == []
    assert second_client.get(f"/api/analyses/{reference}").status_code == 404
    assert second_client.patch(f"/api/org/listings/{listing_id}", json={"quantity_t_per_month": 1}).status_code == 404
    assert second_client.get("/api/org").json()["organization"]["name"] == "GreenBrick Clay"
    assert second_client.get("/api/org").json()["profile"]["certifications"] == []
    assert [m["email"] for m in second_client.get("/api/org/members").json()["members"]] == ["vikram@greenbrick.test"]

    # 18. Both geography providers switched off: the answer changes in exactly one way,
    #     and the words say so.
    monkeypatch.setenv("GEOCODING_PROVIDER", "off")
    monkeypatch.setenv("ROUTING_PROVIDER", "off")
    from services import geo

    geo.reset_for_tests()
    offline = client.post("/api/analyze", json={**COIMBATORE, "location": "Nowhere Village"})
    offline_reference = offline.json()["reference"]
    source = offline.json()["analysis"]["source"]
    assert source["location"] == "Nowhere Village"
    assert source["latitude"] is None and source["longitude"] is None
    assert source["location_resolved"] is False
    assert all(match["distance_km"] is None for match in offline.json()["matches"])
    offline_analysis = offline.json()["analysis"]["id"]
    first_recipient = offline.json()["matches"][0]["recipient"]["id"]
    no_route = client.get(f"/api/matches/{offline_analysis}/{first_recipient}").json()
    assert no_route["route"] is None
    assert no_route["transport"] is None, "no distance means no haulage figure, not a free trip"
    geo.reset_for_tests()

    # 19. Signing out ends it: the private routes stop answering, and signing in again
    #     brings the same organisation back.
    out = client.post("/api/auth/logout")
    assert out.json()["session_revoked"] is True
    assert client.get("/api/org").status_code == 401
    assert client.get("/api/org/history").status_code == 401
    assert client.get(f"/api/analyses/{reference}").status_code == 404, "the saved analysis is not a public page"
    assert client.post("/api/auth/login", json={"email": "anitha@aashirwad.test", "password": TEST_PASSWORD}).status_code == 200
    history = [row["reference"] for row in client.get("/api/org/history").json()["analyses"]]
    # Both runs the organisation made, newest first - including the one whose location
    # nobody could place, which is stored as the unplaced thing it is.
    assert history == [offline_reference, reference]

    # 20. With the database gone, the demo is still a demo: the public pages answer, and
    #     the private ones say why they cannot.
    from db import engine as db_engine
    from db.config import DatabaseSettings

    broken = db_engine.Database(DatabaseSettings(mode="postgres", url="postgresql://symbio:secret@127.0.0.1:1/nosuchdb"))
    db_engine.replace(broken)
    client.app.state.database = broken
    on_disk.close()
    try:
        degraded = _anonymous_client(temp_sqlite)
        assert degraded.get("/api/health").status_code == 200
        assert degraded.get("/api/health").json()["status"] == "degraded"
        assert len(degraded.get("/api/listings").json()["listings"]) >= 19, "the seeded marketplace is unaffected"
        published = degraded.post("/api/listings", json={**SUPPLY, "party_id": None})
        assert published.status_code == 201
        assert published.json()["persisted"] is False
        assert "session" in published.json()["note"].lower()
        refused = degraded.get("/api/org")
        assert refused.status_code in (401, 503)
        assert "postgresql://" not in refused.text
    finally:
        db_engine.replace(temp_sqlite)
        client.app.state.database = temp_sqlite


def _reopen(database):
    from db.engine import Database

    return Database(database.settings)


def _anonymous_client(temp_sqlite):
    """A browser with no session cookie at all.

    Not entered as a context manager on purpose: startup has already run for this app, and
    re-entering it would re-seed the demo part-way through the walkthrough.
    """
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)
