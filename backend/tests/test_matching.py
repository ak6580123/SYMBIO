"""Tests for the deterministic matching engine and the rule-based safety layer.

These are the guarantees the product promises: scores are reproducible, the
weighted sum is auditable, and hazardous or unidentified material is never
routed to a household, farm or artisan.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matching import engine  # noqa: E402
from knowledge_base import loader  # noqa: E402
from knowledge_base.materials import MATERIALS, MATERIALS_BY_ID  # noqa: E402


# ---------------------------------------------------------------------------
# Score arithmetic
# ---------------------------------------------------------------------------


def test_weights_sum_to_one():
    assert abs(sum(engine.WEIGHTS.values()) - 1.0) < 1e-9
    assert engine.WEIGHTS["compatibility"] == 0.30
    assert engine.WEIGHTS["quantity"] == 0.20
    assert engine.WEIGHTS["location"] == 0.15
    assert engine.WEIGHTS["sector"] == 0.15
    assert engine.WEIGHTS["value"] == 0.10
    assert engine.WEIGHTS["environmental"] == 0.10


def test_overall_score_equals_weighted_sum_of_components(fly_ash_analysis):
    for match in fly_ash_analysis["matches"]:
        b = match["breakdown"]
        expected = sum(b[k] * engine.WEIGHTS[k] for k in engine.WEIGHTS)
        # Components are stored to 3dp and the total to 1dp, so they can
        # legitimately differ by up to ~0.05; assert at that precision.
        assert abs(expected * 100 - match["overall_score"]) <= 0.06, match["recipient"]["company_name"]
        for key, value in b.items():
            if key != "weighted_total":
                assert 0.0 <= value <= 1.0, f"{key} out of range: {value}"


def test_matching_is_deterministic():
    """Same input twice must produce byte-identical scores."""
    from services import analysis as analysis_service
    from tests.conftest import FLY_ASH_REQUEST

    first = analysis_service.build_analysis(dict(FLY_ASH_REQUEST))
    second = analysis_service.build_analysis(dict(FLY_ASH_REQUEST))

    scores_a = [(m["recipient"]["id"], m["overall_score"]) for m in first["matches"]]
    scores_b = [(m["recipient"]["id"], m["overall_score"]) for m in second["matches"]]
    assert scores_a == scores_b


def test_results_are_sorted_descending(fly_ash_analysis):
    scores = [m["overall_score"] for m in fly_ash_analysis["matches"]]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Geometry and components
# ---------------------------------------------------------------------------


def test_haversine_known_distance():
    # Chennai Central -> Manali is roughly 13 km.
    km = engine.haversine_km(13.0827, 80.2707, 13.1667, 80.2667)
    assert 8.0 < km < 18.0


def test_haversine_zero_for_same_point():
    assert engine.haversine_km(13.08, 80.27, 13.08, 80.27) == 0.0


def test_quantity_score_peaks_inside_range():
    inside, _ = engine.quantity_score(5.0, 3.0, 20.0)
    below, _ = engine.quantity_score(0.5, 3.0, 20.0)
    above, _ = engine.quantity_score(500.0, 3.0, 20.0)
    assert inside > below
    assert inside > above
    assert 0.0 <= below <= 1.0 and 0.0 <= above <= 1.0


def test_location_score_decreases_with_distance():
    near, _ = engine.location_score(10.0)
    mid, _ = engine.location_score(120.0)
    far, _ = engine.location_score(400.0)
    assert near > mid > far
    assert far == 0.0


# ---------------------------------------------------------------------------
# Safety layer - the non-negotiable rules
# ---------------------------------------------------------------------------


def _recipient(recipient_id):
    rec = loader.get_recipient(recipient_id)
    assert rec is not None
    return rec


def test_hazardous_material_blocked_from_community_use():
    material = MATERIALS_BY_ID["spent_catalyst"]
    allowed, reuse_type, safety, _ = engine.safety_gate(
        material, {"confidence": 0.95}, "industry", _recipient("rec_comm_01")
    )
    assert allowed is False
    assert reuse_type == engine.ReuseType.RESTRICTED
    assert safety == engine.SafetyLevel.hazardous


def test_hazardous_material_allowed_for_licensed_recycler():
    material = MATERIALS_BY_ID["spent_catalyst"]
    allowed, reuse_type, _, _ = engine.safety_gate(
        material, {"confidence": 0.95}, "industry", _recipient("rec_metal_01")
    )
    assert allowed is True
    assert reuse_type == engine.ReuseType.INDUSTRIAL_ONLY


def test_ewaste_never_reaches_household_or_farm():
    material = MATERIALS_BY_ID["ewaste"]
    for recipient_id in ["rec_comm_02", "rec_farm_01", "rec_sme_01"]:
        allowed, _, _, _ = engine.safety_gate(
            material, {"confidence": 0.99}, "industry", _recipient(recipient_id)
        )
        assert allowed is False, recipient_id


def test_unknown_material_only_goes_to_licensed_processor():
    material = MATERIALS_BY_ID["unknown_material"]
    for rec in loader.get_recipients():
        allowed, reuse_type, _, _ = engine.safety_gate(material, {"confidence": 0.2}, "other", rec)
        if rec["sector"] == "waste_processor":
            assert allowed is True
            assert reuse_type == engine.ReuseType.UNKNOWN
        else:
            assert allowed is False, rec["company_name"]


def test_low_confidence_blocks_casual_sectors():
    material = MATERIALS_BY_ID["fly_ash"]
    allowed, _, _, _ = engine.safety_gate(
        material, {"confidence": 0.3}, "industry", _recipient("rec_comm_01")
    )
    assert allowed is False

    allowed_high, _, _, _ = engine.safety_gate(
        material, {"confidence": 0.9}, "industry", _recipient("rec_comm_01")
    )
    assert allowed_high is True


def test_no_casual_recipient_appears_in_any_analysis_of_a_hazardous_material():
    """End-to-end check through the real pipeline."""
    from services import analysis as analysis_service

    casual_sectors = {"community_programme", "agriculture_farm", "artisan_sme"}
    analysis = analysis_service.build_analysis(
        {
            "source_type": "industry",
            "material_description": "Spent hydroprocessing catalyst from our refinery hydrotreater unit",
            "quantity": 3.0,
            "unit": "tonnes",
            "location": "Chennai, Tamil Nadu",
            "frequency": "monthly",
            "composition": None,
        }
    )
    assert analysis["material"]["id"] == "spent_catalyst"
    for match in analysis["matches"]:
        assert match["recipient"]["sector"] not in casual_sectors
        assert match["safety_level"] in {"high", "hazardous"}


# ---------------------------------------------------------------------------
# Knowledge base integrity
# ---------------------------------------------------------------------------


def test_every_material_has_consistent_fields():
    for mat in MATERIALS:
        assert mat["safety_level"] in {"low", "moderate", "high", "hazardous", "unknown"}
        assert mat["default_reuse_type"] in {rt.value for rt in engine.ReuseType}
        for route in mat["reuse_categories"]:
            assert route in engine.REUSE_END_USE, f"{mat['id']}: unknown route {route}"
        for sector in mat["compatible_sectors"]:
            assert sector in engine.SECTOR_LABELS, f"{mat['id']}: unknown sector {sector}"


def test_every_recipient_references_known_materials():
    for rec in loader.get_recipients():
        for material_id in rec["accepted_materials"]:
            assert material_id in MATERIALS_BY_ID, f"{rec['id']}: unknown material {material_id}"
        assert rec["min_quantity_t_per_month"] <= rec["max_quantity_t_per_month"]
        assert rec["sector"] in engine.SECTOR_LABELS


def test_every_reuse_preference_maps_to_a_known_end_use():
    for sector, routes in engine.SECTOR_REUSE_PREFERENCE.items():
        assert sector in engine.SECTOR_LABELS, sector
        for route in routes:
            assert route in engine.REUSE_END_USE, f"{sector}: {route}"


def test_score_ceilings_are_derived_from_the_kb():
    prices = [m["typical_price_inr_per_tonne"] for m in MATERIALS if m["id"] != "unknown_material"]
    factors = [m["co2e_avoided_t_per_tonne"] for m in MATERIALS if m["id"] != "unknown_material"]
    assert engine.VALUE_SCORE_CEILING_INR in prices
    assert engine.ENV_SCORE_CEILING_TCO2E in factors
