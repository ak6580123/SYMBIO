"""Filtering, sorting and the promise that the map shows the same set (Features 1, 3).

The engine's weights and score maths are covered in test_matching.py; this file
covers the query surface built on top of it:

  * every filter returns a subset that actually satisfies the filter;
  * each sort order is monotonic in the field it claims to sort by;
  * /api/map is built from the same filtered, sorted list as /api/matches, so
    the two views can never disagree;
  * unknown filter values are rejected instead of ignored.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def fly_ash(client):
    """The primary demo scenario: industrial fly ash, 5 t/month, Chennai."""
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


def matches(client, analysis_id, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.post(f"/api/matches?analysis_id={analysis_id}{('&' + query) if query else ''}")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sort,key",
    [
        ("score", lambda m: -m["score"]),
        ("distance", lambda m: m["distance_km"]),
        ("value", lambda m: -m["estimated_value_inr_per_month"]),
        ("environmental", lambda m: -m["estimated_co2e_t_per_month"]),
    ],
)
def test_sort_orders_are_monotonic(client, fly_ash, sort, key):
    body = matches(client, fly_ash, sort=sort)
    values = [key(m) for m in body["matches"]]
    assert values == sorted(values), f"{sort} sort is not ordered: {values}"
    assert body["sort"] == sort  # the UI echoes it back so the view can stay in sync


def test_default_sort_is_by_score(client, fly_ash):
    body = matches(client, fly_ash)
    scores = [m["score"] for m in body["matches"]]
    assert scores == sorted(scores, reverse=True)


def test_sorting_is_stable_across_requests(client, fly_ash):
    """Same query twice, same order. A ranking that jitters mid-demo is not credible."""
    first = [m["id"] for m in matches(client, fly_ash, sort="distance")["matches"]]
    second = [m["id"] for m in matches(client, fly_ash, sort="distance")["matches"]]
    assert first == second


def test_unknown_sort_is_rejected(client, fly_ash):
    resp = client.post(f"/api/matches?analysis_id={fly_ash}&sort=vibes")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "partner",
    ["industry", "sme", "recycler", "processing", "agriculture", "community"],
)
def test_partner_type_filter_returns_only_that_type(client, fly_ash, partner):
    body = matches(client, fly_ash, partner_type=partner)
    assert all(m["partner_type"] == partner for m in body["matches"])
    assert body["count"] == len(body["matches"])


def test_partner_types_partition_the_result_set(client, fly_ash):
    """Every match lands in exactly one partner type - none silently dropped."""
    total = matches(client, fly_ash)["count"]
    across = sum(matches(client, fly_ash, partner_type=p)["count"] for p in
                 ("industry", "sme", "recycler", "processing", "agriculture", "community"))
    assert across == total


def test_safety_level_filter(client, fly_ash):
    body = matches(client, fly_ash, safety_level="moderate")
    assert body["count"] > 0
    assert all(m["safety_level"] == "moderate" for m in body["matches"])
    assert matches(client, fly_ash, safety_level="hazardous")["count"] == 0


@pytest.mark.parametrize("reuse_type", ["DIRECT_REUSE", "REQUIRES_PROCESSING", "INDUSTRIAL_ONLY", "RESTRICTED", "UNKNOWN"])
def test_reuse_type_filter_accepts_every_classification(client, fly_ash, reuse_type):
    """RESTRICTED used to be missing from the UI's option list; the API must take all five."""
    resp = client.post(f"/api/matches?analysis_id={fly_ash}&reuse_type={reuse_type}")
    assert resp.status_code == 200
    body = resp.json()
    assert all(m["reuse_type"] == reuse_type for m in body["matches"])


def test_filters_combine(client, fly_ash):
    wide = matches(client, fly_ash, max_distance_km=40)["count"]
    narrow = matches(client, fly_ash, max_distance_km=40, min_match_score=76)["count"]
    assert narrow <= wide
    assert all(m["distance_km"] <= 40 and m["score"] >= 76 for m in matches(client, fly_ash, max_distance_km=40, min_match_score=76)["matches"])


def test_unknown_filter_value_is_rejected_not_ignored(client, fly_ash):
    assert client.post(f"/api/matches?analysis_id={fly_ash}&partner_type=spaceship").status_code == 422
    assert client.post(f"/api/matches?analysis_id={fly_ash}&safety_level=pretty-safe").status_code == 422


# ---------------------------------------------------------------------------
# The map must be the matches list, drawn
# ---------------------------------------------------------------------------


def test_map_shows_exactly_the_filtered_matches(client, fly_ash):
    body = matches(client, fly_ash)
    geo = client.get(f"/api/map?analysis_id={fly_ash}").json()
    assert len(geo["links"]) == body["count"]
    # one source node plus one node per match, no hardcoded extras
    assert len(geo["nodes"]) == body["count"] + 1
    assert {link["id"] for link in geo["links"]} == {m["id"] for m in body["matches"]}


def test_map_honours_the_same_filters(client, fly_ash):
    for params in ({"partner_type": "industry"}, {"max_distance_km": 20}, {"min_match_score": 77}):
        geo = client.get(f"/api/map?analysis_id={fly_ash}" + "".join(f"&{k}={v}" for k, v in params.items())).json()
        assert len(geo["links"]) == matches(client, fly_ash, **params)["count"], params


def test_map_link_order_follows_the_requested_sort(client, fly_ash):
    geo = client.get(f"/api/map?analysis_id={fly_ash}&sort=distance").json()
    ids = [link["id"] for link in geo["links"]]
    expected = [m["id"] for m in matches(client, fly_ash, sort="distance")["matches"]]
    assert ids == expected


def test_map_nodes_carry_what_a_popup_needs(client, fly_ash):
    """Clicking a partner has to answer 'could I send material there?'."""
    geo = client.get(f"/api/map?analysis_id={fly_ash}").json()
    recipient = next(n for n in geo["nodes"] if n["kind"] == "recipient")
    extra = recipient["extra"]
    for key in (
        "sector_label",
        "distance_km",
        "accepted_materials",
        "required_quantity_range_t_per_month",
        "processing_capability",
        "match_score",
        "safety_level",
        "reuse_type",
        "partner_type_label",
        "summary",
    ):
        assert key in extra, f"popup is missing {key}"
    assert extra["scored"] is True


def test_whole_network_view_still_filters_structurally(client):
    """No scores exist in the network view, but sector/distance/partner filters apply."""
    everyone = client.get("/api/map").json()
    assert everyone["links"], "network view should not be empty"
    close = client.get("/api/map?max_distance_km=8").json()
    assert len(close["links"]) < len(everyone["links"])
    assert all(link["distance_km"] <= 8 for link in close["links"])
    sme = client.get("/api/map?partner_type=sme").json()
    assert all(node["extra"]["partner_type"] == "sme" for node in sme["nodes"] if node["kind"] == "recipient")


# ---------------------------------------------------------------------------
# Explainability payload
# ---------------------------------------------------------------------------


def test_summary_sentence_quotes_real_numbers(client, fly_ash):
    body = matches(client, fly_ash)
    top = body["matches"][0]
    summary = top["summary"]
    assert f"{top['distance_km']} km" in summary
    assert top["company_name"] in summary
    assert summary.endswith(".")
    # The tone word has to follow the score, not lead it.
    assert summary.split(":")[0] in {"Strong match", "Good match", "Possible match", "Marginal match"}


def test_weights_are_published_with_the_explanation(client, fly_ash):
    top = matches(client, fly_ash)["matches"][0]
    detail = client.get(f"/api/matches/{top['id'].replace(':', '/')}").json()
    assert round(sum(detail["weights_used"].values()), 4) == 1.0
    assert set(detail["weights_used"]) == {"compatibility", "quantity", "location", "sector", "value", "environmental"}


# --- knowledge base surface (feature 6) -------------------------------------


def test_knowledge_base_exposes_identification_and_gate_rules(client):
    """The KB page has to show aliases, hints and the rules that apply."""
    payload = client.get("/api/materials").json()
    note = payload["verification_note"].lower()
    assert "demo" in note and "verified" in note, "records are not labelled as demo data"
    fly = next(m for m in payload["materials"] if m["id"] == "fly_ash")
    assert "pulverised fuel ash" in fly["aliases"]
    assert "pozzolan" in fly["identification_hints"]
    assert any("processing" in rule.lower() for rule in fly["gate_rules"])
    assert fly["verification"] == "demo"


def test_hazardous_gate_rule_is_stated_in_the_knowledge_base(client):
    """A hazardous record must carry its restrictions, not just its label."""
    fly = {m["id"]: m for m in client.get("/api/materials").json()["materials"]}
    catalyst = fly["spent_catalyst"]
    text = " ".join(catalyst["gate_rules"]).lower()
    assert "licensed handling" in text
    assert "community, farm or artisan" in text
    # ...and the rules come from the gate, so they cannot be nicer than the code
    assert "direct reuse" not in text or "never" in text


def test_every_material_has_at_least_the_confidence_rule(client):
    rows = client.get("/api/materials").json()["materials"]
    assert rows, "knowledge base is empty"
    for row in rows:
        assert row["gate_rules"], f"{row['id']} exposes no safety rule"
