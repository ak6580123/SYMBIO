"""One organisation's data never reaches another (§3).

Isolation is asserted from the outside. Something is published as A, then looked for as
B through every door B has: the marketplace, the tenant's own list, the edit route, the
status route, the analysis history, the analysis record, the profile and the member
list. A repository query that forgot `and organization_id = ?` fails one of these, which
is the whole point of the file.
"""

from __future__ import annotations

import pytest

from conftest import sign_up

SUPPLY = {
    "kind": "supply",
    "material_ids": ["fly_ash"],
    "quantity_t_per_month": 20.0,
    "asking_price_inr_per_tonne": 900,
    "location": "Coimbatore, Tamil Nadu",
    "max_distance_km": 60,
    "frequency": "monthly",
    "notes": "Available from the yard, tipper loading.",
}

FLY_ASH = {
    "source_type": "industry",
    "material_description": "Fly ash from a 120 MW coal boiler, dry collection",
    "quantity": 20,
    "unit": "tonnes",
    "frequency": "monthly",
    "location": "Coimbatore, Tamil Nadu",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}


@pytest.fixture
def pair(temp_sqlite, client, second_client):
    """Two organisations, each signed in on its own client."""
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    sign_up(second_client, "vikram@greenbrick.test", "Vikram S", "GreenBrick Clay")
    return client, second_client


# ---------------------------------------------------------------------------- listings


def test_a_published_listing_is_advertised_to_everyone_and_owned_by_one_tenant(pair):
    admin, other = pair
    published = admin.post("/api/listings", json=SUPPLY)
    assert published.status_code == 201, published.text
    body = published.json()
    assert body["persisted"] is True
    listing_id = body["listing"]["id"]

    # Everyone in the marketplace can see the offer itself...
    marketplace = admin.get("/api/listings").json()["listings"]
    row = next((item for item in marketplace if item["id"] == listing_id), None)
    assert row is not None
    assert row["party_name"] == "Aashirwad Blocks"

    # ...but only A gets it in a list of its own.
    assert [item["id"] for item in admin.get("/api/org/listings/mine").json()["listings"]] == [listing_id]
    assert other.get("/api/org/listings/mine").json()["listings"] == []

    # The detail page is public, so the private shape of the row has to stay behind.
    detail = other.get(f"/api/listings/{listing_id}").json()["listing"]
    for private in ("provenance", "created_by", "verification_status", "organization_id", "facility_id"):
        assert private not in detail, f"{private} must not appear in a public listing view"
    # What a tenant asked for internally is not part of the advertisement: the key is
    # there so the shape of a listing does not change by who is looking, and it is empty.
    assert detail["requirements"] == {}
    assert detail["notes"] == SUPPLY["notes"]  # what was offered is what is shown


def test_another_tenant_cannot_change_or_retire_a_listing_it_does_not_own(pair):
    admin, other = pair
    listing_id = admin.post("/api/listings", json=SUPPLY).json()["listing"]["id"]

    for response in (
        other.patch(f"/api/org/listings/{listing_id}", json={"quantity_t_per_month": 999}),
        other.post(f"/api/org/listings/{listing_id}/status", json={"status": "closed"}),
    ):
        assert response.status_code == 404
        # Not "forbidden": a route that says "not one of yours" without confirming the
        # row exists would be a better neighbour, and this is the copy it uses.
        assert "not one of yours" in response.json()["detail"]

    mine = admin.get("/api/org/listings/mine").json()["listings"][0]
    assert mine["quantity_t_per_month"] == 20.0
    assert mine["lifecycle"] == "active"

    # The same routes work for the owner, which is what makes the 404 above a scope and
    # not a broken route.
    assert admin.patch(f"/api/org/listings/{listing_id}", json={"notes": "Now with a weighbridge."}).status_code == 200
    assert admin.post(f"/api/org/listings/{listing_id}/status", json={"status": "paused"}).status_code == 200


def test_a_listing_id_guesser_gets_nothing_from_another_tenant(pair):
    admin, other = pair
    listing_id = admin.post("/api/listings", json=SUPPLY).json()["listing"]["id"]
    # `GET /api/org/listings/{id}` deliberately does not exist; the only per-id route a
    # tenant has is the marketplace detail page, and that is the advertised view.
    assert other.patch(f"/api/org/listings/{listing_id}", json={"notes": "theirs"}).status_code == 404
    assert other.post(f"/api/org/listings/{listing_id}/status", json={"status": "closed"}).status_code == 404


# ---------------------------------------------------------------------------- analyses


def test_an_analysis_run_by_a_tenant_is_not_readable_by_anyone_else(pair):
    admin, other = pair
    run = admin.post("/api/analyze", json=FLY_ASH)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["saved"] is True
    analysis_id = body["analysis"]["id"]
    reference = body["reference"]
    assert reference.startswith("SYM-")

    # Another tenant, and an anonymous visitor, both get "no such analysis" - by id and
    # by reference - rather than somebody else's ranking.
    for probe in (analysis_id, reference):
        assert other.get(f"/api/analyses/{probe}").status_code == 404
        assert admin.get(f"/api/analyses/{probe}").status_code == 200  # the owner still can

    # The owner's history has it; the neighbour's is empty.
    assert [row["reference"] for row in admin.get("/api/org/history").json()["analyses"]] == [reference]
    assert other.get("/api/org/history").json()["analyses"] == []


def test_a_private_analysis_is_absent_from_the_public_lists(pair):
    admin, other = pair
    run = admin.post("/api/analyze", json=FLY_ASH)
    analysis_id = run.json()["analysis"]["id"]

    # The public pool still holds the seeded demonstrations for a neighbour, which is
    # correct; what must not be in it is a run that belongs to somebody else.
    listed = other.get("/api/analyses").json()
    assert listed["count"] == len(listed["analyses"])
    assert all(row["id"] != analysis_id for row in listed["analyses"])


def test_an_anonymous_analysis_stays_public_so_the_demo_keeps_working(client):
    run = client.post("/api/analyze", json=FLY_ASH)
    assert run.status_code == 200
    assert run.json()["saved"] is False
    analysis_id = run.json()["analysis"]["id"]
    assert client.get(f"/api/analyses/{analysis_id}").status_code == 200
    assert analysis_id in [row["id"] for row in client.get("/api/analyses").json()["analyses"]]


# ---------------------------------------------------------------------------- the organisation itself


def test_the_profile_facilities_and_members_are_not_shared(pair):
    admin, other = pair
    saved = admin.put(
        "/api/org/profile",
        json={
            "sector": "building_materials",
            "products_produced": ["Fly ash blocks", "Paving blocks"],
            "materials_required": [{"material_id": "fly_ash", "quantity_t_per_month": 30, "note": "Boiler flue, dry"}],
            "waste_streams": [],
            "processing_capabilities": ["Block press"],
            "certifications": ["ISO 9001"],
            "contact": {"email": "yard@aashirwad.test"},
        },
    )
    assert saved.status_code == 200, saved.text
    admin.post("/api/org/facilities", json={"name": "Coimbatore yard", "location": "Coimbatore, Tamil Nadu"})

    theirs = other.get("/api/org").json()
    assert theirs["organization"]["name"] == "GreenBrick Clay"
    assert theirs["profile"]["products_produced"] == []
    assert theirs["profile"]["materials_required"] == []
    assert theirs["facilities"] == []
    assert [row["email"] for row in theirs["members"]] == ["vikram@greenbrick.test"]
    assert theirs["counts"] == {"listings": 0, "analyses": 0, "facilities": 0}

    ours = admin.get("/api/org").json()
    assert ours["profile"]["products_produced"] == ["Fly ash blocks", "Paving blocks"]
    assert ours["counts"]["listings"] == 0
    assert ours["counts"]["facilities"] == 1


def test_the_public_status_endpoint_reports_counts_and_no_records(client, pair):
    admin, other = pair
    admin.post("/api/listings", json=SUPPLY)
    admin.post("/api/analyze", json=FLY_ASH)
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    text = response.text
    assert body["data"]["persistent"]["listings"] == 1
    assert body["data"]["persistent"]["analyses"] == 1
    assert body["data"]["persistent"]["organizations"] == 2
    assert "aashirwad" not in text.lower()
    assert "lst_" not in text and "SYM-" not in text  # totals, never the rows


def test_the_material_a_tenant_declares_is_not_a_fact_about_the_network(pair):
    """A profile line must not become a property of the seeded recipients."""
    admin, other = pair
    admin.put("/api/org/profile", json={"materials_required": [{"material_id": "fly_ash", "quantity_t_per_month": 30}]})
    run = other.post("/api/analyze", json=FLY_ASH)
    scores_before = [match["overall_score"] for match in run.json()["matches"]]

    admin.put("/api/org/profile", json={"materials_required": [{"material_id": "bottom_ash"}]})
    assert admin.get("/api/org").json()["profile"]["materials_required"][0]["name"] == "Bottom Ash"
    run_again = other.post("/api/analyze", json=FLY_ASH)
    assert [match["overall_score"] for match in run_again.json()["matches"]] == scores_before

