"""Where a stream sits on the map: the location a user states is the location used.

The rule these tests hold
-------------------------
The seeded network is Chennai-region, and that is fine - the partners, sources and
demand areas really are there. But *user* geography must never be defaulted to
Chennai. An unresolvable place keeps its text and loses its coordinates; it does not
get the city centroid, and therefore does not get a distance, a freight figure or a
distance-driven ranking position measured from somewhere else.

A-H map onto the correctness brief for this pass:

  A  explicit coordinates win
  B  a recorded place name resolves to its own coordinates
  C  an unknown place does not silently become 13.0827, 80.2707
  D  an empty location is a validation error, not a default
  E  Coimbatore stays Coimbatore end to end
  F  Bengaluru stays Bengaluru end to end
  G  no coordinates means no invented distance, haulage or map line
  H  the seeded Chennai analysis still behaves exactly as before
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

CHENNAI_CENTROID = (13.0827, 80.2707)

BASE = {
    "source_type": "industry",
    "material_description": (
        "Pulverised coal fly ash collected from the electrostatic precipitator of our "
        "thermal power station. Dry, fine grey powder, consistent quality."
    ),
    "quantity": 5.0,
    "unit": "tonnes",
    "frequency": "monthly",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}


def analyse(client, **overrides):
    response = client.post("/api/analyze", json={**BASE, **overrides})
    assert response.status_code == 200, response.text
    return response.json()["analysis"]


def cards_for(client, analysis_id, **params):
    body = client.post("/api/matches", params={"analysis_id": analysis_id, **params})
    assert body.status_code == 200, body.text
    return body.json()["matches"]


# -------------------------------------------------------------------------- A
def test_explicit_coordinates_are_used_exactly_as_given(client):
    """A: a sender who states coordinates is never overruled by the gazetteer."""
    analysis = analyse(
        client, location="No. 4, SIDCO Industrial Estate, Coimbatore", latitude=11.0168, longitude=76.9558
    )
    source = analysis["source"]
    assert (source["latitude"], source["longitude"]) == (11.0168, 76.9558)
    assert source["location_resolved"] is True
    assert source["location"] == "No. 4, SIDCO Industrial Estate, Coimbatore"


# -------------------------------------------------------------------------- B
def test_recorded_place_resolves_to_its_own_coordinates(client):
    """B: a place in the gazetteer resolves from the gazetteer, not from a default."""
    from knowledge_base import loader

    seeded = next(row for row in loader.get_sources() if "Tambaram" in row["location"])
    source = analyse(client, location="Tambaram")["source"]
    assert (source["latitude"], source["longitude"]) == (seeded["latitude"], seeded["longitude"])
    assert source["location_resolved"] is True


# -------------------------------------------------------------------------- C
def test_unknown_place_is_not_replaced_by_the_city_centroid(client):
    """C: the point of the pass. No silent Chennai, ever."""
    source = analyse(client, location="Kodaikanal, Tamil Nadu")["source"]
    assert source["latitude"] is None
    assert source["longitude"] is None
    assert source["location_resolved"] is False
    assert (source["latitude"], source["longitude"]) != CHENNAI_CENTROID
    # the text the user typed is the source of truth, and the limit of what can be said
    assert source["location"] == "Kodaikanal, Tamil Nadu"
    assert "Chennai" not in source["location"]


def test_an_unplaced_analysis_says_so_in_the_readers_own_words(client):
    analysis = analyse(client, location="Kodaikanal, Tamil Nadu")
    warnings = " ".join(analysis["warnings"])
    assert "coordinates" in warnings
    assert "another city" in warnings


def test_no_lookup_falls_through_to_the_city_centroid():
    """C, continued: the gazetteer lookup itself cannot return a Chennai centroid.

    Substring matching is how a locality is found inside a longer string, which is
    exactly the lookup that could fall through to a city. It returns nothing instead.
    """
    from services.analysis import resolve_coordinates

    for place in ["Kodaikanal", "Yemlur, Bengaluru", "Hallim, Goa", "Salt Lake City", "Chennaiyur"]:
        assert resolve_coordinates(place, None, None) == (None, None, False), place


# -------------------------------------------------------------------------- D
@pytest.mark.parametrize("blank", ["", "   ", None])
def test_missing_location_is_a_clear_validation_error(client, blank):
    """D: refuse, explain, and never insert a city."""
    payload = dict(BASE)
    if blank is None:
        payload.pop("location", None)
    else:
        payload["location"] = blank
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    # a sentence a person can act on, not a stack of field objects
    assert isinstance(detail, str), detail
    assert "location" in detail.lower()
    assert "Chennai" not in detail


# ------------------------------------------------------------------- E and F
@pytest.mark.parametrize(
    "place",
    ["Coimbatore, Tamil Nadu", "Bengaluru, Karnataka", "Hyderabad", "Pune, Maharashtra", "Delhi"],
)
def test_a_non_chennai_place_survives_the_whole_analysis(client, place):
    """E and F: the location the user typed is what every view keeps showing."""
    analysis = analyse(client, location=place)

    assert analysis["source"]["location"] == place
    row = next(item for item in client.get("/api/analyses").json()["analyses"] if item["id"] == analysis["id"])
    assert row["location"] == place

    cards = cards_for(client, analysis["id"])
    assert cards, "an unplaced location must not empty the result set - geography is one component of six"
    for card in cards:
        assert card["source_location"] == place
        # no coordinates means no distance, on every card
        assert card["distance_km"] is None
        assert card["transport"] is None
        assert card["recipient"]["location"]  # the partner keeps its own real place


# -------------------------------------------------------------------------- G
def test_unplaced_source_leaves_geography_unscored_rather_than_fabricated(client):
    """G: what 'no coordinates' must mean for the numbers downstream."""
    match = analyse(client, location="Bengaluru, Karnataka")["matches"][0]

    # distance is absent, not zero and not the distance to Chennai
    assert match["distance_km"] is None
    assert match["breakdown"]["location"] == pytest.approx(0.5)
    assert any("distance is not scored" in reason for reason in match["reasons"]), match["reasons"]
    # every other component is still scored, so the analysis is not blocked
    assert match["breakdown"]["compatibility"] > 0
    assert match["overall_score"] > 0
    # and the summary says it could not measure, instead of naming a number
    assert "km away" not in match["summary"]
    assert "could not calculate" in match["summary"]


def test_ranking_is_not_reordered_by_an_unmeasured_distance(client):
    """G, continued: geography cannot advantage anyone when it was not measured."""
    matches = analyse(client, location="Bengaluru, Karnataka")["matches"]
    scores = [match["overall_score"] for match in matches]
    assert scores == sorted(scores, reverse=True)
    assert {round(match["breakdown"]["location"], 6) for match in matches} == {0.5}


def test_unplaced_source_is_plotted_nowhere_and_priced_nothing(client):
    """G, continued: the map, the funnel and the impact page stay honest."""
    analysis = analyse(client, location="Bengaluru, Karnataka")

    payload = client.get("/api/map", params={"analysis_id": analysis["id"]}).json()
    # the source is not plotted at all - least of all on top of Chennai
    assert [node for node in payload["nodes"] if node["kind"] == "source"] == []
    assert payload["links"] == []
    assert payload["nodes"], "partners are still shown; only the unmeasured link disappears"

    rows = [row for row in client.get("/api/material-flow").json()["routes"] if row["analysis_id"] == analysis["id"]]
    assert rows
    for row in rows:
        assert row["distance_km"] is None
        assert row["transport_status"] == "unavailable"
        assert row["transport_cost_inr_per_month"] is None
        assert row["net_economic_potential_inr_per_month"] is None

    assert client.get("/api/impact").status_code == 200


def test_scenario_over_an_unplaced_source_reports_no_freight_totals(client):
    """G, closed loop: a scenario whose routes are all unpriced says so, not zero."""
    analysis = analyse(client, location="Bengaluru, Karnataka")
    body = client.post("/api/scenario", json={"analysis_id": analysis["id"], "quantity": 8.0}).json()
    rollup = body["transport"]  # the same rollup the scenario panel and Compare read
    assert rollup["transport_cost_inr_per_month"] is None
    assert rollup["net_economic_potential_inr_per_month"] is None
    assert all(card["distance_km"] is None for card in body["matches"])


# -------------------------------------------------------------------------- H
def test_the_seeded_chennai_analysis_still_resolves_and_prices(client):
    """H: the Chennai path is untouched - real coordinates, real distance, real freight."""
    analysis = analyse(client, location="Manali, Chennai")
    source = analysis["source"]
    assert source["location_resolved"] is True
    assert source["latitude"] is not None and source["longitude"] is not None
    assert not any("gazetteer" in w for w in analysis["warnings"])

    match = analysis["matches"][0]
    assert isinstance(match["distance_km"], float) and match["distance_km"] > 0
    assert match["breakdown"]["location"] != 0.5
    assert "km away" in match["summary"]

    card = cards_for(client, analysis["id"])[0]
    assert card["transport"] is not None
    assert card["transport"]["status"] in {"viable", "marginal", "impractical", "unknown"}

    everything = cards_for(client, analysis["id"])
    nearby = cards_for(client, analysis["id"], max_distance_km=1)
    assert everything and len(nearby) < len(everything), "a measured distance has to feed the distance filter"


def test_distance_filter_keeps_unplaced_routes_instead_of_dropping_them(client):
    """H's counterpart: an unmeasured route is not 'too far', so a tight distance
    filter must not silently discard it. It stays, flagged as unplaced."""
    cards = cards_for(client, analyse(client, location="Bengaluru, Karnataka")["id"], max_distance_km=5)
    assert cards, "no coordinates is not evidence of being outside 5 km"
    assert all(card["distance_km"] is None for card in cards)


# ------------------------------------------------------------------ the store
def test_coordinates_survive_the_round_trip_through_the_store(client):
    """What-if and scenarios re-score from the stored record; they must not re-default."""
    analysis = analyse(client, location="Kodaikanal, Tamil Nadu")
    stored = client.get(f"/api/analyses/{analysis['id']}").json()
    assert stored["source"]["latitude"] is None
    assert stored["source"]["location"] == "Kodaikanal, Tamil Nadu"

    body = client.post("/api/scenario", json={"analysis_id": analysis["id"], "quantity": 8.0}).json()
    assert body["scenario"]["source"]["location"] == "Kodaikanal, Tamil Nadu"
    assert body["scenario"]["source"]["latitude"] is None
    assert body["matches"][0]["distance_km"] is None
    assert all(card["transport"] is None for card in body["matches"])


def test_a_scenario_moving_to_a_known_place_gives_geography_back(client):
    """The abstention is reversible: move to a placed town and distance returns."""
    analysis = analyse(client, location="Kodaikanal, Tamil Nadu")
    body = client.post("/api/scenario", json={"analysis_id": analysis["id"], "location": "Guindy, Chennai"}).json()
    source = body["scenario"]["source"]
    assert source["location"] == "Guindy, Chennai"
    assert source["latitude"] is not None
    assert body["matches"][0]["distance_km"] is not None
    assert body["matches"][0]["transport"] is not None


def test_a_scenario_moving_to_another_unknown_place_keeps_its_text(client):
    analysis = analyse(client, location="Manali, Chennai")
    body = client.post("/api/scenario", json={"analysis_id": analysis["id"], "location": "Mysuru, Karnataka"}).json()
    assert body["scenario"]["source"]["location"] == "Mysuru, Karnataka"
    assert body["scenario"]["source"]["latitude"] is None
    assert any("gazetteer" in warning for warning in body["scenario"]["warnings"])


# ------------------------------------------------------------------- listings
def test_listing_location_is_never_defaulted_to_the_city(client):
    """The same rule on the marketplace: an unstated location stays unstated."""
    response = client.post(
        "/api/listings",
        json={
            "kind": "supply",
            "material_ids": ["fly_ash"],
            "quantity_t_per_month": 4.0,
            "party_name": "A yard in Coimbatore",
            "location": "",
        },
    )
    assert response.status_code == 201, response.text
    listing = response.json()["listing"]
    assert listing["location"] is None
    assert listing["latitude"] is None and listing["longitude"] is None
    assert "no coordinates" in listing["location_note"]

    stored = next(row for row in client.get("/api/listings").json()["listings"] if row["id"] == listing["id"])
    assert "Chennai" not in (stored["location"] or "")


def test_a_listing_for_a_known_party_inherits_that_party_place(client):
    """Not a default: the place comes from a record that exists, or not at all."""
    from knowledge_base import loader

    source = loader.get_sources()[0]
    body = client.post(
        "/api/listings",
        json={"kind": "supply", "material_ids": ["fly_ash"], "quantity_t_per_month": 3.0, "party_id": source["id"]},
    )
    assert body.status_code == 201, body.text
    listing = body.json()["listing"]
    assert listing["location"] == source["location"]
    assert (listing["latitude"], listing["longitude"]) == (source["latitude"], source["longitude"])
    assert "party record" in listing["location_note"]


def test_two_unplaced_listings_are_matched_without_an_invented_distance(client):
    published = []
    for kind, name in (("supply", "Yard A"), ("demand", "Processor B")):
        body = client.post(
            "/api/listings",
            json={
                "kind": kind,
                "material_ids": ["fly_ash"],
                "quantity_t_per_month": 4.0,
                "party_name": name,
                "location": f"{name}'s premises, unknown town",
                "asking_price_inr_per_tonne": 900 if kind == "supply" else None,
                "offer_price_inr_per_tonne": 900 if kind == "demand" else None,
            },
        )
        assert body.status_code == 201, body.text
        published.append(body.json()["listing"]["id"])

    ids = set(published)
    pairs = [
        row
        for row in client.post("/api/listings/match", json={"listing_id": published[0]}).json().get("counterparties", [])
        if row["listing"]["id"] in ids
    ]
    if pairs:
        assert pairs[0]["distance_km"] is None
        assert pairs[0]["fit_components"]["distance"] == 0.5
