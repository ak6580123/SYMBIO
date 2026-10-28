"""What an organisation saves stays saved (§4, §5, §6).

Three things have to be true of persistence and these tests say them in the order a
reviewer would check them: the write goes to the database file (not to process memory),
a re-read after the process forgets shows the same values, and the timestamps and status
transitions the spec asks for are really recorded.
"""

from __future__ import annotations

from datetime import date

import pytest

from conftest import sign_up

PROFILE = {
    "sector": "building_materials",
    "products_produced": ["Fly ash bricks", "Paving blocks"],
    "materials_required": [{"material_id": "fly_ash", "quantity_t_per_month": 30, "note": "Boiler flue, dry"}],
    "waste_streams": [{"material_id": "gypsum_waste", "quantity_t_per_month": 4}],
    "processing_capabilities": ["Curing yard", "Block press"],
    "certifications": ["ISO 9001:2015"],
    "contact": {"name": "Anitha R", "email": "yard@aashirwad.test", "phone": "+91 98400 00000"},
}

SUPPLY = {
    "kind": "supply",
    "material_ids": ["fly_ash"],
    "quantity_t_per_month": 20.0,
    "asking_price_inr_per_tonne": 900,
    "location": "Coimbatore, Tamil Nadu",
    "max_distance_km": 60,
    "frequency": "monthly",
    "application_use": "",
}

DEMAND = {
    "kind": "demand",
    "material_ids": ["fly_ash"],
    "quantity_t_per_month": 40.0,
    "offer_price_inr_per_tonne": 1100,
    "location": "Hosur, Tamil Nadu",
    "max_distance_km": 120,
    "frequency": "monthly",
    "notes": "Two presses, steady offtake.",
    "requirements": {"application_use": "Block manufacturing", "moisture_max_percent": 25},
}

ANALYSIS = {
    "source_type": "industry",
    "material_description": "Fly ash from a 120 MW coal boiler, dry collection, consistent quality",
    "quantity": 20,
    "unit": "tonnes",
    "frequency": "monthly",
    "location": "Coimbatore, Tamil Nadu",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}


def _reopen(temp_sqlite):
    """A brand-new connection to the same file: what a restart would see."""
    from db.engine import Database

    return Database(temp_sqlite.settings)


# ---------------------------------------------------------------------------- the profile


def test_a_saved_profile_survives_a_process_that_forgets_everything(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    assert client.put("/api/org/profile", json=PROFILE).status_code == 200

    read_back = client.get("/api/org").json()["profile"]
    assert read_back["products_produced"] == PROFILE["products_produced"]
    assert read_back["certifications"] == PROFILE["certifications"]
    assert read_back["contact"]["email"] == "yard@aashirwad.test"
    assert read_back["updated_at"], "a profile that was saved has to say when"

    on_disk = _reopen(temp_sqlite)
    org_id = client.get("/api/org").json()["organization"]["id"]
    from db import repositories as repo

    stored = repo.get_profile(on_disk, org_id)
    assert stored["waste_streams"] == [{"material_id": "gypsum_waste", "quantity_t_per_month": 4.0, "name": "Gypsum Waste"}]
    on_disk.close()


def test_an_edit_to_the_profile_replaces_only_what_was_sent(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    client.put("/api/org/profile", json=PROFILE)
    response = client.put("/api/org/profile", json={"products_produced": ["Fly ash bricks"]})
    assert response.status_code == 200

    profile = client.get("/api/org").json()["profile"]
    assert profile["products_produced"] == ["Fly ash bricks"]
    # A field the caller said nothing about keeps its value; clearing one is a statement
    # and has to be made as one.
    assert profile["certifications"] == PROFILE["certifications"]
    assert client.put("/api/org/profile", json={"certifications": []}).status_code == 200
    assert client.get("/api/org").json()["profile"]["certifications"] == []


def test_a_profile_line_that_names_an_unknown_material_is_refused(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    response = client.put("/api/org/profile", json={"waste_streams": [{"material_id": "moon_dust"}]})
    assert response.status_code == 422
    assert "moon_dust" in response.json()["detail"]
    assert client.get("/api/org").json()["profile"]["waste_streams"] == []


def test_a_facility_keeps_the_location_as_stated_even_when_it_cannot_be_placed(temp_sqlite, client, monkeypatch):
    monkeypatch.setenv("GEOCODING_PROVIDER", "off")
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/org/facilities", json={"name": "Site 4", "location": "Nowhere Village"})
    assert created.status_code == 201, created.text
    facility = created.json()["facility"]
    assert facility["location"] == "Nowhere Village"
    assert facility["latitude"] is None and facility["longitude"] is None
    assert facility["location_resolved"] is False
    assert facility["location_source"] == "unresolved"

    listed = client.get("/api/org/facilities").json()["facilities"]
    assert [row["location"] for row in listed] == ["Nowhere Village"]
    assert client.delete(f"/api/org/facilities/{facility['id']}").status_code == 200
    assert client.get("/api/org/facilities").json()["facilities"] == []


# ---------------------------------------------------------------------------- the listings


def test_a_listing_can_be_created_read_edited_and_retired(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/listings", json=SUPPLY).json()["listing"]
    assert created["persisted"] is True
    assert created["lifecycle"] == "active"
    assert created["created_at"] == date.today().isoformat()
    assert created["material_names"] == ["Fly Ash"]
    assert created["organization"]["name"] == "Aashirwad Blocks"
    assert created["organization"]["verification_status"] == "unverified"

    edited = client.patch(f"/api/org/listings/{created['id']}", json={"quantity_t_per_month": 26, "notes": "Weighbridge on site."})
    assert edited.status_code == 200
    assert edited.json()["changed"] == ["notes", "quantity_t_per_month"]
    listing = edited.json()["listing"]
    assert listing["quantity_t_per_month"] == 26.0
    assert listing["asking_price_inr_per_tonne"] == 900  # the price was not part of the edit
    assert listing["updated_at"], "an edited listing has to carry the time it was edited"

    retired = client.post(f"/api/org/listings/{created['id']}/status", json={"status": "closed"})
    assert retired.json()["listing"]["lifecycle"] == "closed"
    assert [row["id"] for row in client.get("/api/org/listings/mine").json()["listings"]] == [created["id"]]
    assert client.get("/api/org/listings/mine", params={"status": "active"}).json()["listings"] == []

    on_disk = _reopen(temp_sqlite)
    from db import repositories as repo

    row = repo.get_listing(on_disk, created["organization"]["id"], created["id"])
    assert row["quantity_t_per_month"] == 26.0 and row["status"] == "closed"
    on_disk.close()


def test_the_price_of_a_listing_can_be_edited_under_either_name(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/listings", json=SUPPLY).json()["listing"]
    for field, expected in (("price_inr_per_tonne", 1000), ("asking_price_inr_per_tonne", 1100)):
        response = client.patch(f"/api/org/listings/{created['id']}", json={field: expected})
        assert response.status_code == 200, response.text
        assert response.json()["listing"]["asking_price_inr_per_tonne"] == expected
    confused = client.patch(
        f"/api/org/listings/{created['id']}", json={"price_inr_per_tonne": 1, "offer_price_inr_per_tonne": 2}
    )
    assert confused.status_code == 422
    assert "one price" in confused.json()["detail"]


def test_an_edit_that_names_a_material_the_knowledge_base_lacks_is_refused(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/listings", json=SUPPLY).json()["listing"]
    response = client.patch(f"/api/org/listings/{created['id']}", json={"material_ids": ["moon_dust"]})
    assert response.status_code == 422
    assert "moon_dust" in response.json()["detail"]
    assert client.get(f"/api/listings/{created['id']}").json()["listing"]["material_ids"] == ["fly_ash"]


def test_an_empty_edit_is_refused_rather_than_reporting_a_saved_nothing(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/listings", json=SUPPLY).json()["listing"]
    response = client.patch(f"/api/org/listings/{created['id']}", json={})
    assert response.status_code == 422
    assert "nothing to change" in response.json()["detail"].lower()


def test_a_demand_listing_keeps_its_offer_and_its_application(temp_sqlite, client, second_client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/listings", json=DEMAND).json()["listing"]
    assert created["offer_price_inr_per_tonne"] == 1100
    assert "asking_price_inr_per_tonne" not in created
    assert created["requirements"]["application_use"] == "Block manufacturing"

    mine = client.get("/api/org/listings/mine").json()["listings"][0]
    assert mine["requirements"]["application_use"] == "Block manufacturing"
    assert mine["requirements"]["moisture_max_percent"] == 25
    # In the marketplace, as somebody else sees it, the row advertises what it is for
    # and not the technical limit the tenant noted for itself.
    row = next(item for item in second_client.get("/api/listings").json()["listings"] if item["id"] == created["id"])
    assert row["offer_price_inr_per_tonne"] == 1100
    assert row["requirements"] == {"application_use": "Block manufacturing"}


def test_a_relocation_of_a_listing_is_stated_as_the_organisation_stated_it(temp_sqlite, client, monkeypatch):
    monkeypatch.setenv("GEOCODING_PROVIDER", "off")
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    created = client.post("/api/listings", json=SUPPLY).json()["listing"]
    moved = client.patch(f"/api/org/listings/{created['id']}", json={"location": "Salem, Tamil Nadu"})
    listing = moved.json()["listing"]
    assert listing["location"] == "Salem, Tamil Nadu"
    assert listing["location_resolved"] is False
    assert listing["latitude"] is None, "no coordinates are invented because a place could not be found"


# ---------------------------------------------------------------------------- the analyses


def test_a_run_analysis_can_be_reopened_by_its_reference_next_time(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    run = client.post("/api/analyze", json=ANALYSIS)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["saved"] is True
    assert body["persistence"]["mode"] == "sqlite"
    reference = body["reference"]
    analysis_id = body["analysis"]["id"]

    history = client.get("/api/org/history").json()["analyses"]
    assert len(history) == 1
    row = history[0]
    assert row["reference"] == reference
    assert row["material"] == "Fly Ash"
    assert row["quantity_t_per_month"] == 20.0
    assert row["location"] == "Coimbatore, Tamil Nadu"
    assert row["match_count"] == len(body["matches"])
    assert row["best_match"] == body["matches"][0]["recipient"]["company_name"]
    assert row["best_match_score"] == body["matches"][0]["overall_score"]
    assert row["created_on"]

    for probe in (reference, analysis_id):
        reopened = client.get(f"/api/analyses/{probe}")
        assert reopened.status_code == 200, reopened.text
        stored = reopened.json()
        assert stored["id"] == analysis_id
        # The point of a history row: opening it shows what was seen then, not a rerun.
        assert [m["overall_score"] for m in stored["matches"]] == [m["overall_score"] for m in body["matches"]]
        assert [m["safety_level"] for m in stored["matches"]] == [m["safety_level"] for m in body["matches"]]
        assert stored["source"]["location"] == "Coimbatore, Tamil Nadu"


def test_the_stored_analysis_is_the_same_row_on_disk_after_a_restart(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    body = client.post("/api/analyze", json=ANALYSIS).json()
    reference = body["reference"]
    org_id = body["organization_id"]

    on_disk = _reopen(temp_sqlite)
    from db import repositories as repo

    stored = repo.get_analysis(on_disk, org_id, reference)
    assert stored is not None
    assert stored["payload"]["id"] == body["analysis"]["id"]
    assert len(stored["matches"]) == len(body["matches"])
    assert stored["location"] == "Coimbatore, Tamil Nadu"
    assert stored["completeness_percent"] == body["analysis"]["completeness"]["percent"]
    # The safety column holds the verdicts the engine already made, counted.
    assert sum(stored["safety"]["levels"].values()) == len(body["matches"])
    assert stored["safety"]["gated"] == len(body["analysis"]["excluded"])
    on_disk.close()


def test_two_runs_get_two_references_that_do_not_repeat(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    first = client.post("/api/analyze", json=ANALYSIS).json()["reference"]
    second = client.post("/api/analyze", json=ANALYSIS).json()["reference"]
    assert first != second
    assert first.startswith("SYM-2026-") and second.startswith("SYM-2026-")
    rows = client.get("/api/org/history").json()["analyses"]
    assert [row["reference"] for row in rows] == [second, first], "newest first"


def test_history_can_be_limited_and_a_run_by_a_visitor_is_not_in_any_history(client):
    response = client.get("/api/org/history", params={"limit": 1})
    assert response.status_code == 401
    run = client.post("/api/analyze", json=ANALYSIS)
    assert run.json()["saved"] is False
    assert run.json()["reference"] is None
    assert client.get("/api/analyses").json()["count"] >= 1
