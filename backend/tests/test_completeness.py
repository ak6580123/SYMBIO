"""§3 - missing-data detection, completeness, and what the optional fields change.

The contract these tests pin down is narrow but load-bearing: optional data buys you
*specificity*, never a better rank. If any of these fail, the pipeline has started
letting the richness of a form decide a score, which is exactly the thing Symbio
must not do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FLY_ASH_REQUEST

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _build(**overrides):
    from services import analysis as analysis_service

    payload = {**FLY_ASH_REQUEST, **overrides}
    return analysis_service.build_analysis(payload)


def _percentages(analysis) -> float:
    return analysis["completeness"]["percent"]


# ---------------------------------------------------------------------------
# the scale itself
# ---------------------------------------------------------------------------


def test_field_weights_sum_to_one_hundred():
    from services.completeness import FIELD_SPECS

    total = sum(spec.weight for spec in FIELD_SPECS)
    assert total == 100, "completeness is a percentage; the weights have to add up"


def test_every_group_is_covered_and_labelled():
    from services.completeness import FIELD_SPECS

    groups = {spec.group for spec in FIELD_SPECS}
    assert groups == {"identification", "scoring", "handling", "safety"}
    # Every optional field says what it changes, in one of the three allowed shapes.
    for spec in FIELD_SPECS:
        assert spec.changes
        assert spec.changes.startswith(("changes ", "adds ", "can only ", "nothing"))


# ---------------------------------------------------------------------------
# thin input vs full input
# ---------------------------------------------------------------------------


def test_minimal_request_scores_lower_but_still_completes():
    analysis = _build()
    completeness = analysis["completeness"]
    assert completeness["percent"] < 100
    assert completeness["blocks_analysis"] is False
    assert analysis["matches"], "a partial description must still produce real matches"
    missing_keys = {item["key"] for item in completeness["missing"]}
    assert {"physical_state", "moisture_percent", "contaminants", "intended_use"} <= missing_keys
    assert completeness["advice"], "missing data has to come with instructions, not just a number"


def test_full_request_reaches_one_hundred():
    analysis = _build(
        physical_state="powder",
        moisture_percent=1.5,
        contaminants=["carbon"],
        intended_use="cement replacement in ready-mix concrete",
    )
    assert analysis["completeness"]["percent"] == 100.0
    assert analysis["completeness"]["missing"] == []
    assert analysis["completeness"]["level"] == "complete"


def test_optional_fields_do_not_move_a_single_score_or_value():
    bare = _build()
    filled = _build(
        physical_state="powder",
        moisture_percent=1.5,
        contaminants=["carbon"],
        intended_use="cement replacement",
    )
    bare_by_id = {m["recipient"]["id"]: m for m in bare["matches"]}
    filled_by_id = {m["recipient"]["id"]: m for m in filled["matches"]}
    assert bare_by_id.keys() == filled_by_id.keys()
    for recipient_id, match in bare_by_id.items():
        other = filled_by_id[recipient_id]
        assert match["overall_score"] == other["overall_score"]
        assert match["estimated_value_inr_per_month"] == other["estimated_value_inr_per_month"]
        assert match["breakdown"] == other["breakdown"]
    # The pinned headline figure from Sprint 1/2 must survive untouched.
    assert bare["matches"][0]["overall_score"] == filled["matches"][0]["overall_score"]


# ---------------------------------------------------------------------------
# contaminants: tighten only, never relax
# ---------------------------------------------------------------------------


def test_declared_contaminants_never_open_a_route():
    bare = _build()
    dirty = _build(contaminants=["used oil", "paint chips"])

    bare_ids = {m["recipient"]["id"] for m in bare["matches"]}
    dirty_ids = {m["recipient"]["id"] for m in dirty["matches"]}
    assert dirty_ids <= bare_ids, "declaring contamination must not widen the set"

    bare_by_id = {m["recipient"]["id"]: m for m in bare["matches"]}
    dirty_by_id = {m["recipient"]["id"]: m for m in dirty["matches"]}
    order = {"low": 0, "moderate": 1, "high": 2, "hazardous": 3, "unknown": 4}
    for recipient_id, match in dirty_by_id.items():
        before = bare_by_id[recipient_id]
        assert order[match["safety_level"]] >= order[before["safety_level"]]
        assert match["reuse_type"] == before["reuse_type"]
        assert match["overall_score"] == before["overall_score"]
        # tightening does show up, as a caution on the route
        assert any("used oil" in caution for caution in match["cautions"])
        assert all("used oil" not in caution for caution in before["cautions"])
    assert dirty["contaminant_cautions_applied"] == len(dirty["matches"])


def test_contaminant_insight_names_partners_that_cannot_test():
    recipients = json.loads((DATA_DIR / "recipients.json").read_text())
    by_name = {r["company_name"]: r for r in recipients}
    analysis = _build(contaminants=["gypsum board scraps"])

    insight = next(i for i in analysis["completeness"]["insights"] if i["field"] == "contaminants")
    assert "gypsum board scraps" in insight["title"]
    for name in insight["affected_recipients"]:
        capabilities = " ".join(by_name[name]["processing_capability"]).lower()
        # The engine's own rule: no lab, testing, separation or licensed handling.
        assert not any(word in capabilities for word in ("lab", "test", "analysis", "separation", "sorting", "licensed"))


def test_moisture_insight_counts_recipients_without_drying():
    recipients = json.loads((DATA_DIR / "recipients.json").read_text())
    analysis = _build(moisture_percent=40.0)
    insight = next(i for i in analysis["completeness"]["insights"] if i["field"] == "moisture_percent")
    assert insight["value"] == 40.0

    matched = {m["recipient"]["id"] for m in analysis["matches"]}
    expected = [
        r["company_name"]
        for r in recipients
        if r["id"] in matched and not any(k in " ".join(r["processing_capability"]).lower() for k in ("dry", "dewater", "wash", "press"))
    ]
    assert sorted(insight["affected_recipients"]) == sorted(expected)


def test_dry_moisture_figure_is_recorded_without_a_flag():
    analysis = _build(moisture_percent=0.4)
    assert [i for i in analysis["completeness"]["insights"] if i["field"] == "moisture_percent"] == []


# ---------------------------------------------------------------------------
# physical state and intended use
# ---------------------------------------------------------------------------


def test_unknown_physical_state_says_so_instead_of_guessing():
    analysis = _build(physical_state="mixed")
    insight = next(i for i in analysis["completeness"]["insights"] if i["field"] == "physical_state")
    assert "not in the handling table" in insight["note"]
    assert insight["affected_recipients"] == []


def test_powder_state_is_checked_against_handling_capability():
    analysis = _build(physical_state="powder")
    insight = next(i for i in analysis["completeness"]["insights"] if i["field"] == "physical_state")
    assert insight["affects"].startswith("explanation only")
    assert insight["tone"] in {"info", "warn"}


def test_intended_use_is_compared_with_the_knowledge_base():
    aligned = _build(intended_use="brick and block manufacture")
    off = _build(intended_use="birdhouse timber cladding")

    aligned_note = next(i for i in aligned["completeness"]["insights"] if i["field"] == "intended_use")
    off_note = next(i for i in off["completeness"]["insights"] if i["field"] == "intended_use")
    assert aligned_note["tone"] == "info"
    assert off_note["tone"] == "warn"
    assert "ranking ignores it" in off_note["note"]


# ---------------------------------------------------------------------------
# the API surface
# ---------------------------------------------------------------------------


def test_analyze_endpoint_returns_completeness(client):
    payload = dict(FLY_ASH_REQUEST)
    payload.pop("composition")
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    completeness = response.json()["analysis"]["completeness"]
    assert completeness["percent"] < 100
    assert any(item["key"] == "composition" for item in completeness["missing"])
    assert "composition" in " ".join(completeness["advice"])


def test_moisture_is_validated_as_a_percentage(client):
    response = client.post("/api/analyze", json={**FLY_ASH_REQUEST, "moisture_percent": 140})
    assert response.status_code == 422


def test_stored_analysis_keeps_its_completeness(client):
    payload = dict(FLY_ASH_REQUEST, physical_state="powder")
    analysis_id = client.post("/api/analyze", json=payload).json()["analysis"]["id"]
    stored = client.get(f"/api/analyses/{analysis_id}").json()
    assert stored["completeness"]["fields"], "a stored analysis must stay auditable"
    assert [f["key"] for f in stored["completeness"]["fields"]] == [
        "material_description",
        "composition",
        "quantity",
        "location",
        "frequency",
        "physical_state",
        "moisture_percent",
        "contaminants",
        "intended_use",
    ]


def test_scenario_keeps_completeness_of_its_source(client):
    """A what-if re-scores the same picture; the completeness number describes that
    picture, so it may not silently reset to 'nothing supplied'."""
    payload = dict(FLY_ASH_REQUEST, moisture_percent=35.0)
    analysis_id = client.post("/api/analyze", json=payload).json()["analysis"]["id"]
    scenario = client.post("/api/scenario", json={"analysis_id": analysis_id, "quantity": 80}).json()
    assert scenario["scenario"]["completeness"]["percent"] == pytest.approx(
        client.get(f"/api/analyses/{analysis_id}").json()["completeness"]["percent"]
    )


def test_completeness_is_readable_on_its_own_route(client, fly_ash_analysis):
    """§3 on a route of its own, so a thin input can be reviewed without re-running
    the analysis (and without paying for another model call)."""
    body = client.get(f"/api/analyses/{fly_ash_analysis['id']}/completeness").json()
    assert body["percent"] == fly_ash_analysis["completeness"]["percent"]
    assert body["note"] == fly_ash_analysis["completeness"]["note"]
    assert body["blocks_analysis"] is False
    assert client.get("/api/analyses/an_nope/completeness").status_code == 404
