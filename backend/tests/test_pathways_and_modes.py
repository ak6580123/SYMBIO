"""Reuse pathways and optimisation modes (Features 1 and 2).

What has to be true for these to be real features and not furniture:

  * pathways come out of the engine's own ranked matches - grouped, never
    invented, and every ranked partner appears in exactly one row;
  * the pathway shown as "primary" follows the selected optimisation mode, so
    "highest value" really does put the best-paying route first;
  * the five modes re-order the same result set without touching the canonical
    weighted score, and a mode that cannot change anything says so;
  * safety wins over whichever mode is chosen;
  * a different material produces different pathways (nothing is hardcoded).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from conftest import FLY_ASH_REQUEST  # noqa: E402

RICE_HUSK_REQUEST = {
    "source_type": "agriculture",
    "material_description": "Rice husk separated at our mill during milling, loose pale husk, about a trailer load a week.",
    "quantity": 12.0,
    "unit": "tonnes",
    "location": "Kumbakonam",
    "frequency": "monthly",
    "composition": None,
}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def fly_ash_id(client):
    resp = client.post("/api/analyze", json=FLY_ASH_REQUEST)
    assert resp.status_code == 200
    return resp.json()["analysis"]["id"]


@pytest.fixture(scope="module")
def rice_husk_id(client):
    resp = client.post("/api/analyze", json=RICE_HUSK_REQUEST)
    assert resp.status_code == 200
    return resp.json()["analysis"]["id"]


def _cards(client, analysis_id, sort):
    resp = client.post(f"/api/matches?analysis_id={analysis_id}&sort={sort}")
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Feature 2 - optimisation modes
# ---------------------------------------------------------------------------


def test_sort_mode_set_is_the_five_promised_modes(fly_ash_id, client):
    """The mode list is a product decision, so it is asserted, not inferred."""
    import main

    assert set(main.SORTS) == {"score", "value", "environmental", "distance", "least_processing"}
    assert set(main.SORT_LABELS) == set(main.SORTS)


@pytest.mark.parametrize(
    "sort,key",
    [
        ("score", lambda c: (-c["score"], c["distance_km"])),
        ("distance", lambda c: (c["distance_km"], -c["score"])),
        ("value", lambda c: (-c["estimated_value_inr_per_month"], -c["score"])),
        ("environmental", lambda c: (-c["estimated_co2e_t_per_month"], -c["score"])),
        ("least_processing", None),
    ],
)
def test_each_mode_returns_the_full_result_set_sorted_by_its_own_field(fly_ash_id, client, sort, key):
    from matching.engine import processing_burden

    body = _cards(client, fly_ash_id, sort)
    cards = body["matches"]
    assert body["sort"] == sort
    assert len(cards) == body["count"] == body["filtered_from"]
    if key is not None:
        assert cards == sorted(cards, key=lambda c: key(c))
    else:
        burdens = [processing_burden(c["reuse_type"]) for c in cards]
        assert burdens == sorted(burdens)
        for first, second in zip(cards, cards[1:]):
            if processing_burden(first["reuse_type"]) == processing_burden(second["reuse_type"]):
                assert first["score"] >= second["score"]


def test_modes_actually_move_different_partners_to_the_top(fly_ash_id, client):
    """'Best' has to depend on the mode - otherwise it is decoration."""
    tops = {sort: _cards(client, fly_ash_id, sort)["matches"][0]["company_name"] for sort in
            ("score", "value", "distance", "least_processing")}
    assert len(set(tops.values())) >= 2, tops
    # Value mode promotes the best-paying partner even though it is far away.
    value_top = _cards(client, fly_ash_id, "value")["matches"][0]
    score_top = _cards(client, fly_ash_id, "score")["matches"][0]
    assert value_top["estimated_value_inr_per_month"] >= score_top["estimated_value_inr_per_month"]
    # Distance mode promotes the nearest partner even though it scores lower.
    distance_top = _cards(client, fly_ash_id, "distance")["matches"][0]
    assert distance_top["distance_km"] <= score_top["distance_km"]
    assert distance_top["score"] <= score_top["score"]


def test_least_processing_prefers_routes_that_need_no_processing(client):
    """Cardboard has both direct-reuse and processing partners; direct must lead."""
    resp = client.post(
        "/api/analyze",
        json={
            "source_type": "household",
            "material_description": "Household cardboard boxes, flattened and kept dry, one pickup a week.",
            "quantity": 0.9,
            "unit": "tonnes",
            "location": "Anna Nagar, Chennai",
            "frequency": "monthly",
        },
    )
    analysis_id = resp.json()["analysis"]["id"]
    cards = _cards(client, analysis_id, "least_processing")["matches"]
    assert cards, "expected at least one route for cardboard"
    assert cards[0]["reuse_type"] == "DIRECT_REUSE"
    # Score order does not necessarily put a direct-reuse route first.
    assert any(c["reuse_type"] != "DIRECT_REUSE" for c in cards)


def test_switching_mode_never_changes_the_canonical_score(fly_ash_id, client):
    """The weighted score is fixed: a mode re-orders, it does not re-price."""
    by_mode = {
        sort: {c["id"]: (c["score"], c["breakdown"]) for c in _cards(client, fly_ash_id, sort)["matches"]}
        for sort in ("score", "value", "distance", "environmental", "least_processing")
    }
    assert all(by_mode[sort] == by_mode["score"] for sort in by_mode)


def test_mode_explains_itself_when_it_cannot_change_the_order(fly_ash_id, client):
    """Fly ash is never direct reuse in this data, so the note must say so
    rather than leave a control that appears broken."""
    env = _cards(client, fly_ash_id, "environmental")
    assert env["sort_note"], env
    co2e = {c["estimated_co2e_t_per_month"] for c in env["matches"]}
    assert len(co2e) == 1
    assert "CO₂e" in env["sort_note"] or "same on" in env["sort_note"]
    # A mode that does change something carries no note.
    assert _cards(client, fly_ash_id, "value")["sort_note"] is None
    assert _cards(client, fly_ash_id, "score")["sort_note"] is None


def test_unknown_sort_is_rejected_not_ignored(fly_ash_id, client):
    assert client.post(f"/api/matches?analysis_id={fly_ash_id}&sort=cheapest").status_code == 422


# ---------------------------------------------------------------------------
# Feature 1 - multiple reuse pathways
# ---------------------------------------------------------------------------


def test_pathways_group_the_ranked_partners_without_losing_any(fly_ash_id, client):
    body = client.get(f"/api/pathways?analysis_id={fly_ash_id}").json()
    cards = _cards(client, fly_ash_id, "score")["matches"]
    rows = ([body["primary"]] if body["primary"] else []) + body["alternatives"]

    assert body["pathway_count"] == len(rows)
    assert body["pathway_count"] <= len(cards), "grouping may collapse, never invent"

    named = [row["partner"] for row in rows] + [name for row in rows for name in row["other_partners"]]
    assert sorted(named) == sorted(c["company_name"] for c in cards)
    assert len(named) == len(set(named)), "a partner may not appear in two pathways"


def test_each_pathway_carries_the_fields_needed_to_compare_them(fly_ash_id, client):
    body = client.get(f"/api/pathways?analysis_id={fly_ash_id}").json()
    rows = [body["primary"]] + body["alternatives"]
    assert len(rows) >= 2, "fly ash must have a genuine alternative route"
    required = {
        "pathway",
        "processing",
        "sector_label",
        "product",
        "partner",
        "score",
        "distance_km",
        "reuse_type",
        "safety_level",
        "estimated_value_inr_per_month",
        "estimated_co2e_t_per_month",
        "matched_quantity_t_per_month",
        "summary",
    }
    for row in rows:
        missing = required - row.keys()
        assert not missing, f"pathway row missing {missing}"
        assert len(row["pathway"]) == 5
        assert row["pathway"][1] == "Fly Ash"


def test_primary_pathway_follows_the_chosen_mode(fly_ash_id, client):
    for sort in ("score", "value", "distance", "least_processing"):
        pathways = client.get(f"/api/pathways?analysis_id={fly_ash_id}&sort={sort}").json()
        cards = _cards(client, fly_ash_id, sort)["matches"]
        assert pathways["sort"] == sort
        assert pathways["primary"]["match_id"] == cards[0]["id"], sort


def test_alternatives_are_real_alternatives_not_repeats(fly_ash_id, client):
    body = client.get(f"/api/pathways?analysis_id={fly_ash_id}").json()
    keys = [tuple(row["pathway"][2:]) for row in [body["primary"]] + body["alternatives"]]
    assert len(keys) == len(set(keys)), "two rows must not describe the same route"
    for row in body["alternatives"]:
        assert row["score"] <= body["primary"]["score"]


def test_safety_overrides_the_mode(fly_ash_id, client):
    """A mode that favours the closest partner must not open a gated route."""
    unknown = client.post(
        "/api/analyze",
        json={
            "source_type": "other",
            "material_description": "Grey leftover from our site, stored in drums. Not sure what it is.",
            "quantity": 4,
            "unit": "tonnes",
            "location": "Chennai",
            "frequency": "monthly",
        },
    ).json()["analysis"]["id"]
    for sort in ("score", "distance", "value", "least_processing"):
        rows = client.get(f"/api/pathways?analysis_id={unknown}&sort={sort}").json()
        partners = [rows["primary"]] + rows["alternatives"] if rows["primary"] else []
        for row in partners:
            assert row["sector_label"] == "Waste Processing", (sort, row)
    # And the refusals are reported, not hidden.
    body = client.get(f"/api/pathways?analysis_id={unknown}").json()
    assert body["excluded_by_safety"] > 0


def test_gated_out_routes_are_never_added_to_fill_the_list(fly_ash_id, client):
    """No pathway may contain a partner the engine excluded."""
    for analysis_id in (fly_ash_id,):
        detail = client.get(f"/api/analyses/{analysis_id}").json()
        excluded_ids = {e["recipient_id"] for e in detail["excluded"]}
        body = client.get(f"/api/pathways?analysis_id={analysis_id}").json()
        used = {row["match_id"].split(":", 1)[1] for row in [body["primary"]] + body["alternatives"]}
        assert used & excluded_ids == set()


def test_a_different_material_changes_the_pathways(rice_husk_id, client):
    """Nothing in the pathway builder may be fly-ash specific."""
    body = client.get(f"/api/pathways?analysis_id={rice_husk_id}").json()
    rows = [body["primary"]] + body["alternatives"]
    assert rows, "rice husk must produce at least one pathway"
    text = str(rows)
    assert "Fly Ash" not in text
    assert all(row["pathway"][1] == body["material"] for row in rows)
    assert body["material"] == "Rice Husk"
    assert any("husk" in str(row["pathway"]).lower() or "Rice" in row["pathway"][1] for row in rows)


def test_pathways_are_deterministic(fly_ash_id, client):
    first = client.get(f"/api/pathways?analysis_id={fly_ash_id}").json()
    second = client.get(f"/api/pathways?analysis_id={fly_ash_id}").json()
    assert first == second


def test_pathways_honour_the_same_filters_as_the_list(fly_ash_id, client):
    """One filter list, shared by the list, the map and the pathway view."""
    body = client.get(f"/api/pathways?analysis_id={fly_ash_id}&max_distance_km=15").json()
    rows = [body["primary"]] + body["alternatives"]
    assert rows
    assert all(row["distance_km"] <= 15 for row in rows)
    assert body["filters_applied"] == {"max_distance_km": 15}


def test_a_pathway_never_claims_a_product_the_sector_does_not_make():
    """`choose_reuse_category` may pick nothing, but it may not borrow.

    A recipient can be a legitimate family-level match for a material without
    performing any of the reuse applications recorded for it. Labelling that
    route with another sector's product would put words in the knowledge base's
    mouth, so the function returns None and the pathway says "Assessed Material".
    """
    from knowledge_base.materials import MATERIALS
    from matching.engine import SECTOR_REUSE_PREFERENCE, choose_reuse_category

    checked = 0
    for material in MATERIALS:
        for sector, preferred in SECTOR_REUSE_PREFERENCE.items():
            chosen = choose_reuse_category(material, material["reuse_categories"], sector)
            if chosen is not None:
                assert chosen in preferred, (material["id"], sector, chosen)
                assert chosen in material["reuse_categories"]
                checked += 1
    assert checked > 50, "the test must actually exercise real pairings"
    # And a real mismatch does return None: a cement plant is not a board mill.
    rice_husk = next(m for m in MATERIALS if m["id"] == "rice_husk")
    assert choose_reuse_category(rice_husk, rice_husk["reuse_categories"], "cement_manufacturing") is None
    assert choose_reuse_category(rice_husk, rice_husk["reuse_categories"], "furniture_manufacturer") == (
        "panel_and_board_making"
    )


def test_an_unmatched_sector_is_flagged_instead_of_dressed_up(rice_husk_id, client):
    """Such a route stays visible - it is a family-level match - but says so."""
    detail = client.get(f"/api/analyses/{rice_husk_id}").json()
    flagged = [m for m in detail["matches"] if any("No reuse application is recorded" in c for c in m["cautions"])]
    labelled = [m for m in detail["matches"] if m["reuse_pathway"]["steps"][-1] == "Assessed Material"]
    assert flagged, "rice husk at a cement plant is the case this must catch"
    assert {m["id"] for m in flagged} == {m["id"] for m in labelled}
    for match in flagged:
        # The product step must not name a product the sector does not perform.
        assert match["reuse_pathway"]["steps"][-1] == "Assessed Material"
