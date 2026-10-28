"""Symbio deterministic matching engine.

WHY THIS FILE EXISTS
--------------------
The LLM never scores a match. It only identifies the material and suggests
candidate reuse categories. Everything below is a pure function of:

    the material record from the knowledge base
    the recipient record from the knowledge base
    the source's quantity / location / sector
    the identification confidence

Score = compatibility*0.30 + quantity*0.20 + location*0.15
        + sector*0.15      + value*0.10    + environmental*0.10

Every component returns a value in [0, 1] and every match ships with the
plain-language reasons behind each component, so a judge can audit the ranking
by hand. Change WEIGHTS to re-tune; nothing else needs to move.
"""

from __future__ import annotations

import math
from typing import Any

from knowledge_base.materials import (
    CASUAL_SECTORS,
    MATERIALS_BY_ID,
    UNKNOWN_MATERIAL_ID,
    co2e_ceiling_t_per_tonne,
    price_ceiling_inr,
    primary_reuse_category,
)
from models.schemas import Match, Recipient, ReuseType, SafetyLevel, SourceSector

# ---------------------------------------------------------------------------
# Tunable constants (documented in the README)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "compatibility": 0.30,
    "quantity": 0.20,
    "location": 0.15,
    "sector": 0.15,
    "value": 0.10,
    "environmental": 0.10,
}

MAX_LOGISTICS_DISTANCE_KM = 300.0   # beyond this, location contributes ~0

# Score normalisation is derived from the knowledge base (90th percentile of the
# recorded prices and avoidance factors) rather than hardcoded, so adding a
# material cannot silently distort every other score.
VALUE_SCORE_CEILING_INR = price_ceiling_inr()
ENV_SCORE_CEILING_TCO2E = co2e_ceiling_t_per_tonne()

# How much a source sector naturally feeds each recipient sector.
# Only the relationships used by the demo data are listed; anything unlisted
# falls back to a neutral 0.45 so new sectors still work.
SECTOR_AFFINITY: dict[str, dict[str, float]] = {
    SourceSector.industry.value: {
        "cement_manufacturing": 1.0, "brick_manufacturing": 0.88, "ceramic_tile_manufacturing": 0.8,
        "ready_mix_concrete": 0.92, "construction_company": 0.8, "road_infrastructure": 0.9,
        "metal_recycler": 0.9, "ewaste_processor": 0.85, "waste_processor": 0.72,
        "energy_plant": 0.8, "adsorbent_manufacturer": 0.85, "glass_manufacturing": 0.8,
        "fertiliser_company": 0.7, "composting_facility": 0.6, "plastic_recycler": 0.75,
        "paper_recycler": 0.6, "furniture_manufacturer": 0.7, "biogas_plant": 0.6,
    },
    SourceSector.household.value: {
        "community_programme": 1.0, "paper_recycler": 0.9, "plastic_recycler": 0.9,
        "packaging_company": 0.85, "composting_facility": 0.9, "waste_processor": 0.8,
        "artisan_sme": 0.8, "metal_recycler": 0.7, "ewaste_processor": 0.7,
        "agriculture_farm": 0.6, "biogas_plant": 0.7, "glass_manufacturing": 0.6,
    },
    SourceSector.sme.value: {
        "artisan_sme": 1.0, "plastic_recycler": 0.9, "paper_recycler": 0.9,
        "furniture_manufacturer": 0.9, "packaging_company": 0.85, "composting_facility": 0.85,
        "waste_processor": 0.8, "energy_plant": 0.75, "metal_recycler": 0.75,
        "community_programme": 0.7, "biogas_plant": 0.7, "agriculture_farm": 0.7,
    },
    SourceSector.agriculture.value: {
        "composting_facility": 0.9, "biogas_plant": 0.95, "agriculture_farm": 0.85,
        "energy_plant": 0.85, "cement_manufacturing": 0.8, "adsorbent_manufacturer": 0.75,
        "waste_processor": 0.7, "fertiliser_company": 0.8,
    },
    SourceSector.other.value: {
        "waste_processor": 1.0, "composting_facility": 0.6, "plastic_recycler": 0.6,
        "paper_recycler": 0.6, "metal_recycler": 0.6,
    },
}

# Human labels for the UI (so the API does not leak raw snake_case everywhere).
SECTOR_LABELS = {
    "cement_manufacturing": "Cement Manufacturing",
    "brick_manufacturing": "Brick & Block Manufacturing",
    "ceramic_tile_manufacturing": "Ceramic & Tile Manufacturing",
    "glass_manufacturing": "Glass Manufacturing",
    "construction_company": "Construction",
    "ready_mix_concrete": "Ready-Mix Concrete",
    "road_infrastructure": "Road Infrastructure",
    "fertiliser_company": "Fertiliser",
    "composting_facility": "Composting",
    "biogas_plant": "Biogas / Energy from Organics",
    "agriculture_farm": "Agriculture",
    "plastic_recycler": "Plastic Recycling",
    "paper_recycler": "Paper Recycling",
    "packaging_company": "Packaging",
    "metal_recycler": "Metal Recycling",
    "ewaste_processor": "E-Waste Processing",
    "furniture_manufacturer": "Furniture & Panels",
    "waste_processor": "Waste Processing",
    "community_programme": "Community Programme",
    "artisan_sme": "Artisan / SME",
    "energy_plant": "Energy Plant",
    "adsorbent_manufacturer": "Adsorbent Manufacturing",
}

# What kind of reuse partner a sector represents. Deliberately not "buyer":
# a cement plant, an artisan collective and a community programme are all
# recipients, but they accept material for different reasons and on different
# terms, and the demo has to show Industry->Industry, ->SME, ->Recycler,
# ->Agriculture and ->Community flows as distinct routes.
PARTNER_TYPE_LABELS = {
    "industry": "Industry",
    "sme": "SME / Artisan",
    "recycler": "Recycler",
    "processing": "Processing Partner",
    "agriculture": "Agriculture",
    "community": "Community / Household",
}

SECTOR_PARTNER_TYPE = {
    "cement_manufacturing": "industry",
    "brick_manufacturing": "industry",
    "ceramic_tile_manufacturing": "industry",
    "glass_manufacturing": "industry",
    "ready_mix_concrete": "industry",
    "road_infrastructure": "industry",
    "furniture_manufacturer": "industry",
    "adsorbent_manufacturer": "industry",
    "packaging_company": "industry",
    "energy_plant": "industry",
    "fertiliser_company": "industry",
    "construction_company": "industry",
    "artisan_sme": "sme",
    "plastic_recycler": "recycler",
    "paper_recycler": "recycler",
    "metal_recycler": "recycler",
    "ewaste_processor": "recycler",
    "waste_processor": "processing",
    "composting_facility": "processing",
    "biogas_plant": "processing",
    "agriculture_farm": "agriculture",
    "community_programme": "community",
}


def partner_type(sector: str) -> str:
    """Deterministic partner category for a recipient sector.

    Unknown sectors fall back to `industry` rather than being dropped, so adding
    a sector to the knowledge base can never silently disappear from a filter.
    """
    return SECTOR_PARTNER_TYPE.get(sector, "industry")


def summary_sentence(
    *,
    overall: float,
    company_name: str,
    material_name: str,
    minimum: float,
    maximum: float,
    available: float,
    distance_km: float | None,
    requires_processing: bool,
    processing_capability: list[str],
    reuse_type: ReuseType,
) -> str:
    """One plain-language sentence explaining the ranking, from computed values.

    A score on its own is not an explanation, and a hand-written justification
    would drift from the numbers. Every figure below is the same one the score
    was calculated from.
    """
    if overall >= 75:
        tone = "Strong match"
    elif overall >= 60:
        tone = "Good match"
    elif overall >= 45:
        tone = "Possible match"
    else:
        tone = "Marginal match"

    if distance_km is None:
        haul = "at a distance Symbio could not calculate from the location stated"
    else:
        haul = f"is {distance_km} km away"
    parts = [
        f"{tone}: {company_name} accepts {material_name}, works with {minimum:g}-{maximum:g} t/month "
        f"(this stream is {available:g} t/month) and {haul}"
    ]

    if requires_processing:
        if processing_capability:
            capability = processing_capability[0].replace("_", " ")
            parts.append(f"it lists {capability} capability on site")
        else:
            parts.append("no processing capability is recorded for it, so material must arrive prepared")

    if reuse_type == ReuseType.INDUSTRIAL_ONLY:
        parts.append("industrial handling only - not for casual or household use")
    elif reuse_type == ReuseType.RESTRICTED:
        parts.append("restricted stream: licensed handlers only")
    elif reuse_type == ReuseType.UNKNOWN:
        parts.append("assessment route only, since the material is not yet identified")
    elif reuse_type == ReuseType.DIRECT_REUSE:
        parts.append("usable without further processing")

    return ", ".join(parts) + "."



# Ordering of safety levels, lowest risk first. The safety layer *gates* routes
# with sets (see safety_gate); this ordering exists only so "what is the safest
# option?" can rank answers without inventing a new judgement. `unknown` ranks
# worst: not knowing a material's hazard is worse than knowing it is hazardous.
SAFETY_RANK = {"low": 0, "moderate": 1, "high": 2, "hazardous": 3, "unknown": 4}

# How much handling a route demands, lightest first. Used by the "least
# processing" optimisation mode and by the pathway grouping - never by the
# canonical score, whose weights are untouched. UNKNOWN sits above
# industrial-only because an unresolved stream is the heaviest burden there is:
# it has to be tested before anything else can be decided.
PROCESSING_BURDEN = {
    "DIRECT_REUSE": 0,
    "REQUIRES_PROCESSING": 1,
    "INDUSTRIAL_ONLY": 2,
    "UNKNOWN": 3,
    "RESTRICTED": 4,
}


def processing_burden(reuse_type: object) -> int:
    """Rank of a reuse classification by handling burden (unknown values last)."""
    return PROCESSING_BURDEN.get(str(getattr(reuse_type, "value", reuse_type)), 9)

# Final product of each reuse route - used to draw the reuse pathway.
REUSE_END_USE = {
    "cement_supplementary_material": "Blended Cement / Concrete",
    "brick_and_block_making": "Bricks & Blocks",
    "aggregate_substitute": "Recycled Aggregate",
    "road_and_embankment_fill": "Road Sub-base / Embankment",
    "soil_amendment": "Soil Amendment",
    "compost_feedstock": "Compost",
    "animal_feed": "Treated Feed Input",
    "energy_recovery": "Recovered Energy",
    "fibre_pulping": "Recycled Paper & Board",
    "packaging_material": "New Packaging",
    "polymer_reprocessing": "Recycled Polymer Pellets",
    "metal_recovery": "Recovered Metal",
    "ceramic_and_tile_body": "Ceramic & Tile Body",
    "glass_batch_cullet": "New Glass Products",
    "adsorbent_water_treatment": "Water-Treatment Adsorbent",
    "fertiliser_raw_material": "Fertiliser Input",
    "panel_and_board_making": "Panels & Boards",
    "textile_shoddy": "Recycled Fibre Products",
    "precious_metal_recovery": "Recovered Precious Metals",
}

SOURCE_SECTOR_LABEL = {
    SourceSector.industry.value: "Industrial Waste",
    SourceSector.household.value: "Household / Community Waste",
    SourceSector.sme.value: "SME Waste",
    SourceSector.agriculture.value: "Agricultural Residue",
    SourceSector.other.value: "Waste Stream",
}

# Which reuse application each recipient sector is actually after, in priority
# order. Used to pick the correct end-product for the reuse pathway diagram.
SECTOR_REUSE_PREFERENCE: dict[str, list[str]] = {
    "cement_manufacturing": ["cement_supplementary_material"],
    "ready_mix_concrete": ["cement_supplementary_material", "aggregate_substitute"],
    "brick_manufacturing": ["brick_and_block_making", "aggregate_substitute"],
    "ceramic_tile_manufacturing": ["ceramic_and_tile_body", "aggregate_substitute"],
    "glass_manufacturing": ["glass_batch_cullet"],
    "construction_company": ["aggregate_substitute", "road_and_embankment_fill"],
    "road_infrastructure": ["road_and_embankment_fill", "aggregate_substitute"],
    "fertiliser_company": ["fertiliser_raw_material", "soil_amendment"],
    "composting_facility": ["compost_feedstock"],
    "biogas_plant": ["energy_recovery"],
    "agriculture_farm": ["soil_amendment", "compost_feedstock"],
    "plastic_recycler": ["polymer_reprocessing"],
    "paper_recycler": ["fibre_pulping"],
    "packaging_company": ["packaging_material"],
    "metal_recycler": ["metal_recovery"],
    "ewaste_processor": ["precious_metal_recovery", "metal_recovery"],
    "furniture_manufacturer": ["panel_and_board_making"],
    "energy_plant": ["energy_recovery"],
    "adsorbent_manufacturer": ["adsorbent_water_treatment"],
    "artisan_sme": ["textile_shoddy", "packaging_material", "panel_and_board_making"],
    "community_programme": ["compost_feedstock", "fibre_pulping"],
    "waste_processor": ["aggregate_substitute", "polymer_reprocessing", "metal_recovery", "fibre_pulping"],
}


def choose_reuse_category(material: dict, reuse_categories: list[str], recipient_sector: str) -> str | None:
    """Pick the reuse application this recipient is genuinely interested in."""
    candidates = [r for r in reuse_categories if r in REUSE_END_USE]
    if not candidates:
        candidates = [r for r in material["reuse_categories"] if r in REUSE_END_USE]
    if not candidates:
        return None
    preferred = SECTOR_REUSE_PREFERENCE.get(recipient_sector)
    if preferred is None:
        # A sector the knowledge base has no preference list for: fall back to the
        # material's own primary route rather than pretending to know the partner.
        return candidates[0]
    for pref in preferred:
        if pref in candidates:
            return pref
    # This partner's sector performs none of the reuse applications recorded for
    # this material. Saying so is better than borrowing another sector's product -
    # a cement plant must not be shown making particle board because the material
    # happens to list that route. The pathway then reads "Assessed Material".
    return None


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km. Straight-line, so the UI labels it as such."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)), 1)


# ---------------------------------------------------------------------------
# Score components - each returns (score 0..1, reason or None)
# ---------------------------------------------------------------------------


def compatibility_score(
    material: dict, identification: dict, recipient: dict
) -> tuple[float, str | None]:
    exact = material["id"] in recipient["accepted_materials"]
    by_family = material["category"] in recipient.get("accepted_categories", [])

    # An unidentified stream cannot be "compatible" with anything - but a
    # licensed processor can still take it for assessment. Give that a flat,
    # clearly-labelled partial score rather than dropping the route entirely.
    if not exact and not by_family and material["id"] == UNKNOWN_MATERIAL_ID:
        if recipient["sector"] == "waste_processor":
            return (
                0.45,
                "Material is unidentified, so this recipient is offered an assessment route only",
            )
        return 0.0, None

    reuse = material["reuse_categories"]
    offered = [r for r in reuse if r in REUSE_END_USE]
    overlap = 1.0 if not offered else (1.0 if offered else 0.0)

    if exact:
        base = 0.85 + 0.15 * overlap
        reason = f"Recipient explicitly accepts {material['name']}"
    elif by_family:
        base = 0.55 + 0.10 * overlap
        reason = f"Recipient accepts the {material['category'].replace('_', ' ')} family, which includes this material"
    else:
        base = 0.0
        reason = None

    confidence = float(identification.get("confidence", 0.5))
    score = base * (0.65 + 0.35 * confidence)

    if score > 0 and confidence < 0.5:
        reason = f"{reason}, but identification confidence is low ({confidence:.0%})"
    return min(1.0, score), reason


def quantity_score(available: float, minimum: float, maximum: float) -> tuple[float, str | None]:
    if available < minimum:
        if minimum <= 0:
            return 0.9, "No minimum quantity required"
        score = max(0.0, 0.55 * (available / minimum))
        return score, f"Available quantity is below the recipient's {minimum:g} t/month minimum (partial loads may still be accepted)"
    if available > maximum:
        score = max(0.35, 1.0 - 0.4 * ((available - maximum) / maximum))
        return min(1.0, score), f"Supply exceeds this recipient's {maximum:g} t/month capacity - consider splitting the load"
    span = max(maximum - minimum, 1e-6)
    position = (available - minimum) / span
    score = 0.80 + 0.20 * math.sin(math.pi * position)
    return min(1.0, score), f"Available {available:g} t/month sits inside the recipient's {minimum:g}-{maximum:g} t/month range"


def location_score(distance_km: float | None) -> tuple[float, str | None]:
    """Distance component, or a stated abstention.

    A missing coordinate set scores a flat neutral value for *every* partner, with a
    reason that says so. That is deliberately not 0 and not 1: a neutral 0.5 leaves
    the other five components to decide the order, so nobody gains or loses ground
    because the sender's town is not in the gazetteer. The weights themselves are
    untouched.
    """
    if distance_km is None:
        return 0.5, (
            "No coordinates are available for the stated location, so distance is not scored - "
            "every partner is neutral on this component"
        )
    score = max(0.0, 1.0 - (distance_km / MAX_LOGISTICS_DISTANCE_KM) ** 1.2)
    if distance_km <= 25:
        reason = f"Very short haul ({distance_km:g} km) keeps transport cost and emissions low"
    elif distance_km <= 100:
        reason = f"Regional haul ({distance_km:g} km), economically practical"
    else:
        reason = f"Long haul ({distance_km:g} km) erodes the value of this match"
    return min(1.0, max(0.0, score)), reason


def sector_score(
    source_sector: str, recipient_sector: str, material_id: str | None = None
) -> tuple[float, str | None]:
    """How well this recipient sector suits this source *and this material*.

    A recipient whose preferred route IS the material's primary route in the
    knowledge base scores 1.0 - that is why fly ash ranks cement above brick
    even when the brick works is marginally closer.
    """
    table = SECTOR_AFFINITY.get(source_sector, {})
    score = table.get(recipient_sector, 0.45)
    label = SECTOR_LABELS.get(recipient_sector, recipient_sector.replace("_", " "))
    src_label = SOURCE_SECTOR_LABEL.get(source_sector, source_sector.title())

    preferred = SECTOR_REUSE_PREFERENCE.get(recipient_sector, [])
    primary = primary_reuse_category(material_id or "")
    if primary and primary in preferred:
        score = max(score, 1.0)
        # Only the sector whose route IS the primary one gets the "primary"
        # label - ready-mix concrete shares the route but is not the canonical one.
        if primary in preferred[:1]:
            return score, f"{label} is the primary recorded reuse route for this material"
        return score, f"{label} shares the primary recorded reuse route for this material"

    if score >= 0.85:
        return score, f"{src_label} streams routinely supply {label}"
    if score >= 0.6:
        return score, f"{label} is a plausible destination for {src_label.lower()}"
    return score, None


def value_score(price_inr_per_tonne: float, material_price: float) -> tuple[float, str | None]:
    price = max(price_inr_per_tonne, material_price)
    score = min(1.0, price / VALUE_SCORE_CEILING_INR)
    if score <= 0:
        return 0.0, "No market price recorded for this material (demo value = 0)"
    if score >= 0.5:
        return score, f"High-value stream at an estimated ₹{price:,.0f}/tonne (demo value)"
    return score, f"Lower unit value at an estimated ₹{price:,.0f}/tonne (demo value)"


def environmental_score(co2e_factor: float) -> tuple[float, str | None]:
    score = min(1.0, co2e_factor / ENV_SCORE_CEILING_TCO2E)
    if score <= 0:
        return 0.0, "No emission-avoidance factor recorded for this material"
    if score >= 0.6:
        return score, f"High avoidance potential (~{co2e_factor:.2f} t CO2e per tonne reused, demo factor)"
    return score, f"Moderate avoidance potential (~{co2e_factor:.2f} t CO2e per tonne reused, demo factor)"


# ---------------------------------------------------------------------------
# Rule-based safety layer (MVP, not a regulatory compliance engine)
# ---------------------------------------------------------------------------


def safety_gate(
    material: dict,
    identification: dict,
    source_sector: str,
    recipient: dict,
) -> tuple[bool, ReuseType, SafetyLevel, list[str]]:
    """Decide whether a route is allowed and how it must be classified.

    Returns (allowed, reuse_type, effective_safety_level, cautions).
    """
    cautions: list[str] = []
    kb_safety = material["safety_level"]
    recipient_sector = recipient["sector"]
    casual = recipient_sector in CASUAL_SECTORS
    confidence = float(identification.get("confidence", 0.5))

    # 1. Hazardous streams only go to recipients that handle hazardous material.
    if kb_safety == "hazardous":
        if "licensed_handling" not in recipient.get("processing_capability", []):
            return False, ReuseType.RESTRICTED, SafetyLevel.hazardous, [
                f"{material['name']} is a hazardous stream and this recipient has no licensed handling capability"
            ]
        cautions.append("Hazardous stream: authorised recycler only, with full chain-of-custody paperwork.")

    # 2. Never recommend industrial-only or high-hazard material to casual users.
    if casual and kb_safety in {"high", "hazardous"}:
        return False, ReuseType.RESTRICTED, SafetyLevel(kb_safety), [
            f"{material['name']} is classified {kb_safety}-risk and is not suitable for "
            f"{SECTOR_LABELS.get(recipient_sector, recipient_sector).lower()} use"
        ]

    # 3. Unknown material: only a licensed waste processor may take it, and only
    #    for assessment - never a farm, household programme or artisan.
    if material["id"] == UNKNOWN_MATERIAL_ID:
        if recipient_sector != "waste_processor":
            return False, ReuseType.UNKNOWN, SafetyLevel.unknown, [
                "Material is unidentified, so no reuse route other than licensed assessment is offered"
            ]
        cautions.append("Unidentified material: route is for assessment and testing only, not for reuse.")
        return True, ReuseType.UNKNOWN, SafetyLevel.unknown, cautions

    if casual and kb_safety == "moderate":
        cautions.append(
            "Moderate-risk material for a non-industrial recipient: handling controls and a "
            "contamination check are required before use."
        )

    # 4. Low confidence must not silently become a casual-use recommendation.
    if confidence < 0.5 and casual:
        return False, ReuseType.UNKNOWN, SafetyLevel.unknown, [
            f"Identification confidence is too low ({confidence:.0%}) to recommend this material for "
            f"{SECTOR_LABELS.get(recipient_sector, recipient_sector).lower()} use"
        ]
    if confidence < 0.5:
        cautions.append(f"Identification confidence is {confidence:.0%}; verify the material before committing.")

    # 5. Resolve the reuse classification.
    reuse_type = _resolve_reuse_type(material, recipient, casual)
    if material["requires_processing"] and reuse_type == ReuseType.DIRECT_REUSE:
        cautions.append("Knowledge base expects processing before this material is used.")

    if material["requires_processing"]:
        cautions.append(
            f"Required handling: {', '.join(material['properties'][:3])}. "
            f"Recipient capability: {', '.join(recipient.get('processing_capability', [])[:3])}."
        )

    return True, reuse_type, SafetyLevel(kb_safety), cautions


def gate_rules_for(material: dict) -> list[str]:
    """The safety-gate rules that will apply to this material, as plain text.

    Written from the same record fields `safety_gate()` reads, in the same order,
    so the knowledge-base page can show what the rules do without a second copy
    of them that could drift. Nothing here is material-specific advice the
    knowledge base does not already hold.
    """
    safety = material["safety_level"]
    rules = [
        "Confidence below 50% blocks a casual-use recommendation and adds a verify-before-committing caution.",
    ]
    if material["id"] == UNKNOWN_MATERIAL_ID:
        rules.insert(0, "Unidentified material: only a licensed waste processor is offered, for assessment and testing, never for reuse.")
    if safety == "hazardous":
        rules.insert(0, "Hazardous stream: matched only with licensed handling capability, and with chain-of-custody paperwork.")
    if safety in {"high", "hazardous"}:
        rules.insert(1, "Never offered to community, farm or artisan recipients, however well the rest of the match scores.")
    if safety == "moderate":
        rules.append("Moderate risk reaching a non-industrial recipient: handling controls and a contamination check are required first.")
    if material["requires_processing"]:
        rules.append("Expects processing before use: a direct-reuse route is still flagged with that caution.")
    if material["default_reuse_type"] == ReuseType.RESTRICTED.value:
        rules.append(
            "Default classification is RESTRICTED: only a recipient holding licensed handling capability is upgraded "
            "to an industrial-use route; every other route keeps the restricted label."
        )
    elif material["default_reuse_type"] == ReuseType.INDUSTRIAL_ONLY.value:
        rules.append(
            "Default classification is INDUSTRIAL_ONLY: matched routes are labelled for industrial use and never as "
            "direct reuse."
        )
    return rules


def _resolve_reuse_type(material: dict, recipient: dict, casual: bool) -> ReuseType:
    try:
        declared = ReuseType(recipient["reuse_type"])
    except ValueError:
        declared = ReuseType.UNKNOWN

    default = ReuseType(material["default_reuse_type"])

    if declared == ReuseType.INDUSTRIAL_ONLY or default == ReuseType.INDUSTRIAL_ONLY:
        return ReuseType.INDUSTRIAL_ONLY
    if declared == ReuseType.RESTRICTED or default == ReuseType.RESTRICTED:
        # A recipient that demonstrably holds a licence for the stream may take
        # it under industrial controls. Everyone else was already refused by
        # safety_gate() before reaching here, so RESTRICTED is the safe default.
        if "licensed_handling" in recipient.get("processing_capability", []):
            return ReuseType.INDUSTRIAL_ONLY
        return ReuseType.RESTRICTED

    if casual and material["requires_processing"]:
        return ReuseType.REQUIRES_PROCESSING
    return declared if declared != ReuseType.UNKNOWN else default


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def find_matches(
    *,
    analysis_id: str,
    material: dict,
    identification: dict,
    source: dict,
    candidates: list[dict],
) -> tuple[list[Match], list[dict]]:
    """Score every candidate recipient against the source.

    Returns (ranked matches, excluded records with the reason they were dropped).
    """
    available = float(source["quantity_t_per_month"])
    matches: list[Match] = []
    excluded: list[dict] = []

    for candidate in candidates:
        recipient = Recipient(**candidate)
        allowed, reuse_type, safety, cautions = safety_gate(material, identification, source["source_type"], candidate)

        if not allowed:
            excluded.append(
                {
                    "recipient_id": recipient.id,
                    "company_name": recipient.company_name,
                    "sector": recipient.sector,
                    "reuse_type": reuse_type.value,
                    "reason": cautions[0] if cautions else "Blocked by the safety layer",
                }
            )
            continue

        # No coordinates means no distance - not a distance measured from elsewhere.
        if source.get("latitude") is None or source.get("longitude") is None:
            distance: float | None = None
        else:
            distance = haversine_km(
                float(source["latitude"]), float(source["longitude"]),
                recipient.latitude, recipient.longitude,
            )

        components: dict[str, float] = {}
        reasons: list[str] = []

        comp, comp_reason = compatibility_score(material, identification, candidate)
        if comp <= 0.001:
            excluded.append(
                {
                    "recipient_id": recipient.id,
                    "company_name": recipient.company_name,
                    "sector": recipient.sector,
                    "reuse_type": reuse_type.value,
                    "reason": f"Does not accept {material['name']} or its material family",
                }
            )
            continue
        components["compatibility"] = comp
        if comp_reason:
            reasons.append(comp_reason)

        qty, qty_reason = quantity_score(available, recipient.min_quantity_t_per_month, recipient.max_quantity_t_per_month)
        components["quantity"] = qty
        if qty_reason:
            reasons.append(qty_reason)

        loc, loc_reason = location_score(distance)
        components["location"] = loc
        if loc_reason:
            reasons.append(loc_reason)

        sec, sec_reason = sector_score(source["source_type"], recipient.sector, material["id"])
        components["sector"] = sec
        if sec_reason:
            reasons.append(sec_reason)

        val, val_reason = value_score(recipient.estimated_price_inr_per_tonne, material["typical_price_inr_per_tonne"])
        components["value"] = val
        if val_reason:
            reasons.append(val_reason)

        env, env_reason = environmental_score(material["co2e_avoided_t_per_tonne"])
        components["environmental"] = env
        if env_reason:
            reasons.append(env_reason)

        total = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
        overall = round(total * 100, 1)

        matched_qty = min(available, recipient.max_quantity_t_per_month)
        price = max(recipient.estimated_price_inr_per_tonne, material["typical_price_inr_per_tonne"])
        if material["id"] == UNKNOWN_MATERIAL_ID:
            # An unidentified stream is sent for assessment, not sold for reuse, so
            # no value can be claimed for it - and no tonnage of "whatever this is"
            # should ever appear as revenue. The recipient's price still informs the
            # ranking, which only orders partners against each other.
            price = 0.0

        reuse_cat = choose_reuse_category(
            material,
            identification.get("reuse_categories") or material["reuse_categories"],
            recipient.sector,
        )
        end_use = REUSE_END_USE[reuse_cat] if reuse_cat else "Assessed Material"
        if reuse_cat is None:
            cautions.append(
                "No reuse application is recorded for "
                f"{SECTOR_LABELS.get(recipient.sector, recipient.sector).lower()} with this material: this route is a "
                "material-family match, not a product this partner is listed as making."
            )

        matches.append(
            Match(
                id=f"{analysis_id}:{recipient.id}",
                analysis_id=analysis_id,
                recipient=recipient,
                overall_score=overall,
                breakdown={
                    **{k: round(v, 3) for k, v in components.items()},
                    "weighted_total": round(total, 4),
                },  # type: ignore[arg-type]
                reuse_type=reuse_type,
                safety_level=safety,
                reasons=reasons,
                cautions=cautions,
                distance_km=distance,
                matched_quantity_t_per_month=round(matched_qty, 2),
                required_quantity_range_t_per_month=[
                    recipient.min_quantity_t_per_month,
                    recipient.max_quantity_t_per_month,
                ],
                available_quantity_t_per_month=available,
                estimated_value_inr_per_month=round(matched_qty * price, 2),
                estimated_co2e_t_per_month=round(matched_qty * material["co2e_avoided_t_per_tonne"], 3),
                summary=summary_sentence(
                    overall=overall,
                    company_name=recipient.company_name,
                    material_name=material["name"],
                    minimum=recipient.min_quantity_t_per_month,
                    maximum=recipient.max_quantity_t_per_month,
                    available=available,
                    distance_km=distance,
                    requires_processing=bool(material["requires_processing"])
                    or reuse_type == ReuseType.REQUIRES_PROCESSING,
                    processing_capability=list(recipient.processing_capability),
                    reuse_type=reuse_type,
                ),
                reuse_pathway={
                    "steps": _pathway(source, material, reuse_type, recipient, end_use)
                },  # type: ignore[arg-type]
                demo_data=True,
            )
        )

    # Unranked-by-distance routes sort last rather than as if they were 0 km away.
    matches.sort(
        key=lambda m: (-m.overall_score, m.distance_km is None, m.distance_km or 0.0, m.recipient.id)
    )
    return matches, excluded


def _pathway(source: dict, material: dict, reuse_type: ReuseType, recipient: Recipient, end_use: str) -> list[str]:
    steps = [
        SOURCE_SECTOR_LABEL.get(source["source_type"], "Waste Source"),
        material["name"],
        "Processing" if reuse_type in (ReuseType.REQUIRES_PROCESSING, ReuseType.INDUSTRIAL_ONLY) else "Direct Use",
        SECTOR_LABELS.get(recipient.sector, recipient.sector),
        end_use,
    ]
    return steps


# ---------------------------------------------------------------------------
# Impact allocation
# ---------------------------------------------------------------------------


def allocate_impact(matches: list[Match], available_t_per_month: float) -> list[Match]:
    """Split the source's available tonnage across the ranked matches.

    Naive per-match impact would let 5 tonnes be "diverted" ten times over, so
    dashboard totals are computed from this allocation instead: greedy in score
    order, best match filled first, the rest share what is left.

    This does NOT overwrite the per-route figures. Every match keeps its own
    standalone quantity, value and CO2e (what that route would deliver if it ran
    on its own); only `allocated_t_per_month` reflects the shared-budget view.
    """
    remaining = available_t_per_month
    for match in matches:
        take = max(0.0, min(match.matched_quantity_t_per_month, remaining))
        remaining = max(0.0, remaining - take)
        match.allocated_t_per_month = round(take, 2)
        if take <= 0:
            match.cautions.append(
                "No tonnage left to allocate at the current source volume once higher-ranked routes are "
                "filled. This route becomes viable if supply increases or the load is split."
            )
    return matches


def unit_value_inr_per_tonne(match: Match) -> float:
    if match.matched_quantity_t_per_month <= 0:
        return 0.0
    return match.estimated_value_inr_per_month / match.matched_quantity_t_per_month


def totals_for(matches: list[Match], available_t_per_month: float, material: dict) -> dict:
    factor = material["co2e_avoided_t_per_tonne"]
    diverted = round(sum(m.allocated_t_per_month for m in matches), 2)
    value = round(sum(m.allocated_t_per_month * unit_value_inr_per_tonne(m) for m in matches), 2)
    co2e = round(diverted * factor, 3)
    return {
        "available_t_per_month": available_t_per_month,
        "allocated_t_per_month": diverted,
        "unallocated_t_per_month": round(max(0.0, available_t_per_month - diverted), 2),
        "potential_matches": len(matches),
        "viable_matches": len([m for m in matches if m.allocated_t_per_month > 0]),
        "estimated_value_inr_per_month": value,
        "estimated_value_inr_per_year": round(value * 12, 2),
        "estimated_co2e_avoided_t_per_month": co2e,
        "estimated_co2e_avoided_t_per_year": round(co2e * 12, 3),
        "diversion_rate": round(diverted / available_t_per_month, 3) if available_t_per_month else 0.0,
        "co2e_factor_used_t_per_tonne": factor,
        "label": "Estimated impact - demo calculation",
    }


def material_record(material: dict) -> dict:
    """Shape a KB material dict for the API."""
    return {k: v for k, v in MATERIALS_BY_ID[material["id"]].items() if k not in {"keywords", "aliases"}}
