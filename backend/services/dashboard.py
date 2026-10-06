"""Dashboard and impact aggregation over the stored analyses."""

from __future__ import annotations

from typing import Any

from knowledge_base.materials import MATERIALS_BY_ID
from matching.engine import SECTOR_LABELS, SOURCE_SECTOR_LABEL
from services import storage


def _short(analysis: dict) -> dict[str, Any]:
    top = analysis["matches"][0] if analysis["matches"] else None
    return {
        "id": analysis["id"],
        "created_at": analysis["created_at"],
        "material": analysis["material"]["name"],
        "material_id": analysis["material"]["id"],
        "category": analysis["material"]["category"],
        "confidence": analysis["identification"]["confidence"],
        "engine": analysis["identification"]["engine"],
        "source_type": analysis["source"]["source_type"],
        "location": analysis["source"]["location"],
        "quantity_t_per_month": analysis["source"]["quantity_t_per_month"],
        "allocated_t_per_month": analysis["totals"]["allocated_t_per_month"],
        "estimated_value_inr_per_month": analysis["totals"]["estimated_value_inr_per_month"],
        "estimated_co2e_t_per_month": analysis["totals"]["estimated_co2e_avoided_t_per_month"],
        "potential_matches": analysis["totals"]["potential_matches"],
        "top_match": {
            "company_name": top["recipient"]["company_name"],
            "sector": top["recipient"]["sector"],
            "sector_label": SECTOR_LABELS.get(top["recipient"]["sector"], top["recipient"]["sector"]),
            "score": top["overall_score"],
            "distance_km": top["distance_km"],
            "match_id": top["id"],
        }
        if top
        else None,
        "seeded": analysis.get("seeded", False),
    }


def _match_card(match: dict, analysis: dict) -> dict[str, Any]:
    return {
        "id": match["id"],
        "analysis_id": analysis["id"],
        "material": analysis["material"]["name"],
        "company_name": match["recipient"]["company_name"],
        "sector": match["recipient"]["sector"],
        "sector_label": SECTOR_LABELS.get(match["recipient"]["sector"], match["recipient"]["sector"]),
        "location": match["recipient"]["location"],
        "score": match["overall_score"],
        "distance_km": match["distance_km"],
        "reuse_type": match["reuse_type"],
        "matched_quantity_t_per_month": match["matched_quantity_t_per_month"],
        "required_quantity_range_t_per_month": match["required_quantity_range_t_per_month"],
        "available_quantity_t_per_month": match["available_quantity_t_per_month"],
        "estimated_value_inr_per_month": match["estimated_value_inr_per_month"],
        "estimated_co2e_t_per_month": match["estimated_co2e_t_per_month"],
        "top_reason": match["reasons"][0] if match["reasons"] else "",
    }


def dashboard() -> dict[str, Any]:
    analyses = storage.all_newest_first()
    recent = [_short(a) for a in analyses[:8]]

    top_matches = sorted(
        (m for a in analyses for m in a["matches"] if m["matched_quantity_t_per_month"] > 0),
        key=lambda m: -m["overall_score"],
    )[:6]
    top_cards = [
        _match_card(m, next(a for a in analyses if a["id"] == m["analysis_id"])) for m in top_matches
    ]

    categories: dict[str, dict[str, Any]] = {}
    for a in analyses:
        key = a["material"]["category"]
        bucket = categories.setdefault(
            key,
            {"category": key, "label": key.replace("_", " ").title(), "analyses": 0, "tonnes": 0.0, "value": 0.0, "co2e": 0.0},
        )
        bucket["analyses"] += 1
        bucket["tonnes"] += a["source"]["quantity_t_per_month"]
        bucket["value"] += a["totals"]["estimated_value_inr_per_month"]
        bucket["co2e"] += a["totals"]["estimated_co2e_avoided_t_per_month"]
    for bucket in categories.values():
        bucket["tonnes"] = round(bucket["tonnes"], 2)
        bucket["value"] = round(bucket["value"], 2)
        bucket["co2e"] = round(bucket["co2e"], 3)

    sectors: dict[str, float] = {}
    for a in analyses:
        for m in a["matches"]:
            if m["matched_quantity_t_per_month"] > 0:
                sectors[m["recipient"]["sector"]] = (
                    sectors.get(m["recipient"]["sector"], 0.0) + m["matched_quantity_t_per_month"]
                )
    sector_flow = [
        {"sector": s, "label": SECTOR_LABELS.get(s, s), "tonnes": round(v, 2)}
        for s, v in sorted(sectors.items(), key=lambda kv: -kv[1])
    ]

    impact = {
        "analyses": len(analyses),
        "tonnes_analysed": round(sum(a["source"]["quantity_t_per_month"] for a in analyses), 2),
        "tonnes_diverted": round(sum(a["totals"]["allocated_t_per_month"] for a in analyses), 2),
        "potential_matches": sum(a["totals"]["potential_matches"] for a in analyses),
        "viable_matches": sum(a["totals"]["viable_matches"] for a in analyses),
        "estimated_value_inr_per_month": round(sum(a["totals"]["estimated_value_inr_per_month"] for a in analyses), 2),
        "estimated_co2e_t_per_month": round(sum(a["totals"]["estimated_co2e_avoided_t_per_month"] for a in analyses), 3),
        "label": "Estimated impact - demo calculation",
    }
    impact["diversion_rate"] = (
        round(impact["tonnes_diverted"] / impact["tonnes_analysed"], 3) if impact["tonnes_analysed"] else 0.0
    )

    return {
        "recent_analyses": recent,
        "top_matches": top_cards,
        "waste_categories": sorted(categories.values(), key=lambda c: -c["tonnes"]),
        "sector_flow": sector_flow,
        "impact": impact,
        "generated_from": "in-memory demo store",
        "demo_data": True,
    }


def impact_summary() -> dict[str, Any]:
    analyses = storage.all_newest_first()

    by_sector: dict[str, dict[str, float]] = {}
    for a in analyses:
        for m in a["matches"]:
            if m["matched_quantity_t_per_month"] <= 0:
                continue
            s = m["recipient"]["sector"]
            bucket = by_sector.setdefault(s, {"tonnes": 0.0, "value": 0.0, "co2e": 0.0, "routes": 0})
            bucket["tonnes"] += m["matched_quantity_t_per_month"]
            bucket["value"] += m["estimated_value_inr_per_month"]
            bucket["co2e"] += m["estimated_co2e_t_per_month"]
            bucket["routes"] += 1

    sector_rows = [
        {
            "sector": s,
            "label": SECTOR_LABELS.get(s, s),
            "tonnes": round(v["tonnes"], 2),
            "value": round(v["value"], 2),
            "co2e": round(v["co2e"], 3),
            "routes": int(v["routes"]),
        }
        for s, v in sorted(by_sector.items(), key=lambda kv: -kv[1]["tonnes"])
    ]

    by_source: dict[str, dict[str, float]] = {}
    for a in analyses:
        key = a["source"]["source_type"]
        bucket = by_source.setdefault(key, {"analysed": 0.0, "diverted": 0.0, "co2e": 0.0, "analyses": 0})
        bucket["analysed"] += a["source"]["quantity_t_per_month"]
        bucket["diverted"] += a["totals"]["allocated_t_per_month"]
        bucket["co2e"] += a["totals"]["estimated_co2e_avoided_t_per_month"]
        bucket["analyses"] += 1

    source_rows = [
        {
            "source_type": k,
            "label": SOURCE_SECTOR_LABEL.get(k, k.title()),
            "analysed_t": round(v["analysed"], 2),
            "diverted_t": round(v["diverted"], 2),
            "co2e_t": round(v["co2e"], 3),
            "analyses": int(v["analyses"]),
        }
        for k, v in sorted(by_source.items(), key=lambda kv: -kv[1]["analysed"])
    ]

    totals = {
        "tonnes_analysed": round(sum(a["source"]["quantity_t_per_month"] for a in analyses), 2),
        "tonnes_diverted": round(sum(a["totals"]["allocated_t_per_month"] for a in analyses), 2),
        "estimated_value_inr_per_month": round(sum(a["totals"]["estimated_value_inr_per_month"] for a in analyses), 2),
        "estimated_co2e_t_per_month": round(sum(a["totals"]["estimated_co2e_avoided_t_per_month"] for a in analyses), 3),
        "analyses": len(analyses),
    }
    totals["estimated_co2e_t_per_year"] = round(totals["estimated_co2e_t_per_month"] * 12, 3)
    totals["estimated_value_inr_per_year"] = round(totals["estimated_value_inr_per_month"] * 12, 2)
    totals["diversion_rate"] = (
        round(totals["tonnes_diverted"] / totals["tonnes_analysed"], 3) if totals["tonnes_analysed"] else 0.0
    )

    # Reference table of the demo emission factors actually used.
    factors = [
        {
            "material": m["name"],
            "co2e_avoided_t_per_tonne": m["co2e_avoided_t_per_tonne"],
            "typical_price_inr_per_tonne": m["typical_price_inr_per_tonne"],
        }
        for m in MATERIALS_BY_ID.values()
        if m["id"] != "unknown_material"
    ]

    return {
        "totals": totals,
        "by_sector": sector_rows,
        "by_source_type": source_rows,
        "factors_used": sorted(factors, key=lambda f: -f["co2e_avoided_t_per_tonne"]),
        "formulae": {
            "waste_diverted": "sum over allocated matches of min(available, recipient_max), allocated greedily by score",
            "estimated_value_inr_per_month": "allocated tonnes x max(recipient price, material typical price)",
            "estimated_co2e_t_per_month": "allocated tonnes x material.co2e_avoided_t_per_tonne",
        },
        "disclaimer": (
            "Estimated impact - demo calculation. Prices and CO2e factors are illustrative values stored in "
            "the knowledge base, not certified figures. Replace them with validated LCA factors before "
            "real-world use."
        ),
        "demo_data": True,
    }
