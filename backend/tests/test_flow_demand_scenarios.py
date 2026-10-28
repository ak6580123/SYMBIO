"""§9 material flow, §10 regional demand potential, §11 scenario comparison."""

from __future__ import annotations

import pytest

STAGE_NAMES = ["Generated", "Technically reusable", "Economically viable", "Matched", "Processed", "Reused"]


# ---------------------------------------------------------------------------
# §9 - the funnel
# ---------------------------------------------------------------------------


def test_six_stages_in_the_named_order(client):
    flow = client.get("/api/material-flow").json()
    assert [stage["stage"] for stage in flow["stages"]] == STAGE_NAMES
    for stage in flow["stages"]:
        assert stage["definition"], "a funnel whose stages are undefined is decoration"


def test_stages_are_a_subset_chain(client):
    stages = client.get("/api/material-flow").json()["stages"]
    tonnes = [stage["tonnes_per_month"] for stage in stages]
    assert tonnes == sorted(tonnes, reverse=True), "each stage must be a subset of the one above"
    assert all(0.0 <= stage["share_of_generated"] <= 1.0 for stage in stages)


def test_generated_tonnage_is_what_the_sources_stated(client, fly_ash_analysis):
    """Single-analysis flow: the first bar is that source's own monthly figure."""
    flow = client.get(f"/api/material-flow?analysis_id={fly_ash_analysis['id']}").json()
    offered = float(fly_ash_analysis["source"]["quantity_t_per_month"])
    assert flow["stages"][0]["tonnes_per_month"] == pytest.approx(offered)
    assert flow["analyses"] == 1


def test_funnel_reconciles_with_the_impact_dashboard(client):
    """The funnel and the dashboard read the same store, so any difference between them
    has to be an explained one rather than a silent contradiction."""
    flow = client.get("/api/material-flow").json()
    impact = flow["impact_dashboard"]
    assert impact["matches_generated_tonnes"] is True
    assert impact["matches_diverted_tonnes"] is True or "caps each stage" in impact["note"]
    assert impact["difference_tonnes"] >= 0.0
    if not impact["matches_diverted_tonnes"]:
        assert impact["difference_tonnes"] > 0.0, "a flagged mismatch must be quantified"


def test_reused_can_only_lag_processed_by_unnamed_products(client):
    flow = client.get("/api/material-flow").json()
    processed, reused = flow["stages"][4]["tonnes_per_month"], flow["stages"][5]["tonnes_per_month"]
    assert reused <= processed
    if flow["reused_equals_processed"]:
        assert reused == processed
    # Every tonnage that did not reach a product went to a route the engine could not
    # name a product for - check that the routes explain the gap.
    gap = round(processed - reused, 3)
    assessed = round(
        sum(row["tonnes_per_month"] for row in flow["routes"] if row["product"] == "Assessed Material"), 3
    )
    assert assessed >= gap - 1e-6 or assessed == 0.0


def test_routes_are_source_processor_recipient_product_with_tonnage(client):
    flow = client.get("/api/material-flow").json()
    assert flow["routes"]
    for row in flow["routes"]:
        for field in ("source", "processor", "recipient", "product", "tonnes_per_month", "transport_status"):
            assert field in row
        assert row["tonnes_per_month"] >= 0
    assert flow["route_count"] >= len(flow["routes"])


def test_an_unknown_analysis_says_there_is_nothing_to_flow(client):
    flow = client.get("/api/material-flow?analysis_id=an_nothere").json()
    assert "No analyses" in flow["note"]
    assert all(stage["tonnes_per_month"] == 0.0 for stage in flow["stages"])


def test_blocked_streams_are_named_with_a_reason(client, fly_ash_analysis):
    """A stream the safety layer refused everywhere must show up as a loss, with the
    reason - not be quietly missing from the funnel."""
    unknown = client.post(
        "/api/analyze",
        json={
            "source_type": "household",
            "material_description": "A sack of mixed stuff from the back of a lorry, contents unknown",
            "quantity": 3,
            "unit": "tonnes",
            "location": "Anna Nagar, Chennai",
            "frequency": "monthly",
        },
    ).json()["analysis"]
    flow = client.get(f"/api/material-flow?analysis_id={unknown['id']}").json()
    assert flow["stages"][0]["tonnes_per_month"] == pytest.approx(3.0)
    assert flow["stages"][1]["tonnes_per_month"] == pytest.approx(0.0), "an unidentified stream is not yet reusable"
    assert flow["blocked_streams"] and "not identified" in flow["blocked_streams"][0]["reason"]


# ---------------------------------------------------------------------------
# §10 - regional demand potential
# ---------------------------------------------------------------------------


def test_areas_are_ranked_banded_and_between_zero_and_one_hundred(client):
    payload = client.get("/api/demand").json()
    areas = payload["areas"]
    assert areas, "the demo dataset has plenty of capacity to rank"
    indices = [row["demand_potential_index"] for row in areas]
    assert indices == sorted(indices, reverse=True)
    assert all(0.0 <= index <= 100.0 for index in indices)
    for row in areas:
        expected = "High" if index_is(row, 66) else "Medium" if index_is(row, 33) else "Low"
        assert row["band"] == expected


def index_is(row, floor) -> bool:
    return row["demand_potential_index"] >= floor


def test_index_is_reproducible_from_the_published_components(client):
    payload = client.get("/api/demand").json()
    weights = payload["areas"][0]["component_weights"]
    assert sum(weights.values()) == pytest.approx(1.0)
    for row in payload["areas"]:
        recomputed = 100.0 * sum(weights[key] * value for key, value in row["components"].items())
        assert row["demand_potential_index"] == pytest.approx(recomputed, abs=0.15)


def test_headroom_is_window_minus_allocated(client):
    """Recomputed straight from the records the way the service claims to do it."""
    from knowledge_base import loader
    from services import storage

    allocated: dict[str, float] = {}
    for analysis in storage.all_newest_first():
        for match in analysis["matches"]:
            allocated[match["recipient"]["id"]] = allocated.get(match["recipient"]["id"], 0.0) + float(
                match["allocated_t_per_month"]
            )
    areas = {row["area"]: row for row in client.get("/api/demand").json()["areas"]}
    by_locality: dict[str, list[dict]] = {}
    for record in loader.get_recipients():
        by_locality.setdefault((record["location"] or "").split(",")[0].strip(), []).append(record)
    for name, row in areas.items():
        computed = sum(
            max(0.0, float(record["max_quantity_t_per_month"]) - allocated.get(record["id"], 0.0))
            for record in by_locality.get(name, [])
        )
        assert row["intake_headroom_t_per_month"] == pytest.approx(computed, abs=0.05), f"{name} drifted from the records"
        assert row["partner_count"] == len(by_locality.get(name, []))


def test_demand_never_promises_a_purchase(client):
    payload = client.get("/api/demand").json()
    text = str(payload).lower()
    for phrase in ("will buy", "will purchase", "guaranteed", "committed to", "next month it will"):
        assert phrase not in text, f"a forecast claim appeared in the payload: {phrase}"
    assert "Regional potential" in payload["caveat"]
    assert "No purchase intention" in payload["not_a_forecast"]
    for row in payload["areas"]:
        assert row["drivers"], "an index nobody can explain is a decoration"


def test_material_filter_restricted_to_partners_that_take_it(client):
    payload = client.get("/api/demand?material_id=fly_ash").json()
    assert payload["material_name"] == "Fly Ash"
    from knowledge_base import loader

    recipients = {r["id"]: r for r in loader.get_recipients()}
    for area in payload["areas"]:
        for partner in area["partners"]:
            assert "fly_ash" in recipients[partner["id"]]["accepted_materials"]


def test_unknown_material_is_refused_not_guessed(client):
    payload = client.get("/api/demand?material_id=moon_dust").json()
    assert "knowledge base" in payload["error"]
    assert payload["areas"] == []


# ---------------------------------------------------------------------------
# §11 - scenario rules and comparison
# ---------------------------------------------------------------------------

BASE_SCENARIO = {"quantity": 40, "unit": "tonnes", "frequency": "monthly", "location": "Manali, Chennai"}


def test_transport_rule_only_removes_routes_and_names_the_rule(client, fly_ash_analysis):
    unfiltered = client.post("/api/scenario", json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"]}).json()
    filtered = client.post(
        "/api/scenario",
        json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"], "require_viable_transport": True},
    ).json()
    assert filtered["rules"] == {"Transport not impractical": True}
    assert filtered["count"] <= unfiltered["count"]
    for card in filtered["matches"]:
        assert card["transport"]["status"] != "impractical"
    # a rule filters: it may not re-score
    unfiltered_by_id = {card["id"]: card for card in unfiltered["matches"]}
    for card in filtered["matches"]:
        assert card["score"] == unfiltered_by_id[card["id"]]["score"]


def test_destination_rule_resolves_to_one_partner(client, fly_ash_analysis):
    filtered = client.post(
        "/api/scenario",
        json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"], "destination_recipient_id": "rec_cement_01"},
    ).json()
    assert {card["recipient"]["id"] for card in filtered["matches"]} <= {"rec_cement_01"}
    assert filtered["dropped_by_rule"], "everything else should be reported as dropped, with a reason"
    assert filtered["dropped_by_rule"][0]["rule_label"] == "Named destination only"


def test_processing_rules_use_the_records_and_the_burden_scale(client, fly_ash_analysis):
    direct = client.post(
        "/api/scenario", json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"], "max_processing_burden": 0}
    ).json()
    assert all(card["reuse_type"] == "DIRECT_REUSE" for card in direct["matches"])

    drying = client.post(
        "/api/scenario",
        json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"], "processing_capability_required": "drying"},
    ).json()
    for card in drying["matches"]:
        assert any("dry" in capability.lower() for capability in card["processing_capability"])


def test_transport_rollup_is_in_the_scenario(client, fly_ash_analysis):
    body = client.post("/api/scenario", json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"]}).json()
    rollup = body["transport"]
    assert rollup["label"].startswith("Transport estimate")
    assert rollup["net_economic_potential_inr_per_month"] == pytest.approx(
        rollup["material_value_inr_per_month"] - rollup["transport_cost_inr_per_month"], abs=0.02
    )
    assert rollup["viable_routes"] + rollup["marginal_routes"] + rollup["impractical_routes"] + rollup["unknown_routes"] == body["count"]


def test_a_ceiling_of_zero_is_a_rule_not_an_absence(client, fly_ash_analysis):
    """`max_processing_burden: 0` means "direct reuse only". A falsy-but-meaningful
    value must not be treated as an unset field."""
    body = client.post(
        "/api/scenario",
        json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"], "max_processing_burden": 0},
    ).json()
    assert body["rules"] == {"Maximum processing burden": 0}
    unfiltered = client.post("/api/scenario", json={**BASE_SCENARIO, "analysis_id": fly_ash_analysis["id"]}).json()
    zero_burden = {card["id"] for card in unfiltered["matches"] if card["reuse_type"] == "DIRECT_REUSE"}
    assert {card["id"] for card in body["matches"]} == zero_burden
    dropped_ids = {row["match_id"] for row in body["dropped_by_rule"]}
    assert dropped_ids == {card["id"] for card in unfiltered["matches"]} - zero_burden
    for row in body["dropped_by_rule"]:
        assert "steps of processing" in row["reason"]


def test_compare_table_over_two_configurations(client, fly_ash_analysis):
    body = client.post(
        "/api/scenarios/compare",
        json={
            "analysis_id": fly_ash_analysis["id"],
            "configs": [
                {"label": "As recorded", "quantity": 5},
                {"label": "Doubling output", "quantity": 40},
                {"label": "Only what a truck can carry", "quantity": 40, "require_viable_transport": True, "max_transport_cost_inr_per_tonne": 250},
            ],
        },
    ).json()
    columns = body["configurations"]
    assert [column["label"] for column in columns] == ["As recorded", "Doubling output", "Only what a truck can carry"]
    assert body["baseline_label"] == "As recorded"
    for column in columns:
        for field in ("best_match", "totals", "transport", "match_count", "viable_at_t_per_month", "changed", "rules"):
            assert field in column
        if column["best_match"]:
            for field in ("company_name", "score", "distance_km", "estimated_value_inr_per_month", "transport_status"):
                assert field in column["best_match"]
    assert columns[1]["match_count"] >= columns[0]["match_count"], "more tonnes should not reduce the partner pool"  # compare returns its own shape
    assert columns[2]["match_count"] <= columns[1]["match_count"], "a transport ceiling can only remove routes"
    assert columns[1]["delta_vs_baseline"]["estimated_value_inr_per_month"] > 0


def test_compare_requires_a_baseline_to_compare_against(client, fly_ash_analysis):
    assert client.post(
        "/api/scenarios/compare", json={"analysis_id": fly_ash_analysis["id"], "configs": [{"label": "only one"}]}
    ).status_code == 422
    too_many = [{"label": f"c{i}", "quantity": 5} for i in range(5)]
    assert client.post(
        "/api/scenarios/compare", json={"analysis_id": fly_ash_analysis["id"], "configs": too_many}
    ).status_code == 422


def test_compare_rejects_an_unknown_analysis(client):
    response = client.post(
        "/api/scenarios/compare",
        json={"analysis_id": "an_nothere", "configs": [{"label": "a"}, {"label": "b"}]},
    )
    assert response.status_code == 404


def test_comparing_scenarios_does_not_persist_anything(client, fly_ash_analysis):
    from services import storage

    before = len(storage.all_newest_first())
    client.post(
        "/api/scenarios/compare",
        json={"analysis_id": fly_ash_analysis["id"], "configs": [{"label": "small", "quantity": 5}, {"label": "big", "quantity": 200}]},
    )
    assert len(storage.all_newest_first()) == before
    stored = client.get(f"/api/analyses/{fly_ash_analysis['id']}").json()
    assert stored["source"]["quantity_t_per_month"] == fly_ash_analysis["source"]["quantity_t_per_month"]


def test_scenario_rules_cannot_surface_a_refused_route(client, fly_ash_analysis):
    """The safety layer runs before the rules, so a scenario can hide a route but
    never rescue one."""
    from services import analysis as analysis_service

    variant = analysis_service.build_scenario(dict(fly_ash_analysis), {"quantity": 40})
    allowed = {match["recipient"]["id"] for match in variant["matches"]}
    body = client.post(
        "/api/scenario",
        json={"analysis_id": fly_ash_analysis["id"], "quantity": 40, "unit": "tonnes", "location": "Manali, Chennai", "frequency": "monthly"},
    ).json()
    assert {card["recipient"]["id"] for card in body["matches"]} <= allowed
