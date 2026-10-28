"""§5/§7 - structured industry profiles, and the rule that they explain, never score."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROFILE_PATH = BACKEND / "data" / "sector_profiles.json"

ALL_STEPS = ["Supply", "Material demand", "Production capability", "Potential reuse product"]


@pytest.fixture(scope="module")
def profiles():
    from services import profiles

    return profiles


@pytest.fixture(scope="module")
def raw():
    return json.loads(PROFILE_PATH.read_text())["profiles"]


@pytest.fixture(scope="module")
def recipients():
    from knowledge_base import loader

    return loader.get_recipients()


# ---------------------------------------------------------------------------
# the seed file itself
# ---------------------------------------------------------------------------


def test_every_referenced_material_exists_in_the_knowledge_base(raw):
    """A profile that points at a material the KB does not have would silently invent a
    route. Null ids are allowed - they are the honest way of naming an unmodelled stream."""
    from knowledge_base.materials import MATERIALS_BY_ID

    unknown = []
    for sector, template in raw.items():
        for field in ("materials_required", "byproducts"):
            for item in template.get(field) or []:
                material_id = item.get("material_id")
                if material_id and material_id not in MATERIALS_BY_ID:
                    unknown.append(f"{sector}.{field}: {material_id}")
    assert not unknown, f"sector_profiles.json references materials that do not exist: {unknown}"


def test_every_sector_field_a_profile_reads_is_present_on_every_template(raw):
    for sector, template in raw.items():
        for field in ("label", "products", "materials_required", "byproducts", "certifications", "intake_note", "capability_summary"):
            assert field in template, f"{sector} is missing {field}"
        assert template["products"], f"{sector} has no products - the point of §7"


def test_templates_cover_every_partner_sector(profiles, recipients):
    covered = set(profiles.profiles())
    assert {r["sector"] for r in recipients} <= covered, "every partner should be described by a template"


GENERIC = {"products", "goods", "material", "materials", "output", "outputs", "waste", "recyclables"}


def test_products_are_specific_not_category_words(raw):
    """§7 is only worth having if the products are named. 'Recyclables' is not a product."""
    for sector, template in raw.items():
        assert template["products"], f"{sector} lists no products at all"
        for product in template["products"]:
            assert len(product) >= 6, f"{sector}: '{product}' is too vague to be a product"
            assert product.lower() not in GENERIC, f"{sector}: '{product}' is a category word"
        # and at least two of them, so a profile is not one line long
        assert len(template["products"]) >= 2, f"{sector}"


# ---------------------------------------------------------------------------
# the merge
# ---------------------------------------------------------------------------


def test_recipient_record_wins_over_the_template(profiles, recipients):
    recipient = next(r for r in recipients if r["id"] == "rec_cement_01")
    profile = profiles.for_recipient(recipient)
    recorded = set(recipient["accepted_materials"])
    merged = {row["material_id"] for row in profile["materials_required"]}
    assert recorded <= merged
    # exactly one row per material, however many sources describe it
    assert len(merged) == len(profile["materials_required"])
    for row in profile["materials_required"]:
        if row["material_id"] in recorded:
            assert "recipient record" in row["source"]


def test_template_lines_are_labelled_as_template(profiles, recipients):
    profile = profiles.for_recipient(recipients[0])
    assert profile["has_sector_template"] is True
    assert "sector template (demo)" in profile["profile_source"]
    for row in profile["byproducts"]:
        assert row["source"] == "sector template (demo)"


def test_chain_has_the_four_named_steps_in_order(profiles, recipients):
    profile = profiles.for_recipient(recipients[0])
    assert [step["step"] for step in profile["chain"]] == ALL_STEPS
    for step in profile["chain"]:
        assert step["origin"], "every step has to say where its content came from"


def test_products_and_certifications_are_carried_through(profiles, recipients):
    profile = profiles.for_recipient(recipients[0])
    assert profile["products"]
    assert profile["certifications"]
    assert profile["intake_note"]
    assert profile["capability"]["processing"] == next(r for r in recipients if r["id"] == profile["recipient_id"])["processing_capability"]


def test_demand_signals_are_min_maxes_of_the_records(profiles, recipients):
    from knowledge_base.materials import MATERIALS_BY_ID

    profile = profiles.for_recipient(recipients[0])
    for signal in profile["demand_signals"]:
        material = MATERIALS_BY_ID[signal["material_id"]]
        seekers = [r for r in recipients if signal["material_id"] in r["accepted_materials"]]
        assert signal["partners_seeking"] == len(seekers)
        prices = [r["estimated_price_inr_per_tonne"] for r in seekers]
        assert signal["price_range_inr_per_tonne"] == ([min(prices), max(prices)] if prices else None)


def test_unmodelled_streams_say_so_instead_of_guessing(profiles, recipients):
    cement = profiles.for_recipient(next(r for r in recipients if r["id"] == "rec_cement_01"))
    kiln_dust = next(b for b in cement["byproducts"] if b["material_id"] is None)
    assert kiln_dust["disposition"] == "handled on site; not modelled as an outbound stream"
    assert kiln_dust["potential_recipients"] == []


def test_product_end_reuses_the_engines_refusal(profiles):
    """A cement plant is not recorded as making board, so sawdust gets no product name -
    the same rule the pathway builder applies."""
    from matching.engine import REUSE_END_USE  # noqa: F401  (documents where the words come from)

    label, note = profiles._product_for("sawdust", {"sector": "cement_manufacturing"})
    assert label == "Assessed Material"
    assert "not recorded as performing" in note

    ash_label, _ = profiles._product_for("fly_ash", {"sector": "cement_manufacturing"})
    assert ash_label == REUSE_END_USE["cement_supplementary_material"]


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


def test_profile_index_reports_coverage(client, recipients):
    payload = client.get("/api/profiles").json()
    assert payload["count"] == len(payload["profiles"])
    assert payload["coverage"]["recipients_total"] == len(recipients)
    assert payload["coverage"]["recipients_with_template"] == len(recipients)
    assert payload["coverage"]["uncovered_sectors"] == []
    assert "sector_profiles.json" in payload["source"]


def test_single_profile_endpoint(client):
    payload = client.get("/api/profiles/rec_cement_01").json()
    assert payload["company_name"] == "Coromandel Cement Materials"
    assert [step["step"] for step in payload["chain"]] == ALL_STEPS
    assert payload["demo_data"] is True


def test_unknown_recipient_is_a_404(client):
    assert client.get("/api/profiles/rec_nobody").status_code == 404


def test_match_detail_gains_an_explanation_and_no_new_arithmetic(client, fly_ash_analysis):
    match = fly_ash_analysis["matches"][0]
    response = client.get(f"/api/matches/{fly_ash_analysis['id']}/{match['recipient']['id']}")
    assert response.status_code == 200
    body = response.json()
    note = body["industry_profile"]
    assert note["product"]
    assert note["origin"] in {"sector template (demo)", "recipient record only"}
    assert "accepted" in note["acceptance_note"] or "does not list" in note["acceptance_note"]
    # no numbers: the profile cannot move a score, a price or a tonnage
    assert not {"score", "overall_score", "value", "estimated_value_inr_per_month", "distance_km"} & set(note)
    assert body["match"]["overall_score"] == match["overall_score"]
