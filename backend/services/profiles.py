"""Structured industry profiles (§5) and the four-step symbiosis chain (§7).

A recipient record answers one question - *what will this partner accept*. A profile
answers the three that come before and after it: what the plant makes, what it has to
be able to do to the material, and what it throws out that somebody else needs.

Two honesty rules run through this module:

* **Templates are per sector, records win.** `data/sector_profiles.json` describes a
  kind of industry; the recipient's own `accepted_materials` and
  `processing_capability` are facts about that company. The merge keeps both and
  labels which line came from where, so nothing a template asserts can be mistaken
  for a company's declaration.
* **The product end of the chain reuses the engine.** `Potential Reuse Product` is
  computed with `matching.engine.choose_reuse_category`, the same function that
  decides a pathway's end use - including its rule that a sector which performs none
  of the recorded reuse applications gets no product name. Profiles never invent one.

Nothing here touches a score, an ordering or the safety layer.
"""

from __future__ import annotations

import json
import os
from typing import Any

from knowledge_base import loader
from knowledge_base.materials import MATERIALS_BY_ID, get_material
from matching import engine

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sector_profiles.json")

_PROFILE_CACHE: dict[str, Any] | None = None

SUPPLY_STEP = "Supply"
DEMAND_STEP = "Material demand"
CAPABILITY_STEP = "Production capability"
PRODUCT_STEP = "Potential reuse product"


def profiles() -> dict[str, dict[str, Any]]:
    """The sector templates, keyed by sector id."""
    global _PROFILE_CACHE
    if _PROFILE_CACHE is None:
        with open(DATA_PATH, encoding="utf-8") as handle:
            _PROFILE_CACHE = json.load(handle).get("profiles", {})
    return _PROFILE_CACHE


def sector_profile(sector: str) -> dict[str, Any]:
    return profiles().get(sector, {})


def _kb(material_id: str | None) -> dict[str, Any] | None:
    return MATERIALS_BY_ID.get(material_id or "")


def _demand_signals(material_ids: list[str]) -> list[dict[str, Any]]:
    """What the whole partner pool pays and can take for each material.

    Every number here is a min/max over `data/recipients.json`; nothing is assumed.
    """
    recipients = loader.get_recipients()
    signals: list[dict[str, Any]] = []
    for material_id in material_ids:
        material = _kb(material_id)
        if not material:
            continue
        seekers = [r for r in recipients if material_id in (r.get("accepted_materials") or [])]
        prices = [float(r["estimated_price_inr_per_tonne"]) for r in seekers if r.get("estimated_price_inr_per_tonne")]
        windows = [
            [float(r["min_quantity_t_per_month"]), float(r["max_quantity_t_per_month"])]
            for r in seekers
            if r.get("min_quantity_t_per_month") is not None
        ]
        signals.append(
            {
                "material_id": material_id,
                "name": material["name"],
                "category": material["category"],
                "safety_level": material["safety_level"],
                "partners_seeking": len(seekers),
                "price_range_inr_per_tonne": [min(prices), max(prices)] if prices else None,
                "quantity_window_t_per_month": (
                    [min(w[0] for w in windows), max(w[1] for w in windows)] if windows else None
                ),
                "note": (
                    f"{len(seekers)} partner(s) in the demo dataset list {material['name']}"
                    + (
                        f" at Rs {min(prices):,.0f}-{max(prices):,.0f}/tonne"
                        if prices
                        else "; none of them records a price"
                    )
                ),
            }
        )
    return signals


def _potential_receivers(material_id: str | None, exclude_id: str) -> list[dict[str, Any]]:
    """Partners whose recorded accepted list already includes this by-product."""
    if not material_id or material_id not in MATERIALS_BY_ID:
        return []
    source = loader.get_recipient(exclude_id)
    rows: list[dict[str, Any]] = []
    for recipient in loader.get_recipients():
        if recipient["id"] == exclude_id:
            continue
        if material_id not in (recipient.get("accepted_materials") or []):
            continue
        # Only a source with real coordinates can be measured against a partner; the
        # sort below already treats an unmeasured row as "last", not as "0 km".
        distance = None
        if source and source.get("latitude") is not None and source.get("longitude") is not None:
            distance = engine.haversine_km(
                float(source["latitude"]), float(source["longitude"]), float(recipient["latitude"]), float(recipient["longitude"])
            )
        rows.append(
            {
                "id": recipient["id"],
                "company_name": recipient["company_name"],
                "sector": recipient["sector"],
                "reuse_type": recipient.get("reuse_type"),
                "safety_level": recipient.get("safety_level"),
                "distance_km": distance,
                "price_inr_per_tonne": recipient.get("estimated_price_inr_per_tonne"),
                "accepted_at": [
                    recipient.get("min_quantity_t_per_month"),
                    recipient.get("max_quantity_t_per_month"),
                ],
            }
        )
    rows.sort(key=lambda row: (row["distance_km"] is None, row["distance_km"] or 0))
    return rows


def _product_for(material_id: str | None, recipient: dict[str, Any]) -> tuple[str, str]:
    """The end use this partner would actually put the material to, or the honest no.

    Same call the pathway builder makes, so a profile can never promise a product the
    engine refuses to name.
    """
    material = _kb(material_id)
    if not material:
        return "Unmodelled stream", "Not in the knowledge base, so no application is claimed for it."
    category = engine.choose_reuse_category(material, material.get("reuse_categories") or [], recipient.get("sector", ""))
    if category is None:
        return (
            "Assessed Material",
            f"{recipient.get('company_name') or 'This partner'}'s sector is not recorded as performing any reuse "
            f"application for {material['name']}; the material family matches, the application is unproven.",
        )
    label = engine.REUSE_END_USE.get(category, "Assessed Material")
    return label, f"Reached through the {category.replace('_', ' ')} route recorded for {material['name']}."


def for_recipient(recipient: dict[str, Any]) -> dict[str, Any]:
    """Merge the sector template with everything this company actually recorded."""
    template = sector_profile(recipient.get("sector", ""))
    recorded_ids = list(recipient.get("accepted_materials") or [])

    required: list[dict[str, Any]] = []
    seen: set[str] = set()
    # The company's own list first: it is the fact, the template is the context.
    for material_id in recorded_ids:
        material = _kb(material_id)
        seen.add(material_id)
        required.append(
            {
                "material_id": material_id,
                "name": material["name"] if material else material_id,
                "category": material["category"] if material else None,
                "note": None,
                "source": "recipient record",
            }
        )
    for item in template.get("materials_required") or []:
        material_id = item.get("material_id")
        if material_id in seen:
            # Same material, richer wording: keep the note, do not duplicate the row.
            for row in required:
                if row["material_id"] == material_id:
                    row["note"] = item.get("note")
                    row["source"] = "recipient record + sector template"
            continue
        if material_id:
            seen.add(material_id)
        required.append(
            {
                "material_id": material_id,
                "name": item.get("name"),
                "category": _kb(material_id)["category"] if _kb(material_id) else None,
                "note": item.get("note"),
                "source": "sector template (demo)",
            }
        )

    byproducts: list[dict[str, Any]] = []
    for item in template.get("byproducts") or []:
        material_id = item.get("material_id")
        receivers = _potential_receivers(material_id, recipient["id"])
        product, product_note = _product_for(material_id, recipient)
        byproducts.append(
            {
                "material_id": material_id,
                "name": item.get("name"),
                "note": item.get("note"),
                "source": "sector template (demo)",
                "disposition": (
                    "handled on site; not modelled as an outbound stream"
                    if not material_id
                    else ("accepted by another partner in the demo dataset" if receivers else "no partner in this dataset lists it")
                ),
                "potential_recipients": receivers,
                "own_product_note": product_note,
            }
        )

    demand = _demand_signals(recorded_ids)
    chain_rows = _chain(recipient, required, byproducts, demand, template)

    return {
        "recipient_id": recipient["id"],
        "company_name": recipient["company_name"],
        "sector": recipient.get("sector"),
        "sector_label": template.get("label") or engine.SECTOR_LABELS.get(recipient.get("sector", ""), recipient.get("sector")),
        "location": recipient.get("location"),
        "has_sector_template": bool(template),
        "profile_source": (
            "recipient record + sector template (demo)" if template else "recipient record only - no sector template"
        ),
        "products": list(template.get("products") or []),
        "certifications": list(template.get("certifications") or []),
        "intake_note": template.get("intake_note"),
        "capability": {
            "processing": list(recipient.get("processing_capability") or []),
            "reuse_type": recipient.get("reuse_type"),
            "safety_level": recipient.get("safety_level"),
            "summary": template.get("capability_summary"),
            "quantity_window_t_per_month": [
                recipient.get("min_quantity_t_per_month"),
                recipient.get("max_quantity_t_per_month"),
            ],
            "price_inr_per_tonne": recipient.get("estimated_price_inr_per_tonne"),
        },
        "materials_required": required,
        "byproducts": byproducts,
        "demand_signals": demand,
        "chain": chain_rows,
        "explanation": (
            f"{recipient['company_name']} is modelled as {template.get('label', 'a ' + str(recipient.get('sector'))).lower()}: "
            f"{len(required)} material(s) it can take and {len(byproducts)} stream(s) it generates. "
            "Products, certifications and by-products come from a sector template in this demo build; the accepted "
            "materials, capabilities, quantities and prices come from the partner's own record."
        )
        if template
        else (
            f"{recipient['company_name']}'s sector has no profile template in this build. Everything shown here - "
            "accepted materials, capabilities, quantity window and price - comes from the partner record itself."
        ),
        "demo_data": True,
    }


def _chain(
    recipient: dict[str, Any],
    required: list[dict[str, Any]],
    byproducts: list[dict[str, Any]],
    demand: list[dict[str, Any]],
    template: dict[str, Any],
) -> list[dict[str, Any]]:
    """The §5 sequence, in words the data supports."""
    named_waste = [b["name"] for b in byproducts if b.get("name")]
    rows = [
        {
            "step": SUPPLY_STEP,
            "label": "What this industry discards",
            "items": named_waste or ["No by-product profile is recorded for this sector"],
            "origin": "sector template (demo)",
            "detail": byproducts,
        },
        {
            "step": DEMAND_STEP,
            "label": "What it needs as input",
            "items": [row["name"] for row in required if row.get("name")],
            "origin": "recipient record + sector template (demo)",
            "detail": demand,
        },
        {
            "step": CAPABILITY_STEP,
            "label": "What it can do to a material",
            "items": list(recipient.get("processing_capability") or []) or ["None recorded"],
            "origin": "recipient record",
            "detail": [{"summary": template.get("capability_summary")} if template.get("capability_summary") else {}],
        },
    ]
    products: list[dict[str, Any]] = []
    for byproduct in byproducts:
        for receiver in byproduct["potential_recipients"][:3]:
            # `_product_for` needs the receiving partner's sector, nothing else.
            label, note = _product_for(byproduct["material_id"], {"sector": receiver["sector"]})
            products.append(
                {
                    "from": byproduct["name"],
                    "to": receiver["company_name"],
                    "product": label,
                    "note": note,
                    "distance_km": receiver.get("distance_km"),
                }
            )
    rows.append(
        {
            "step": PRODUCT_STEP,
            "label": "What a discarded stream could become",
            "items": [f"{p['from']} → {p['product']} at {p['to']}" for p in products]
            or ["No outbound stream from this sector is listed by another partner in the demo dataset"],
            "origin": "sector template (demo) + recipient accepted-material records",
            "detail": products,
        }
    )
    return rows


def summary_rows() -> list[dict[str, Any]]:
    """One row per sector, for the profile index and the role dashboards."""
    recipients = loader.get_recipients()
    rows = []
    for sector, template in sorted(profiles().items()):
        partners = [r for r in recipients if r.get("sector") == sector]
        outbound = [b for b in template.get("byproducts") or [] if b.get("material_id")]
        rows.append(
            {
                "sector": sector,
                "label": template.get("label"),
                "partners": len(partners),
                "partner_ids": [p["id"] for p in partners],
                "products": list(template.get("products") or []),
                "materials_required": [m["name"] for m in template.get("materials_required") or []],
                "byproducts": [b["name"] for b in template.get("byproducts") or []],
                "listed_material_ids": sorted({m["material_id"] for m in template.get("materials_required") or [] if m.get("material_id")}),
                "byproduct_material_ids": sorted({b["material_id"] for b in outbound if b.get("material_id")}),
                "certifications": list(template.get("certifications") or []),
                "capability_summary": template.get("capability_summary"),
                "intake_note": template.get("intake_note"),
            }
        )
    return rows


def intelligence_note(material_id: str | None, recipient: dict[str, Any]) -> dict[str, Any] | None:
    """The one-line §7 explanation a match detail page adds.

    Only a sentence and a product name - never a number, because the score has
    already been computed by the time this runs.
    """
    template = sector_profile(recipient.get("sector", ""))
    if not template and not recipient.get("accepted_materials"):
        return None
    product, note = _product_for(material_id, recipient)
    material = get_material(material_id)
    listed = material_id in (recipient.get("accepted_materials") or [])
    return {
        "sector_label": template.get("label"),
        "products": list(template.get("products") or []),
        "product": product,
        "product_note": note,
        "recorded_acceptance": listed,
        "acceptance_note": (
            f"{recipient['company_name']} lists {material['name']} as accepted"
            if listed
            else f"{recipient['company_name']} does not list {material['name']}; this route rests on the material "
            "category it accepts, not on a named acceptance"
        ),
        "intake_note": template.get("intake_note"),
        "certifications": list(template.get("certifications") or []),
        "origin": "sector template (demo)" if template else "recipient record only",
    }
