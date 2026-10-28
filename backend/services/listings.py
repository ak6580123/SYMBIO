"""The demand / supply marketplace (§6).

What a listing is: one party stating, in their own words, that they have tonnes of
something or want tonnes of something. That is the *only* thing this module stores. It
does not generate demand, it does not price anything, and it never asks the language
model to write one: every seeded listing is traceable to a recipient or source record
(`data/generate_listings.py`), and every published one names the materials it accepts
by knowledge-base id, which is validated against the knowledge base before it is kept.

Why the engine still decides: when a listing needs to know *who could take this*, it
calls `matching.engine.find_matches` - the same safety gate, the same six weighted
components, the same tie-breaks as a normal analysis. The marketplace adds the party
and the specification; it does not add a ranking of its own.

Persistence: seeded listings come from `data/listings.json`; anything published in this
session lives in memory and disappears on restart. `to_row()` is the Postgres shape
(`database/schema.sql`) so the swap is a storage change, not a model change.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from knowledge_base import loader
from knowledge_base.materials import MATERIALS_BY_ID, get_material
from matching import engine, logistics

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "listings.json")

KINDS = ("demand", "supply")

# The marketplace's own fit function only applies listing-to-listing, where there is
# no partner record to score against. Three parts, equal weight, and every one of
# them is a number the two listings actually carry.
FIT_PARTS = ("material", "quantity", "price", "distance")
PRICE_TOLERANCE = 1.15
"""A supplier asking up to 15% over the stated offer is still worth showing: the offer
is a listing figure, not a contract."""

_SEED: list[dict[str, Any]] | None = None
_SESSION: list[dict[str, Any]] = []


def _load_seed() -> list[dict[str, Any]]:
    global _SEED
    if _SEED is None:
        with open(DATA_PATH, encoding="utf-8") as handle:
            _SEED = json.load(handle)["listings"]
    return _SEED


def reset() -> None:
    """Drop session listings. Used by the test suite; nothing calls it from a request."""
    _SESSION.clear()


def all_listings(
    kind: str | None = None,
    material_id: str | None = None,
    status: str | None = "open",
) -> list[dict[str, Any]]:
    """Everything the marketplace can show, from the three places it comes from.

    Seeded network rows (read-only reference data), rows published in this session by a
    visitor with no account, and rows saved to an organisation. A persistent row is
    marked `persisted: true` and carries its own `origin`, so the three never look alike
    when they are not alike - and a visitor's row still disappears on restart, because
    that is what it is.
    """
    rows = [dict(row) for row in _load_seed()] + [dict(row) for row in _SESSION] + _persistent()
    if kind:
        rows = [row for row in rows if row["kind"] == kind]
    if material_id:
        rows = [row for row in rows if material_id in row["material_ids"]]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return rows


def _persistent() -> list[dict[str, Any]]:
    """Saved organisation listings, as marketplace rows.

    Read through `services/persistence.py`, which knows the caller's tenant from the
    request scope: other organisations' rows arrive already limited to what they
    advertise, and this organisation's arrive in full, paused and closed ones included.
    """
    try:
        from services import persistence  # noqa: PLC0415 - optional in a build with no database

        if not persistence.available():
            return []
        # Own rows first: for a listing this organisation published, the fuller view
        # (requirements, provenance, paused and closed rows) is the one to show.
        rows = persistence.tenant_listings() + persistence.advertised_listings()
    except Exception:
        return []
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        merged.append(row)
    return merged


def get(listing_id: str) -> dict[str, Any] | None:
    for row in all_listings(status=None):
        if row["id"] == listing_id:
            return row
    return None


def draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a listing without storing it.

    `POST /api/listings/match` accepts an inline listing for what-if work. A draft has
    to satisfy every rule a published listing does - otherwise a hypothetical could
    skip the checks a real one cannot - but it must not enter the marketplace.
    """
    return _record(payload)


def publish(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a listing and keep it - in the database when it belongs to an
    organisation, in this session when nobody is signed in.

    The split is deliberate and it is reported, not hidden: `_record` applies the same
    rules to both, so an anonymous visitor and a signed-in tenant cannot publish
    different kinds of claim, and the response says which one happened.
    """
    record = _record(payload)
    saved = _save_permanently(record)
    if saved is not None:
        return saved
    return _store(record)


def _save_permanently(record: dict[str, Any]) -> dict[str, Any] | None:
    """Write through to the tenant's listings, or return None for "no storage here"."""
    try:
        from services import persistence  # noqa: PLC0415

        if persistence.actor() is None or not persistence.available():
            return None
        stored = persistence.save_listing(record)
    except persistence.PersistenceUnavailable:
        raise  # a signed-in publish must never quietly degrade to "session only"
    except Exception:
        return None
    return {**stored, "persisted": True, "origin": "saved to your organisation"}


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    """The rules the marketplace enforces, and the record that comes out of them.

    The validation is the feature: a listing cannot name a material the knowledge base
    does not have, cannot claim a partner that does not exist, and cannot carry a
    quantity or price the engine would silently misread. A `ValueError` here becomes a
    422 at the endpoint, so the UI cannot show a listing the API refused.
    """
    kind = payload.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    materials = [m for m in (payload.get("material_ids") or []) if str(m).strip()]
    if not materials:
        raise ValueError("a listing has to name at least one material")
    unknown = [m for m in materials if m not in MATERIALS_BY_ID]
    if unknown:
        raise ValueError(
            f"{', '.join(unknown)} is not a material in the Symbio knowledge base. "
            "A listing can only offer or request a material the knowledge base describes."
        )
    if len(set(materials)) != len(materials):
        raise ValueError("material_ids must not repeat a material")

    quantity = float(payload.get("quantity_t_per_month") or 0)
    if not quantity > 0:
        raise ValueError("quantity_t_per_month must be greater than zero")
    if quantity > 1_000_000:
        raise ValueError("quantity_t_per_month is implausibly large for this dataset")

    # `or 0.0`, not `.get(a, b)`: a demand listing that explicitly sends
    # `offer_price_inr_per_tonne: null` must not fall through to an asking price it
    # never set - that is how a demand form would end up carrying a supplier's number.
    price = float(payload.get("offer_price_inr_per_tonne") or 0.0) if kind == "demand" else float(
        payload.get("asking_price_inr_per_tonne") or 0.0
    )
    if price < 0:
        raise ValueError("a price cannot be negative")
    ceiling = price_ceiling_inr()
    if price > ceiling:
        raise ValueError(f"price must stay at or below the knowledge base ceiling of ₹{ceiling:,.0f}/tonne")

    distance = payload.get("max_distance_km")
    distance = 60.0 if distance is None else float(distance)
    if not 0 < distance <= 500:
        raise ValueError("max_distance_km must be between 0 and 500 for this demo region")

    party_id = payload.get("party_id")
    if party_id:
        if kind == "demand" and not loader.get_recipient(party_id):
            raise ValueError(f"'{party_id}' is not a partner in the demo dataset")
        if kind == "supply" and not _known_source(party_id):
            raise ValueError(f"'{party_id}' is not a source in the demo dataset")

    record: dict[str, Any] = {
        "id": f"lst_{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "party_id": party_id,
        "party_name": payload.get("party_name") or (party_id if party_id else "Unnamed source"),
        "party_sector": payload.get("party_sector"),
        # Whatever the author stated. A listing is never placed in a city its author
        # did not name: an absent location stays absent and the listing is then
        # matched without a distance rather than with an invented one.
        "location": (payload.get("location") or "").strip() or None,
        "latitude": float(payload.get("latitude")) if payload.get("latitude") is not None else None,
        "longitude": float(payload.get("longitude")) if payload.get("longitude") is not None else None,
        "material_ids": materials,
        "quantity_t_per_month": round(quantity, 3),
        "max_distance_km": round(distance, 1),
        "requirements": {
            key: value
            for key, value in (payload.get("requirements") or {}).items()
            if value not in (None, "")
        },
        "notes": (payload.get("notes") or "")[:1000],
        # A demand listing's "what will you do with it" and either side's cadence are
        # stated by the author and stored as stated: they are shown, never scored.
        "frequency": (payload.get("frequency") or "monthly"),
        "application_use": (payload.get("application_use") or "")[:200],
        "status": "open",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "origin": "published in this session",
        "persisted": False,
        "material_names": [MATERIALS_BY_ID[m]["name"] for m in materials],
    }
    # A listing raised for a known partner or source inherits that party's own
    # recorded place. That is a copy of data that exists - not a default city: when
    # neither the author nor the record says where, the listing stays unplaced.
    if record["location"] is None and party_id:
        party = loader.get_recipient(party_id) or loader.get_source(party_id)
        if party:
            record["location"] = party.get("location")
            record["latitude"] = party.get("latitude")
            record["longitude"] = party.get("longitude")
            record["location_note"] = "place taken from the party record this listing belongs to"
            record["location_resolved"] = record["latitude"] is not None and record["longitude"] is not None
            record["location_source"] = "party record" if record["location_resolved"] else "stated only"

    if record["latitude"] is None or record["longitude"] is None:
        from services.analysis import resolve_coordinates

        from services.analysis import resolve_coordinates_detailed

        lat, lng, exact, place_info = resolve_coordinates_detailed(record["location"] or "", None, None)
        record["latitude"], record["longitude"] = lat, lng
        record["location_resolved"] = exact
        record["location_source"] = str(place_info.get("source") or "unresolved")
        record["location_note"] = (
            "coordinates resolved from the recorded gazetteer"
            if exact
            else "no coordinates recorded for this location - it is matched on material, quantity and price, not distance"
        )
    record["offer_price_inr_per_tonne" if kind == "demand" else "asking_price_inr_per_tonne"] = round(price, 2)
    return record


def _store(record: dict[str, Any]) -> dict[str, Any]:
    _SESSION.append(record)
    return dict(record)


def price_ceiling_inr() -> float:
    from knowledge_base.materials import price_ceiling_inr as ceiling

    return ceiling()


def _known_source(source_id: str) -> bool:
    return any(s["id"] == source_id for s in loader.get_sources())


def _identification_for(material_id: str) -> dict[str, Any]:
    """A listing states its material outright, so identification is not a guess."""
    material = get_material(material_id)
    return {
        "material_id": material["id"],
        "material": material["name"],
        "category": material["category"],
        "confidence": 1.0,
        "engine": "listing_material_id",
        "reuse_categories": list(material["reuse_categories"]),
        "safety_level": material["safety_level"],
        "composition": {},
        "reasoning": "The material was named by the listing author and exists in the knowledge base.",
        "uncertainty_note": None,
        "source": "listing",
    }


def _source_side(listing: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": listing.get("party_sector") or "industry",
        "location": listing["location"] or "",
        "location_resolved": listing["latitude"] is not None and listing["longitude"] is not None,
        "latitude": listing["latitude"],
        "longitude": listing["longitude"],
        "quantity_t_per_month": listing["quantity_t_per_month"],
        "unit": "tonnes",
        "frequency": "monthly",
    }


def _fit(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Listing-to-listing fit. Four parts, each a number both listings state."""
    shared = sorted(set(a["material_ids"]) & set(b["material_ids"]))
    material_fit = 1.0 if shared else 0.0

    want = float(a["quantity_t_per_month"])
    have = float(b["quantity_t_per_month"])
    quantity_fit = round(min(have, want) / max(have, want), 4) if want and have else 0.0

    ask = float(b.get("asking_price_inr_per_tonne") or 0.0)
    offer = float(a.get("offer_price_inr_per_tonne") or 0.0)
    if ask <= 0:
        price_fit = 1.0
    elif offer <= 0:
        price_fit = 0.0
    else:
        price_fit = round(min(1.0, offer * PRICE_TOLERANCE / ask), 4)

    # Both sides need to be placeable before any distance is claimed about them.
    placed = all(x.get(key) is not None for x in (a, b) for key in ("latitude", "longitude"))
    if placed:
        distance = engine.haversine_km(
            float(a["latitude"]), float(a["longitude"]), float(b["latitude"]), float(b["longitude"])
        )
        limit = min(float(a.get("max_distance_km") or 0), float(b.get("max_distance_km") or 0)) or None
        distance_fit = 1.0 if limit is None else round(max(0.0, 1.0 - distance / limit), 4)
        within = limit is None or distance <= limit
    else:
        # Neutral, like the engine's abstention: neither listing gains or loses ground
        # for a distance nobody measured.
        distance = None
        distance_fit = 0.5
        within = None

    weights = {"material": 0.40, "quantity": 0.20, "price": 0.20, "distance": 0.20}
    total = sum(weights[part] * value for part, value in [
        ("material", material_fit),
        ("quantity", quantity_fit),
        ("price", price_fit),
        ("distance", distance_fit),
    ])
    return {
        "fit": round(total * 100, 1),
        "fit_components": {k: round(v, 3) for k, v in [
            ("material", material_fit),
            ("quantity", quantity_fit),
            ("price", price_fit),
            ("distance", distance_fit),
        ]},
        "weights_used": weights,
        "shared_material_ids": shared,
        "distance_km": distance,
        "distance_note": (
            None if placed else "No coordinates on both sides of this pair, so the distance is not calculated."
        ),
        "within_stated_range": within,
        "gap": {
            "quantity_t_per_month": round(want - have, 3),
            "price_inr_per_tonne": round(offer - ask, 2),
        },
    }


def match(listing: dict[str, Any], *, limit: int = 8) -> dict[str, Any]:
    """Who this listing could actually deal with, and how well.

    Two candidate sources, kept visibly apart:

    * **Counterparty listings** - matched on what both sides stated, with `_fit`.
    * **The matching engine** - the listing's material run through
      `engine.find_matches` against the partner pool, so a supply listing gets the same
      ranked recipients a real analysis would produce and a demand listing gets the
      score it would have earned if its own partner record were the source.
      The safety layer runs on this path; a route it refuses is refused here too.
    """
    opposite = "supply" if listing["kind"] == "demand" else "demand"
    counterparties: list[dict[str, Any]] = []
    for other in all_listings(kind=opposite):
        if not set(other["material_ids"]) & set(listing["material_ids"]):
            continue
        fit = _fit(listing, other)
        if not fit["shared_material_ids"]:
            continue
        counterparties.append({**fit, "listing": other, "scored_by": "listing fit (both parties' stated figures)"})
    counterparties.sort(key=lambda row: (-row["fit"], row["listing"]["id"]))

    engine_rows, excluded = _engine_side(listing)
    return {
        "listing": listing,
        "counterparties": counterparties[:limit],
        "counterparty_count": len(counterparties),
        "engine_matches": engine_rows[:limit],
        "engine_match_count": len(engine_rows),
        "excluded_by_safety": excluded,
        "note": (
            "Counterparty fits compare what two listings state about themselves. Engine rows are the "
            "deterministic ranking over the partner pool, with the safety layer applied. Where they "
            "disagree, the engine row is the one the rest of Symbio uses."
        ),
        "demo_data": True,
    }


def _engine_side(listing: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the real engine for each material a listing names."""
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for material_id in listing["material_ids"]:
        material = get_material(material_id)
        identification = _identification_for(material_id)
        source = _source_side(listing)
        if listing["kind"] == "demand":
            # The demand side *is* a partner: score that partner against the material
            # rather than the whole pool, so the number means "could this listing be
            # filled as stated".
            partner = loader.get_recipient(listing.get("party_id") or "")
            candidates = [partner] if partner else []
        else:
            candidates = [r for r in loader.get_recipients() if material_id in (r.get("accepted_materials") or [])]
        if not candidates:
            continue
        matches, dropped = engine.find_matches(
            analysis_id=f"listing:{listing['id']}",
            material=material,
            identification=identification,
            source=source,
            candidates=candidates,
        )
        for row in dropped:
            excluded.append({**row, "material_id": material_id})
        for item in matches:
            key = (item.recipient.id, material_id)
            if key in seen:
                continue
            seen.add(key)
            card = item.model_dump()
            card["material_id"] = material_id
            if card["distance_km"] is None:
                card["transport"] = None
            else:
                card["transport"] = logistics.estimate(
                    card["distance_km"],
                    card["matched_quantity_t_per_month"],
                    card["estimated_value_inr_per_month"],
                    (
                        card["estimated_value_inr_per_month"] / card["matched_quantity_t_per_month"]
                        if card["matched_quantity_t_per_month"] > 0
                        else 0.0
                    ),
                )
            card["scored_by"] = "matching engine"
            rows.append(card)
    rows.sort(
        key=lambda card: (
            -card["overall_score"],
            card["distance_km"] is None,
            card["distance_km"] or 0.0,
            card["recipient"]["id"],
        )
    )
    return rows, excluded


def stats() -> dict[str, Any]:
    rows = all_listings()
    by_material: dict[str, dict[str, Any]] = {}
    for row in rows:
        for material_id in row["material_ids"]:
            bucket = by_material.setdefault(
                material_id,
                {"material_id": material_id, "name": MATERIALS_BY_ID[material_id]["name"], "demand": 0, "supply": 0,
                 "demand_t_per_month": 0.0, "supply_t_per_month": 0.0},
            )
            bucket[row["kind"]] += 1
            bucket[f"{row['kind']}_t_per_month"] = round(
                bucket[f"{row['kind']}_t_per_month"] + float(row["quantity_t_per_month"]), 2
            )
    for bucket in by_material.values():
        bucket["balance_t_per_month"] = round(bucket["supply_t_per_month"] - bucket["demand_t_per_month"], 2)
    persisted = [row for row in rows if row.get("persisted")]
    return {
        "total": len(rows),
        "demand": len([r for r in rows if r["kind"] == "demand"]),
        "supply": len([r for r in rows if r["kind"] == "supply"]),
        "session_published": len(_SESSION),
        "persisted": len(persisted),
        "seeded": len(_load_seed()),
        "by_material": sorted(by_material.values(), key=lambda b: (-b["demand"] - b["supply"], b["material_id"])),
    }


def to_row(listing: dict[str, Any]) -> dict[str, Any]:
    """The `listings` table row this record would become (§18)."""
    return {
        "id": listing["id"],
        "kind": listing["kind"],
        "party_id": listing.get("party_id"),
        "party_name": listing.get("party_name"),
        "location": listing.get("location"),
        "latitude": listing.get("latitude"),
        "longitude": listing.get("longitude"),
        "material_ids": listing.get("material_ids"),
        "quantity_t_per_month": listing.get("quantity_t_per_month"),
        "price_inr_per_tonne": listing.get("offer_price_inr_per_tonne", listing.get("asking_price_inr_per_tonne")),
        "max_distance_km": listing.get("max_distance_km"),
        "requirements": listing.get("requirements") or {},
        "notes": listing.get("notes") or "",
        "status": listing.get("status", "open"),
        "origin": listing.get("origin", "seed"),
        "created_on": listing.get("created_at"),
    }
