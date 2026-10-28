"""Regional demand potential (§10) - location-aware, area-level, and honest about it.

What this answers: *which part of the demo region has the most unmet intake capacity
for a material like yours*. What it must never answer is "Company X will buy 30 tonnes
next month" - no dataset here contains a purchase intention, a contract or a forecast
of anyone's buying. So every number is built from three things that do exist: each
partner's recorded intake window, what the stored analyses have already allocated
against it, and what the open demand listings state.

The output is an index between 0 and 100 per *area*, with the four components shown
next to it, because an index a reader cannot decompose is an advertisement. The bands
are labelled "High / Medium / Low demand potential" - potential, not demand, and not a
prediction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from knowledge_base import loader
from knowledge_base.materials import MATERIALS_BY_ID
from matching import engine
from services import listings as listings_service
from services import storage

AREA_RADIUS_KM = 25.0
"""Two localities this far apart are treated as different places. Chosen for the
Chennai demo area, where industrial zones sit 10-40 km apart."""

SUPPLY_SCAN_KM = 40.0
"""How far from an area a supply source has to be to count as reachable by it."""

COMPONENTS = {
    "intake_headroom": 0.40,
    "partner_breadth": 0.25,
    "open_listings": 0.20,
    "unserved_supply": 0.15,
}

COMPONENT_LABELS = {
    "intake_headroom": "Unfilled intake capacity (t/month)",
    "partner_breadth": "Distinct partners and sectors taking it",
    "open_listings": "Open demand listings in the area",
    "unserved_supply": "Nearby supply with nowhere to go yet",
}

BANDS = ((66.0, "High"), (33.0, "Medium"), (0.0, "Low"))


def _area_of(location: str) -> str:
    """'Red Hills, Chennai region' -> 'Red Hills'. The seed data states localities, so
    the grouping is by the part before the comma - no geocoder involved."""
    return (location or "").split(",")[0].strip() or "Unspecified"


def _allocations_by_recipient() -> dict[str, float]:
    allocated: dict[str, float] = defaultdict(float)
    for analysis in storage.all_newest_first():
        for match in analysis.get("matches") or []:
            allocated[match["recipient"]["id"]] += float(match.get("allocated_t_per_month") or 0.0)
    return allocated


def forecast(material_id: str | None = None, *, limit: int | None = None) -> dict[str, Any]:
    """Rank the areas of the demo region by how much unmet intake capacity they hold."""
    recipients = loader.get_recipients()
    sources = loader.get_sources()
    allocated = _allocations_by_recipient()
    demand_listings = [row for row in listings_service.all_listings(kind="demand") if row.get("status") == "open"]
    supply_listings = [row for row in listings_service.all_listings(kind="supply") if row.get("status") == "open"]
    analysis_supply = [
        {
            "area": _area_of(a["source"]["location"]),
            "latitude": float(a["source"]["latitude"]),
            "longitude": float(a["source"]["longitude"]),
            "tonnes": float(a["source"]["quantity_t_per_month"]),
            "material_ids": [a["material"]["id"]],
            "matched": round(sum(float(m.get("allocated_t_per_month") or 0.0) for m in a.get("matches") or []), 3),
        }
        for a in storage.all_newest_first()
        # An analysis whose location could not be placed contributes nothing to an
        # area's supply: counting it at the city centroid would invent geography for
        # someone sitting in another state.
        if a["source"].get("latitude") is not None and a["source"].get("longitude") is not None
    ]

    material = MATERIALS_BY_ID.get(material_id or "")
    if material_id and not material:
        return {"areas": [], "error": f"'{material_id}' is not a material in the Symbio knowledge base.", "demo_data": True}

    buckets: dict[str, dict[str, Any]] = {}
    for recipient in recipients:
        if material and material_id not in (recipient.get("accepted_materials") or []):
            continue
        area = _area_of(recipient["location"])
        bucket = buckets.setdefault(
            area,
            {
                "area": area,
                "partners": [],
                "sectors": set(),
                "materials": defaultdict(float),
                "headroom": 0.0,
                "intake": 0.0,
                "listing_tonnes": 0.0,
                "listing_count": 0,
                "latitudes": [],
                "longitudes": [],
            },
        )
        window_low = float(recipient["min_quantity_t_per_month"])
        window_high = float(recipient["max_quantity_t_per_month"])
        taken = round(allocated.get(recipient["id"], 0.0), 3)
        headroom = max(0.0, window_high - taken)
        bucket["partners"].append(
            {
                "id": recipient["id"],
                "company_name": recipient["company_name"],
                "sector": recipient["sector"],
                "window_t_per_month": [window_low, window_high],
                "allocated_t_per_month": taken,
                "headroom_t_per_month": round(headroom, 3),
                "price_inr_per_tonne": recipient["estimated_price_inr_per_tonne"],
            }
        )
        bucket["sectors"].add(recipient["sector"])
        bucket["headroom"] += headroom
        bucket["intake"] += taken
        for accepted in recipient.get("accepted_materials") or []:
            bucket["materials"][accepted] += headroom
        bucket["latitudes"].append(float(recipient["latitude"]))
        bucket["longitudes"].append(float(recipient["longitude"]))

    for row in demand_listings:
        if material and not set(row["material_ids"]) & {material_id}:
            continue
        area = _area_of(row["location"])
        if area in buckets:
            buckets[area]["listing_tonnes"] += float(row["quantity_t_per_month"])
            buckets[area]["listing_count"] += 1

    # Nearby supply that has not been absorbed yet: tonnes stated by sources within
    # SUPPLY_SCAN_KM of the area, minus what the analyses already placed.
    for name, bucket in buckets.items():
        centre = _centroid(bucket)
        reachable = 0.0
        for row in analysis_supply:
            if material and material_id not in row["material_ids"]:
                continue
            distance = engine.haversine_km(centre["latitude"], centre["longitude"], row["latitude"], row["longitude"])
            if distance <= SUPPLY_SCAN_KM:
                reachable += max(0.0, row["tonnes"] - row["matched"])
        for row in supply_listings:
            if material and material_id not in row["material_ids"]:
                continue
            if _area_of(row["location"]) == name:
                reachable += float(row["quantity_t_per_month"])
        bucket["unserved_supply"] = round(reachable, 3)

    areas = [row for row in buckets.values() if row["partners"]]
    if not areas:
        return {
            "areas": [],
            "material_id": material_id,
            "note": (
                f"No partner in the demo dataset lists {material['name']} as accepted, so there is no regional "
                "capacity to rank."
                if material
                else "No partners in the demo dataset."
            ),
            "method": _method(),
            "caveat": _caveat(),
            "demo_data": True,
        }

    maxima = {
        "intake_headroom": max(row["headroom"] for row in areas) or 1.0,
        "partner_breadth": max(len(row["partners"]) for row in areas) or 1,
        "open_listings": max(row["listing_tonnes"] for row in areas) or 1.0,
        "unserved_supply": max(row.get("unserved_supply", 0.0) for row in areas) or 1.0,
    }

    rows: list[dict[str, Any]] = []
    for row in areas:
        partners = sorted(row["partners"], key=lambda p: (-p["headroom_t_per_month"], p["company_name"]))
        listed = [item for item in demand_listings if _area_of(item["location"]) == row["area"] and (not material or material_id in item["material_ids"])]
        scores = {
            "intake_headroom": row["headroom"] / maxima["intake_headroom"],
            "partner_breadth": len(partners) / maxima["partner_breadth"],
            "open_listings": (row["listing_tonnes"] / maxima["open_listings"]) if maxima["open_listings"] else 0.0,
            "unserved_supply": (row.get("unserved_supply", 0.0) / maxima["unserved_supply"]) if maxima["unserved_supply"] else 0.0,
        }
        index = round(100.0 * sum(COMPONENTS[key] * value for key, value in scores.items()), 1)
        top_materials = sorted(row["materials"].items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        rows.append(
            {
                "area": row["area"],
                "latitude": _centroid(row)["latitude"],
                "longitude": _centroid(row)["longitude"],
                "demand_potential_index": index,
                "band": next(label for floor, label in BANDS if index >= floor),
                "components": {key: round(value, 3) for key, value in scores.items()},
                "component_weights": COMPONENTS,
                "partners": partners,
                "partner_count": len(partners),
                "sector_count": len(row["sectors"]),
                "intake_headroom_t_per_month": round(row["headroom"], 2),
                "currently_allocated_t_per_month": round(row["intake"], 2),
                "open_demand_listings": len(listed),
                "open_demand_tonnes_per_month": round(row["listing_tonnes"], 2),
                "nearby_unplaced_supply_t_per_month": row.get("unserved_supply", 0.0),
                "top_materials": [
                    {
                        "material_id": material_key,
                        "name": MATERIALS_BY_ID[material_key]["name"],
                        "headroom_t_per_month": round(value, 2),
                    }
                    for material_key, value in top_materials
                    if material_key in MATERIALS_BY_ID
                ],
                "drivers": _drivers(row, partners, scores, listed),
            }
        )

    rows.sort(key=lambda item: (-item["demand_potential_index"], item["area"]))
    if limit:
        rows = rows[:limit]
    return {
        "areas": rows,
        "count": len(rows),
        "material_id": material_id,
        "material_name": material["name"] if material else None,
        "radius_km": AREA_RADIUS_KM,
        "supply_scan_km": SUPPLY_SCAN_KM,
        "method": _method(),
        "caveat": _caveat(),
        "not_a_forecast": (
            "No purchase intention, contract or monthly volume is claimed for any company here. This ranks places "
            "by recorded capacity, not people by likelihood."
        ),
        "demo_data": True,
    }


def _centroid(bucket: dict[str, Any]) -> dict[str, float]:
    # Network geography, not user geography: this centre is where a *seeded* Chennai
    # area's marker sits when the area has no recorded partner to average over. It is
    # never applied to a source, a listing or an analysis.
    latitudes = bucket["latitudes"] or [13.0827]
    longitudes = bucket["longitudes"] or [80.2707]
    return {
        "latitude": round(sum(latitudes) / len(latitudes), 4),
        "longitude": round(sum(longitudes) / len(longitudes), 4),
    }


def _drivers(bucket: dict[str, Any], partners: list[dict[str, Any]], scores: dict[str, float], listed: list[dict[str, Any]]) -> list[str]:
    """Plain sentences, each tied to a number the caller can check."""
    out: list[str] = []
    if partners:
        top = partners[0]
        out.append(
            f"{top['company_name']} can still take {top['headroom_t_per_month']:,.0f} t/month of its "
            f"{top['window_t_per_month'][1]:,.0f} t/month window"
        )
    out.append(
        f"{bucket['headroom']:,.1f} t/month of unfilled intake capacity across {len(partners)} partner(s) in "
        f"{len(bucket['sectors'])} sector(s)"
    )
    if listed:
        out.append(f"{len(listed)} open demand listing(s) totalling {bucket['listing_tonnes']:,.1f} t/month")
    else:
        out.append("No open demand listing for this area - the capacity is recorded, not advertised")
    if scores["unserved_supply"] > 0.5:
        out.append(
            f"{bucket.get('unserved_supply', 0.0):,.1f} t/month of nearby supply has not been placed anywhere yet"
        )
    return out


def _method() -> str:
    weights = ", ".join(f"{COMPONENT_LABELS[key]} {int(value * 100)}%" for key, value in COMPONENTS.items())
    return (
        "Each area's four components are divided by the strongest area's value for that component, then weighted: "
        f"{weights}. No component is a model output; every one is a sum over recorded intake windows, stored "
        "allocations, open listings and stated supply."
    )


def _caveat() -> str:
    return (
        "Regional potential only. Areas are localities in the demo dataset, capacity is what partners said they can "
        "take, and an index of 100 means 'the strongest area in this dataset', not 'certain to buy'."
    )
