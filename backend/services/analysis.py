"""Analysis service - the end-to-end pipeline behind POST /api/analyze.

    waste input -> AI identification -> knowledge base -> deterministic
    matching -> ranked opportunities -> estimated impact
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ai import identification as ai_identification
from knowledge_base import loader
from knowledge_base.materials import MATERIALS_BY_ID, get_material
from matching import engine
from models.schemas import Frequency, SourceSector
from services import storage

# Days per month used to normalise quantity. Simple and stated in the UI.
DAYS_PER_MONTH = 30.0

# Chennai-region gazetteer for the demo. Unknown locations fall back to the
# city centroid and the UI is told the coordinate is approximate.
KNOWN_PLACES: dict[str, tuple[float, float]] = {}
for _src in loader.get_sources():
    KNOWN_PLACES[_src["location"].split(",")[0].strip().lower()] = (
        _src["latitude"],
        _src["longitude"],
    )
KNOWN_PLACES.setdefault("chennai", (13.0827, 80.2707))
KNOWN_PLACES.setdefault("chennai, tamil nadu", (13.0827, 80.2707))


def resolve_coordinates(location: str, latitude: float | None, longitude: float | None) -> tuple[float, float, bool]:
    """Return (lat, lng, is_exact). Demo gazetteer only - no external geocoder."""
    if latitude is not None and longitude is not None:
        return latitude, longitude, True
    key = (location or "").strip().lower()
    if key in KNOWN_PLACES:
        lat, lng = KNOWN_PLACES[key]
        return lat, lng, True
    for place, (lat, lng) in KNOWN_PLACES.items():
        if place and place in key:
            return lat, lng, True
    return 13.0827, 80.2707, False


def to_tonnes_per_month(quantity: float, unit: str, frequency: Frequency) -> float:
    """Normalise the user's quantity into tonnes per month."""
    value = float(quantity)
    unit = (unit or "tonnes").strip().lower()

    if unit in {"kg", "kgs", "kilogram", "kilograms", "kgs."}:
        value = value / 1000.0
    elif unit in {"g", "gram", "grams"}:
        value = value / 1_000_000.0
    elif unit in {"l", "litre", "litres", "liter", "liters"}:
        value = value / 1000.0 * 0.6  # demo assumption: loose waste ~0.6 t/m3
    elif unit in {"units", "pieces", "nos", "bags"}:
        value = value * 0.01  # demo assumption: ~10 kg per piece

    if frequency == Frequency.daily:
        value *= DAYS_PER_MONTH
    elif frequency == Frequency.weekly:
        value *= DAYS_PER_MONTH / 7.0
    elif frequency == Frequency.continuous:
        value *= 1.0  # the user is already stating a per-month continuous rate
    return round(value, 3)


def build_analysis(request: dict[str, Any]) -> dict[str, Any]:
    """Run the whole pipeline and return a serialisable analysis record."""
    analysis_id = f"an_{uuid.uuid4().hex[:10]}"
    warnings: list[str] = []

    lat, lng, exact = resolve_coordinates(request.get("location", ""), request.get("latitude"), request.get("longitude"))
    if not exact:
        warnings.append(
            f"'{request.get('location')}' is not in the demo gazetteer, so the city centroid was used. "
            "Distances below are approximate."
        )

    monthly = to_tonnes_per_month(request["quantity"], request.get("unit", "tonnes"), Frequency(request["frequency"]))
    if monthly <= 0:
        warnings.append("Quantity converted to zero tonnes/month. Check the unit you entered.")

    source = {
        "source_type": request["source_type"],
        "location": request.get("location") or "Chennai, Tamil Nadu",
        "latitude": lat,
        "longitude": lng,
        "quantity_t_per_month": monthly,
        "unit": request.get("unit", "tonnes"),
        "frequency": request["frequency"],
    }

    # --- AI identification (LLM, or deterministic fallback) -------------------
    ident = ai_identification.identify(
        description=request["material_description"],
        composition=request.get("composition"),
        attached_text=request.get("attached_text"),
        warnings=warnings,
    )
    material = get_material(ident.material_id)

    # Facts always come from the KB, never from the model.
    ident.category = material["category"]
    if not ident.reuse_categories:
        ident.reuse_categories = list(material["reuse_categories"])
    if ident.safety_level == "unknown" and material["safety_level"] != "unknown":
        ident.safety_level = material["safety_level"]
    if not ident.composition and request.get("composition"):
        from ai.fallback import parse_composition

        ident.composition = parse_composition(request["composition"])

    # --- Deterministic matching ----------------------------------------------
    candidates = loader.get_recipients()
    matches, excluded = engine.find_matches(
        analysis_id=analysis_id,
        material=material,
        identification=ident.model_dump(),
        source=source,
        candidates=candidates,
    )
    matches = engine.allocate_impact(matches, monthly)
    totals = engine.totals_for(matches, monthly, material)

    if ident.uncertainty_note:
        warnings.append(ident.uncertainty_note)
    if excluded:
        blocked = [e for e in excluded if e["reuse_type"] in {"RESTRICTED", "UNKNOWN"}]
        if blocked:
            warnings.append(
                f"{len(blocked)} recipient(s) were excluded by the safety layer, including "
                f"{blocked[0]['company_name']} ({blocked[0]['reason'][:90]}...)."
            )
    if not matches:
        warnings.append(
            "No compatible recipient was found in the demo dataset. Try a different material or increase the quantity."
        )
    elif totals["allocated_t_per_month"] <= 0:
        warnings.append(
            "Matching recipients exist, but the offered quantity is below every minimum. "
            "Aggregating volume with another source would unlock these routes."
        )

    analysis = {
        "id": analysis_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "raw_description": request["material_description"],
        "composition_raw": request.get("composition"),
        "attached_filename": request.get("attached_filename"),
        "identification": ident.model_dump(),
        "material": engine.material_record(material),
        "matches": [m.model_dump() for m in matches],
        "excluded": excluded,
        "totals": totals,
        "warnings": warnings,
        "seeded": False,
    }

    storage.save(analysis)
    return analysis


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    return storage.get(analysis_id)


def get_match(analysis_id: str, recipient_id: str) -> dict[str, Any] | None:
    analysis = storage.get(analysis_id)
    if not analysis:
        return None
    for match in analysis["matches"]:
        if match["recipient"]["id"] == recipient_id or match["id"].endswith(f":{recipient_id}"):
            return match
    return None


def find_match(match_id: str) -> dict[str, Any] | None:
    """`match_id` is 'analysis_id:recipient_id'."""
    if ":" not in match_id:
        return None
    analysis_id, recipient_id = match_id.split(":", 1)
    return get_match(analysis_id, recipient_id)


def materials_summary() -> list[dict[str, Any]]:
    return [engine.material_record(m) for m in MATERIALS_BY_ID.values()]


def seed_demo_analyses() -> list[dict[str, Any]]:
    """Pre-seed the primary demo scenario so the dashboard is never empty.

    Uses the exact same pipeline as a live request, so the seeded rows are
    genuinely computed rather than hand-written.
    """
    seeds = [
        {
            "source_type": SourceSector.industry.value,
            "material_description": (
                "Pulverised coal fly ash collected from the electrostatic precipitator of our "
                "thermal power station. Dry, fine grey powder, consistent quality."
            ),
            "quantity": 5.0,
            "unit": "tonnes",
            "location": "Manali, Chennai",
            "frequency": Frequency.monthly.value,
            "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
        },
        {
            "source_type": SourceSector.sme.value,
            "material_description": "Untreated teak and plywood sawdust and offcuts from our furniture workshop.",
            "quantity": 2.0,
            "unit": "tonnes",
            "location": "Perambur, Chennai",
            "frequency": Frequency.monthly.value,
            "composition": None,
        },
        {
            "source_type": SourceSector.household.value,
            "material_description": "Segregated corrugated cardboard and mixed paper from 240 apartments, baled weekly.",
            "quantity": 900.0,
            "unit": "kg",
            "location": "Anna Nagar, Chennai",
            "frequency": Frequency.monthly.value,
            "composition": None,
        },
    ]
    created = []
    for seed in seeds:
        try:
            analysis = build_analysis(seed)
            analysis["seeded"] = True
            storage.save(analysis)
            created.append(analysis)
        except Exception:  # noqa: BLE001 - a failed seed must never stop startup
            continue
    return created
