"""Where each number shown to a user came from.

Two questions get answered here, both from the stored analysis and never from
the model:

* "Why did Symbio recommend this partner?"  -> `provenance_for`
* "What does Symbio actually know about this material?" -> `material_intelligence`

Every row states its origin from a fixed vocabulary, so a demo estimate can
never read like a measured fact, and every "evidence" check is recomputed from
the record in front of it rather than replayed from a template.
"""

from __future__ import annotations

from typing import Any

from ai.fallback import COMPOSITION_EVIDENCE
from knowledge_base.materials import MATERIALS_BY_ID
from models.schemas import plain
from matching.engine import (
    PROCESSING_BURDEN,
    SECTOR_LABELS,
    WEIGHTS,
    gate_rules_for,
    partner_type,
    sector_score,
)

# The origins the UI colour-codes. Kept short on purpose: a legend the user can read at
# a glance is more useful than a provenance standard.
ORIGINS = {
    "user": "USER PROVIDED",
    "knowledge_base": "KNOWLEDGE BASE",
    "recipient": "RECIPIENT PROFILE",
    "calculated": "CALCULATED",
    "estimate": "DEMO ESTIMATE",
    "ai": "AI INTERPRETATION",
    "external": "EXTERNAL SERVICE",
}

ORIGIN_NOTE = {
    "user": "Typed in or uploaded by you.",
    "knowledge_base": "Stored in backend/knowledge_base - demo-authored, not verified against a standard.",
    "recipient": "Recorded on the demo recipient profile.",
    "calculated": "Produced by the deterministic engine at analysis time.",
    "estimate": "A demo calculation. Not a quotation, invoice or laboratory result.",
    "ai": "The local model's reading of your wording, constrained to knowledge-base names.",
    "external": "Fetched from an outside service at the time shown. Symbio passes it through; it does not verify it.",
}


def annotate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the human tag and the one-line explanation to each row.

    Done here rather than in the frontend so that a provenance label can never be
    forgotten, reworded or invented by whichever screen renders it.
    """
    for row in rows:
        origin = row.get("origin")
        if origin in ORIGINS:
            row["origin_label"] = ORIGINS[origin]
            row["origin_note"] = ORIGIN_NOTE[origin]
    return rows


def _identification_origin(engine_name: str) -> str:
    """Which origin describes this identification run.

    'ollama:<model>' is an interpretation, 'fallback_keyword' is deterministic
    evidence matching, 'user_correction' is the user's own statement. Labelled
    honestly so a model guess is never shown as a calculation.
    """
    if str(engine_name).startswith("ollama"):
        return "ai"
    if str(engine_name) == "user_correction":
        return "user"
    return "calculated"


def provenance_for(analysis: dict[str, Any], match: dict[str, Any]) -> list[dict[str, Any]]:
    """Row per value behind one recommendation, with the origin of that value."""
    material = analysis["material"]
    source = analysis["source"]
    recipient = match["recipient"]
    identification = analysis["identification"]

    rows: list[dict[str, Any]] = [
        {
            "field": "Material identification",
            "value": f"{material['name']} · {identification['confidence'] * 100:.0f}% confidence",
            "origin": _identification_origin(identification.get("engine", "")),
            "detail": (
                f"Engine: {identification.get('engine', 'unknown')}. "
                f"{identification.get('reasoning') or ''}".strip()
            ),
        },
        {
            "field": "Waste description and quantity",
            "value": f"{source['quantity_t_per_month']} t/month from '{analysis['raw_description'][:60]}…'",
            "origin": "user",
            "detail": (
                f"Entered as {source['quantity_t_per_month']} t/month ({source['unit']}, "
                f"{source['frequency'].replace('_', ' ')}) after unit normalisation."
            ),
        },
    ]
    if analysis.get("composition_raw"):
        rows.append(
            {
                "field": "Reported composition",
                "value": analysis["composition_raw"][:90],
                "origin": "user",
                "detail": "Kept verbatim; used as evidence during identification, never edited.",
            }
        )
    if analysis.get("attached_filename"):
        rows.append(
            {
                "field": "Source document",
                "value": analysis["attached_filename"],
                "origin": "user",
                "detail": "Text extracted locally by the upload endpoint and reviewed before analysis.",
            }
        )

    rows += [
        {
            "field": "Materials this partner accepts",
            "value": ", ".join(recipient["accepted_materials"]) or "recorded by material family",
            "origin": "recipient",
            "detail": f"Also accepts these categories: {', '.join(recipient.get('accepted_categories') or []) or 'none recorded'}.",
        },
        {
            "field": "Quantity requirement",
            "value": f"{recipient['min_quantity_t_per_month']}-{recipient['max_quantity_t_per_month']} t/month",
            "origin": "recipient",
            "detail": f"This stream offers {match['available_quantity_t_per_month']} t/month; "
            f"{match['matched_quantity_t_per_month']} t/month fits this route.",
        },
        {
            "field": "Distance",
            "value": (
                f"{match['distance_km']} km"
                if match["distance_km"] is not None
                else "Not calculated"
            ),
            "origin": "calculated",
            "detail": (
                "Straight-line haversine between the source coordinates and the recipient coordinates."
                if match["distance_km"] is not None
                else "The stated location has no coordinates in Symbio's gazetteer, so no distance is measured - "
                "and no other city is used in its place."
            ),
        },
        {
            "field": "Match score",
            "value": f"{match['overall_score']}%",
            "origin": "calculated",
            "detail": "Weighted sum of six components: "
            + ", ".join(f"{k} {v:.2f}×{WEIGHTS[k]:.2f}" for k, v in match["breakdown"].items() if k in WEIGHTS),
        },
        {
            "field": "Safety classification and use category",
            "value": f"{plain(match['safety_level'])} risk · {plain(match['reuse_type']).replace('_', ' ').lower()}",
            "origin": "knowledge_base",
            "detail": "Material class comes from the knowledge base; the safety layer may tighten it for this "
            "recipient, and the effective values shown here are what it decided.",
        },
        {
            "field": "Reuse pathway",
            "value": " → ".join(match["reuse_pathway"]["steps"]),
            "origin": "knowledge_base",
            "detail": "End use is the knowledge-base route this recipient's sector performs; the sector itself is "
            "from the recipient profile.",
        },
        {
            "field": "Estimated economic value",
            "value": f"₹{match['estimated_value_inr_per_month']:,.0f}/month",
            "origin": "estimate",
            "detail": "Matched tonnes × the higher of the recipient's recorded price and the material's typical "
            "price. Demo figures, not a market rate.",
        },
        {
            "field": "Estimated CO₂e avoided",
            "value": f"{match['estimated_co2e_t_per_month']} t/month",
            "origin": "estimate",
            "detail": f"Matched tonnes × {material['co2e_avoided_t_per_tonne']} t CO₂e/t, the knowledge-base factor "
            "for this material. Not a certified lifecycle result.",
        },
        {
            "field": "Recipient record",
            "value": f"{recipient['company_name']} ({partner_type(recipient['sector'])})",
            "origin": "recipient",
            "detail": "Fictional demo company with plausible Chennai-area coordinates.",
        },
    ]

    if analysis.get("user_corrected"):
        rows.insert(
            1,
            {
                "field": "Material identity",
                "value": "Corrected by the user",
                "origin": "user",
                "detail": "The knowledge-base record for this material was used as stated; the model's guess was "
                "overridden for this analysis only.",
            },
        )

    route = match.get("route")
    if route:
        # Only ever appended when a route was actually fetched, so a build with no
        # external provider produces the same provenance rows it always did.
        rows.append(
            {
                "field": "Routing data",
                "value": (
                    f"{route['distance_km']} km by road, about {route['duration_minutes']} minutes"
                    if route.get("duration_minutes") is not None
                    else f"{route['distance_km']} km by road"
                ),
                "origin": "external",
                "detail": (
                    "External route calculation"
                    + (f", fetched {route['fetched_at']}" if route.get("fetched_at") else "")
                    + ". The distance above is the straight line between the two points, and the freight "
                    "estimate is calculated on that figure: switching routing provider cannot quietly reprice "
                    "a recommendation."
                ),
            }
        )
    return annotate(rows)


def _found_tokens(haystack: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle and needle.lower() in haystack]


def material_intelligence(analysis: dict[str, Any]) -> dict[str, Any]:
    """The material card: KB facts, plus the evidence the identifier used.

    Nothing here is generated. The sections restate the knowledge-base record;
    the evidence checks are recomputed against this analysis and report what
    actually matched, including when nothing did.
    """
    material = MATERIALS_BY_ID.get(analysis["material"]["id"], analysis["material"])
    identification = analysis["identification"]
    source = analysis["source"]
    description = (
        f"{analysis.get('raw_description', '')} {analysis.get('composition_raw') or ''} "
        f"{identification.get('reasoning') or ''}"
    ).lower()

    name_hits = _found_tokens(description, [material["name"], *material.get("aliases", [])])
    hint_hits = _found_tokens(description, material.get("keywords", []))
    composition = {k.lower(): v for k, v in (identification.get("composition") or {}).items()}
    pointing = sorted(
        {
            MATERIALS_BY_ID.get(candidate, {}).get("name", candidate)
            for key in composition
            for candidate, _weight in COMPOSITION_EVIDENCE.get(key, [])
        }
    )
    affinities = [
        sector_score(source["source_type"], sector, material["id"])[0]
        for sector in material["compatible_sectors"]
    ]
    burden = PROCESSING_BURDEN.get(str(identification.get("reuse_type") or material["default_reuse_type"]), 1)

    return {
        "material": {
            **analysis["material"],
            "aliases": material.get("aliases", []),
            "identification_hints": material.get("keywords", []),
            "gate_rules": gate_rules_for(material),
        },
        "identification": {
            "confidence": identification["confidence"],
            "engine": identification.get("engine"),
            "reasoning": identification.get("reasoning"),
            "uncertainty_note": identification.get("uncertainty_note"),
            "alternatives": identification.get("alternatives", []),
            "user_corrected": bool(analysis.get("user_corrected")),
        },
        "evidence": annotate([
            {
                "origin": "calculated",
                "check": "Material name or alias appears in what you wrote",
                "passed": bool(name_hits),
                "detail": (
                    "Matched: " + ", ".join(name_hits)
                    if name_hits
                    else "No name or alias was found in the description - the match rests on other evidence."
                ),
            },
            {
                "origin": "calculated",
                "check": "Description uses wording the knowledge base links to this material",
                "passed": bool(hint_hits),
                "detail": (
                    f"{len(hint_hits)} of {len(material.get('keywords', []))} knowledge-base markers found: "
                    + ", ".join(hint_hits[:8])
                    if hint_hits
                    else "None of this material's identification markers appear in the text."
                ),
            },
            {
                "origin": "calculated",
                "check": "Reported composition points at this material",
                "passed": material["name"] in pointing,
                "detail": (
                    ("Constituents recorded: " + ", ".join(f"{k} {v}" for k, v in composition.items()) + ". ")
                    if composition
                    else "No composition was stated, so nothing was checked against it. "
                )
                + (
                    "The composition markers in the knowledge base point at: "
                    + ", ".join(pointing)
                    + "."
                    if pointing
                    else "The knowledge base has no composition rule for this material, so composition was not "
                    "used to confirm the identity."
                ),
            },
            {
                "origin": "calculated",
                "check": "Your source sector feeds the sectors that use this material",
                "passed": bool(affinities) and max(affinities) >= 0.7,
                "detail": (
                    f"Strongest sector affinity {max(affinities) * 100:.0f}% "
                    f"(source type: {source['source_type'].replace('_', ' ')})."
                    if affinities
                    else "This material lists no compatible sectors in the knowledge base."
                ),
            },
            {
                "origin": "calculated",
                "check": "Handling burden expected before reuse",
                "passed": burden <= 1,
                "detail": (
                    material["default_reuse_type"].replace("_", " ").title()
                    + f" - processing {'is required' if material['requires_processing'] else 'is not required'} "
                    "according to the knowledge base."
                ),
            },
        ]),
        "sections": annotate([
            {"title": "What is it?", "kind": "text", "value": material["description"], "origin": "knowledge_base"},
            {"title": "Physical properties", "kind": "list", "value": material["properties"], "origin": "knowledge_base"},
            {
                "title": "Typical composition",
                "kind": "kv",
                "value": composition,
                "origin": "user",
                "empty": "No composition was provided with this analysis, and the knowledge base stores "
                "identification markers rather than fixed oxide ranges.",
            },
            {
                "title": "Potential applications",
                "kind": "list",
                "value": [str(v).replace("_", " ").title() for v in material["reuse_categories"]],
                "origin": "knowledge_base",
            },
            {
                "title": "Compatible sectors",
                "kind": "list",
                "value": [SECTOR_LABELS.get(s, s) for s in material["compatible_sectors"]],
                "origin": "knowledge_base",
            },
            {
                "title": "Processing requirements",
                "kind": "text",
                "value": (
                    "Processing required before reuse."
                    if material["requires_processing"]
                    else "No processing step recorded; direct reuse routes remain possible."
                )
                + f" Default classification: {material['default_reuse_type'].replace('_', ' ').lower()}.",
                "origin": "knowledge_base",
            },
            {
                "title": "Safety classification",
                "kind": "text",
                "value": f"{plain(material['safety_level']).title()} risk material.",
                "origin": "knowledge_base",
            },
            {
                "title": "Restrictions and routing rules",
                "kind": "list",
                "value": gate_rules_for(material),
                "origin": "calculated",
                "empty": "No additional gate rules apply to this record.",
            },
            {
                "title": "Environmental note",
                "kind": "text",
                "value": (
                    f"Knowledge-base factor: {material['co2e_avoided_t_per_tonne']} t CO2e avoided per tonne "
                    "diverted. Demo value - see the factors table on the Impact page."
                ),
                "origin": "estimate",
            },
            {
                "title": "Economic note",
                "kind": "text",
                "value": (
                    f"Knowledge-base typical price: ₹{material['typical_price_inr_per_tonne']:,.0f} per tonne. "
                    "Demo value; a recipient's own recorded price wins when it is higher."
                ),
                "origin": "estimate",
            },
            {
                "title": "Notes from the knowledge base",
                "kind": "text",
                "value": material.get("notes") or "",
                "origin": "knowledge_base",
            },
        ]),
        "verification": "demo",
        "origins": ORIGINS,
        "origin_notes": ORIGIN_NOTE,
    }
