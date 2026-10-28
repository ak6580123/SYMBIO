"""§6 marketplace listings and §8 transport estimates.

Two things are being held to account here. A listing must be traceable: no number in
`listings.json` was invented next to a partner record that already states something
different. And a transport figure must be honest: it is an estimate built from printed
assumptions, it can never be read as a quote, and it can never move a score.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
LISTINGS_PATH = BACKEND / "data" / "listings.json"


@pytest.fixture(autouse=True)
def _clean_session():
    """Session listings live in memory; one test's publish must not leak into the next."""
    from services import listings

    listings.reset()
    yield
    listings.reset()


# ---------------------------------------------------------------------------
# §6 - the seed file is traceable, not typed
# ---------------------------------------------------------------------------


def test_every_demand_listing_matches_the_partner_record():
    from knowledge_base import loader

    rows = json.loads(LISTINGS_PATH.read_text())["listings"]
    demand = [row for row in rows if row["kind"] == "demand"]
    assert demand, "a marketplace with no demand is a list of offers"
    for row in demand:
        recipient = loader.get_recipient(row["party_id"])
        assert recipient, f"{row['id']} names a partner that does not exist"
        assert row["offer_price_inr_per_tonne"] == float(recipient["estimated_price_inr_per_tonne"]), (
            f"{row['id']} prices it differently from the partner record"
        )
        low, high = recipient["min_quantity_t_per_month"], recipient["max_quantity_t_per_month"]
        assert low <= row["quantity_t_per_month"] <= high, f"{row['id']} is outside the partner's intake window"
        assert set(row["material_ids"]) <= set(recipient["accepted_materials"]), f"{row['id']} asks for what is not accepted"


def test_every_supply_listing_matches_the_source_and_the_knowledge_base():
    from knowledge_base import loader
    from knowledge_base.materials import MATERIALS_BY_ID

    sources = {s["id"]: s for s in loader.get_sources()}
    rows = json.loads(LISTINGS_PATH.read_text())["listings"]
    supply = [row for row in rows if row["kind"] == "supply"]
    assert supply
    for row in supply:
        source = sources[row["party_id"]]
        assert row["material_ids"] == [source["material_hint"]], f"{row['id']} offers a material the source does not record"
        assert row["asking_price_inr_per_tonne"] == float(MATERIALS_BY_ID[source["material_hint"]]["typical_price_inr_per_tonne"])
        assert (row["latitude"], row["longitude"]) == (source["latitude"], source["longitude"])


def test_hazardous_stream_is_listed_so_the_safety_layer_can_refuse_it():
    from knowledge_base import loader
    from knowledge_base.materials import MATERIALS_BY_ID

    rows = json.loads(LISTINGS_PATH.read_text())["listings"]
    hazardous = [row for row in rows if MATERIALS_BY_ID[row["material_ids"][0]]["safety_level"] == "hazardous"]
    assert hazardous, "the demo marketplace must show at least one stream the gate will argue about"


# ---------------------------------------------------------------------------
# §6 - querying, publishing, validating
# ---------------------------------------------------------------------------


def test_listing_query_filters(client):
    payload = client.get("/api/listings?kind=demand").json()
    assert payload["count"] == 10
    assert all(row["kind"] == "demand" for row in payload["listings"])
    fly_ash = client.get("/api/listings?material_id=fly_ash").json()
    # both sides of it: the cement plant's demand, the brick plant's demand, the station's supply
    assert {row["id"] for row in fly_ash["listings"]} == {"lst_dem_001", "lst_dem_002", "lst_sup_001"}
    assert fly_ash["stats"]["total"] == payload["count"] + client.get("/api/listings?kind=supply").json()["count"]


def test_unknown_kind_is_refused(client):
    assert client.get("/api/listings?kind=wants").status_code == 422


def test_publishing_a_listing_is_validated_and_admitted(client):
    created = client.post(
        "/api/listings",
        json={
            "kind": "supply",
            "party_name": "Test Yard (draft)",
            "material_ids": ["fly_ash"],
            "quantity_t_per_month": 12,
            "asking_price_inr_per_tonne": 1700,
            "location": "Manali, Chennai",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["persisted"] is False
    assert body["listing"]["origin"] == "published in this session"
    assert body["listing"]["material_names"] == ["Fly Ash"]
    listed = client.get("/api/listings?kind=supply").json()
    assert body["listing"]["id"] in {row["id"] for row in listed["listings"]}


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"kind": "supply", "material_ids": ["moon_dust"], "quantity_t_per_month": 5}, "knowledge base"),
        ({"kind": "supply", "material_ids": ["fly_ash"], "quantity_t_per_month": 0}, "greater than zero"),
        ({"kind": "supply", "material_ids": ["fly_ash"], "quantity_t_per_month": 5, "asking_price_inr_per_tonne": -1}, ""),
        ({"kind": "supply", "material_ids": ["fly_ash"], "quantity_t_per_month": 5, "asking_price_inr_per_tonne": 10_000_000}, "ceiling"),
        ({"kind": "supply", "material_ids": [], "quantity_t_per_month": 5}, "at least one material"),
        ({"kind": "swap", "material_ids": ["fly_ash"], "quantity_t_per_month": 5}, "kind must be"),
        ({"kind": "demand", "material_ids": ["fly_ash"], "quantity_t_per_month": 5, "party_id": "rec_ghost"}, "not a partner"),
    ],
)
def test_a_listing_that_could_not_be_true_is_rejected(client, payload, message):
    response = client.post("/api/listings", json=payload)
    assert response.status_code == 422
    if message:  # an empty expectation means pydantic's own range check caught it
        assert message in response.json()["detail"]


def test_a_demand_listing_cannot_smuggle_in_an_asking_price(client):
    """A demand form sends `offer_price_inr_per_tonne`. It must not quietly pick up an
    `asking_price_inr_per_tonne` from somewhere else - the two belong to opposite sides
    of the transaction, and a listing that mixes both has no honest meaning."""
    body = client.post(
        "/api/listings",
        json={
            "kind": "demand",
            "material_ids": ["fly_ash"],
            "quantity_t_per_month": 10,
            "offer_price_inr_per_tonne": 1500,
            "asking_price_inr_per_tonne": 9000,
        },
    ).json()["listing"]
    assert body["offer_price_inr_per_tonne"] == 1500.0
    assert "asking_price_inr_per_tonne" not in body
    assert client.get(f"/api/listings/{body['id']}").json()["as_row"]["price_inr_per_tonne"] == 1500.0


def test_an_invented_listing_cannot_be_drafted_past_the_rules(client):
    response = client.post("/api/listings/match", json={"kind": "demand", "material_ids": ["unicorn_dung"], "quantity_t_per_month": 4})
    assert response.status_code == 422
    assert "knowledge base" in response.json()["detail"]


# ---------------------------------------------------------------------------
# §6 - matching a listing
# ---------------------------------------------------------------------------


def test_demand_listing_finds_the_supply_listing_and_the_engine_score(client):
    body = client.post("/api/listings/match", json={"listing_id": "lst_dem_001"}).json()
    assert body["listing_source"] == "stored listing"
    counterparties = body["counterparties"]
    assert {row["listing"]["id"] for row in counterparties} >= {"lst_sup_001"}
    top = counterparties[0]
    assert top["shared_material_ids"] == ["fly_ash"]
    assert 0 < top["fit"] <= 100
    assert top["within_stated_range"] is True
    # engine rows are real engine output, on the partner the listing belongs to
    assert body["engine_matches"]
    assert body["engine_matches"][0]["recipient"]["id"] == "rec_cement_01"
    assert body["engine_matches"][0]["scored_by"] == "matching engine"
    assert body["engine_matches"][0]["transport"]["estimate"] is True
    assert "safety" in json.dumps(body["note"]).lower() or "Engine rows" in body["note"]


def test_supply_listing_reuses_the_ranking_and_the_safety_layer(client):
    body = client.post("/api/listings/match", json={"listing_id": "lst_sup_001"}).json()
    scores = [row["overall_score"] for row in body["engine_matches"]]
    assert scores == sorted(scores, reverse=True)
    assert body["engine_matches"], "fly ash has partners in the demo dataset"
    for row in body["engine_matches"]:
        assert "fly_ash" in row["recipient"]["accepted_materials"]


def test_hazardous_listing_only_reaches_licensed_handlers(client):
    body = client.post("/api/listings/match", json={"listing_id": "lst_sup_009"}).json()
    assert body["engine_matches"], "an e-waste stream does have licensed handlers"
    for row in body["engine_matches"]:
        assert "licensed_handling" in row["recipient"]["processing_capability"]
        assert row["safety_level"] == "hazardous"
    assert body["excluded_by_safety"], "unlicensed partners must have been refused, not hidden"
    reasons = " ".join(row["reason"] for row in body["excluded_by_safety"])
    assert "licensed" in reasons.lower() or "hazardous" in reasons.lower()


def test_matching_a_listing_does_not_touch_storage(client):
    from services import storage

    before = len(storage.all_newest_first())
    client.post("/api/listings/match", json={"listing_id": "lst_sup_001"})
    client.get("/api/listings/lst_dem_002")
    assert len(storage.all_newest_first()) == before


def test_listing_row_shape_is_the_postgres_shape():
    from services import listings

    row = listings.to_row(listings.get("lst_dem_001"))
    assert set(row) == {
        "id",
        "kind",
        "party_id",
        "party_name",
        "location",
        "latitude",
        "longitude",
        "material_ids",
        "quantity_t_per_month",
        "price_inr_per_tonne",
        "max_distance_km",
        "requirements",
        "notes",
        "status",
        "origin",
        "created_on",
    }


# ---------------------------------------------------------------------------
# §8 - the freight estimate
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def logistics():
    from matching import logistics

    return logistics


def test_a_short_haul_with_priced_material_is_viable(logistics):
    estimate = logistics.estimate(3.9, 5.0, 48_750.0, 9_750.0)
    assert estimate["status"] == "viable"
    assert estimate["trips_per_month"] == 1
    assert estimate["net_economic_potential_inr_per_month"] == pytest.approx(48_750.0 - estimate["transport_cost_inr_per_month"])
    assert estimate["minimum_viable_shipment_t"] <= 5.0


def test_the_breakdown_adds_up_to_the_trip_cost(logistics):
    estimate = logistics.estimate(40.0, 20.0, 39_000.0, 1_950.0)
    parts = estimate["cost_breakdown"]
    total = parts["fuel_inr"] + parts["labour_inr"] + parts["tipping_inr"] + parts["return_load_credit_inr"]
    assert total == pytest.approx(parts["cost_per_trip_inr"], abs=0.05)
    assert parts["return_load_credit_inr"] < 0, "a return load is a credit, not a cost"


def test_further_is_more_and_a_fuller_truck_is_cheaper_per_tonne(logistics):
    near = logistics.estimate(10.0, 16.0, 32_000.0, 2_000.0)
    far = logistics.estimate(90.0, 16.0, 32_000.0, 2_000.0)
    assert far["transport_cost_inr_per_month"] > near["transport_cost_inr_per_month"]
    one_tonne = logistics.estimate(40.0, 1.0, 2_000.0, 2_000.0)
    full_truck = logistics.estimate(40.0, 16.0, 32_000.0, 2_000.0)
    assert full_truck["transport_cost_inr_per_tonne"] < one_tonne["transport_cost_inr_per_tonne"]


def test_more_than_a_truck_needs_more_than_one_trip(logistics):
    estimate = logistics.estimate(25.0, 40.0, 78_000.0, 1_950.0)
    assert estimate["trips_per_month"] == 3  # 40 t over a 16 t truck
    assert estimate["load_per_trip_t"] == pytest.approx(40 / 3, abs=0.01)


def test_a_worthless_load_never_becomes_worth_it_by_being_bigger(logistics):
    estimate = logistics.estimate(60.0, 8.0, 0.0, 0.0)
    assert estimate["status"] == "impractical"
    assert estimate["minimum_viable_shipment_t"] is None
    assert "no shipment size" in estimate["minimum_viable_explanation"]
    assert "floor" in estimate["ratio_basis"]


def test_nothing_to_move_is_reported_as_such(logistics):
    estimate = logistics.estimate(20.0, 0.0, 0.0, 0.0)
    assert estimate["status"] == "unknown"
    assert estimate["trips_per_month"] == 0
    assert estimate["transport_cost_inr_per_month"] == 0.0


def test_every_estimate_prints_its_assumptions_and_says_estimate(logistics):
    estimate = logistics.estimate(12.0, 60.0, 117_000.0, 1_950.0)
    assert estimate["estimate"] is True
    assert "not a quotation" in estimate["disclaimer"]
    assert len(estimate["assumptions"]) == len(logistics.ASSUMPTIONS)
    for assumption in estimate["assumptions"]:
        assert assumption["why"], "an assumption with no reason is just a magic number"


def test_viability_band_is_consistent_with_the_minimum_viable_quantity(logistics):
    for distance in (5, 15, 30, 60, 120):
        for tonnes in (2, 8, 24, 80):
            estimate = logistics.estimate(float(distance), float(tonnes), tonnes * 1_950.0, 1_950.0)
            minimum = estimate["minimum_viable_shipment_t"]
            if estimate["status"] == "viable":
                assert minimum is not None and minimum <= tonnes
            if minimum is None:
                assert estimate["status"] == "impractical"


def test_match_cards_carry_the_estimate_without_touching_the_score(client, fly_ash_analysis):
    cards = client.post("/api/matches", params={"analysis_id": fly_ash_analysis["id"]}).json()["matches"]
    assert cards
    for card in cards:
        assert card["transport"]["estimate"] is True
        assert card["transport"]["distance_km"] == pytest.approx(card["distance_km"], abs=0.11)
    detail = client.get(f"/api/matches/{fly_ash_analysis['id']}/{cards[0]['recipient']['id']}").json()
    assert detail["transport"]["status"] in {"viable", "marginal", "impractical", "unknown"}
    # the score the estimate sits next to is still the engine's, unchanged
    assert detail["match"]["overall_score"] == fly_ash_analysis["matches"][0]["overall_score"]


# ---------------------------------------------------------------------------
# GET /api/logistics - the assumptions, published
# ---------------------------------------------------------------------------


def test_logistics_route_publishes_the_constants_the_cards_use(client):
    payload = client.get("/api/logistics").json()
    assert payload["estimate"] is None, "a partial query must not invent a calculation"
    assert "distance_km" in payload["how_to_calculate"]
    keys = {row["key"] for row in payload["assumptions"]}
    assert {"truck_capacity_t", "diesel_price_inr_per_litre", "tipping_and_gate_inr_per_trip"} <= keys
    assert len(payload["assumptions"]) == 8, "the same eight constants the cards are built from"
    for row in payload["assumptions"]:
        assert row["unit"] and row["note"]
    assert payload["bands"]["viable_at_most"] < payload["bands"]["marginal_at_most"]


def test_logistics_calculator_matches_the_card_estimate(client, fly_ash_analysis):
    """The standalone calculator and the figure on the match card are the same call."""
    cards = client.post("/api/matches", params={"analysis_id": fly_ash_analysis["id"]}).json()["matches"]
    transport = cards[0]["transport"]
    again = client.get(
        "/api/logistics",
        params={
            "distance_km": transport["distance_km"],
            "quantity_t_per_month": transport["quantity_t_per_month"],
            "value_inr_per_tonne": round(
                transport["material_value_inr_per_month"] / transport["quantity_t_per_month"], 2
            )
            if transport["quantity_t_per_month"]
            else 0,
        },
    ).json()["estimate"]
    assert again["transport_cost_inr_per_month"] == pytest.approx(transport["transport_cost_inr_per_month"])
    assert again["status"] == transport["status"]
    assert again["disclaimer"] == transport["disclaimer"]


def test_the_supply_party_list_is_the_one_the_validator_uses(client):
    """`GET /api/sources` exists so the publish form can only offer ids that will pass
    validation - a free-text party field is where a fake listing would sneak in."""
    rows = client.get("/api/sources").json()["sources"]
    assert rows, "the seeded sources back the supply side of the marketplace"
    for row in rows:
        assert {"id", "name", "sector", "location", "material_hint"} <= set(row)
    listing = client.post(
        "/api/listings",
        json={
            "kind": "supply",
            "party_id": rows[0]["id"],
            "material_ids": [rows[0]["material_hint"]],
            "quantity_t_per_month": 5,
            "asking_price_inr_per_tonne": 100,
        },
    ).json()
    assert listing["listing"]["party_id"] == rows[0]["id"]
    # a party that is not a seeded record is refused, and says which list it checked
    refused = client.post(
        "/api/listings",
        json={"kind": "supply", "party_id": "src_imaginary_99", "material_ids": ["fly_ash"], "quantity_t_per_month": 5},
    ).json()
    assert "is not a source in the demo dataset" in refused["detail"]
