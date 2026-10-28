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
from services import completeness, storage

# Days per month used to normalise quantity. Simple and stated in the UI.
DAYS_PER_MONTH = 30.0

# The places this build can place on a map: every seeded source locality, plus the
# city those localities sit in. It is a gazetteer, not a default. A location that is
# not in it keeps the text the user typed and has NO coordinates - it is never
# replaced by another city, because a wrong coordinate silently becomes a wrong
# distance, a wrong haulage estimate and a wrong ranking.
KNOWN_PLACES: dict[str, tuple[float, float]] = {}
for _src in loader.get_sources():
    KNOWN_PLACES[_src["location"].split(",")[0].strip().lower()] = (
        _src["latitude"],
        _src["longitude"],
    )
KNOWN_PLACES.setdefault("chennai", (13.0827, 80.2707))
KNOWN_PLACES.setdefault("chennai, tamil nadu", (13.0827, 80.2707))


def resolve_coordinates(
    location: str | None, latitude: float | None, longitude: float | None
) -> tuple[float | None, float | None, bool]:
    """Return ``(lat, lng, is_exact)``. See `resolve_coordinates_detailed`."""
    lat, lng, exact, _info = resolve_coordinates_detailed(location, latitude, longitude)
    return lat, lng, exact


def resolve_coordinates_detailed(
    location: str | None, latitude: float | None, longitude: float | None
) -> tuple[float | None, float | None, bool, dict[str, Any]]:
    """Return ``(lat, lng, is_exact, provenance)`` for the location someone stated.

    Three steps, in this order, and no fourth:

    1. coordinates the caller gave are used exactly as given;
    2. a place this build already knows (the seeded localities) resolves to its own
       recorded point;
    3. a place nobody has recorded is put to the external geocoder, if one is
       configured - and only if it answers does anything become a coordinate.

    Otherwise the location stays exactly what was typed, with no coordinates and
    `is_exact` false. The rule this function exists to keep is that Symbio never
    produces a coordinate for a place it cannot actually find: a wrong point becomes a
    wrong distance, then a wrong haulage estimate, then a wrong recommendation.
    """
    if latitude is not None and longitude is not None:
        return float(latitude), float(longitude), True, {"source": "coordinates as given"}
    key = (location or "").strip().lower()
    # 'Manali, Chennai' arrives as comma-separated parts, so parts are what get
    # looked up. Matching on loose substrings would resolve 'Chennaiyur' - a different
    # place that happens to contain the word - to the city centroid, which is exactly
    # the silent substitution this file exists to prevent.
    parts = [part.strip() for part in key.split(",") if part.strip()] or ([key] if key else [])
    for part in parts:
        if part in KNOWN_PLACES:
            return KNOWN_PLACES[part][0], KNOWN_PLACES[part][1], True, {"source": "recorded place"}
    for place, (lat, lng) in KNOWN_PLACES.items():
        if not place:
            continue
        if any(part == place or part.startswith(f"{place} ") or part.startswith(f"{place}-") for part in parts):
            return lat, lng, True, {"source": "recorded place"}

    from services import geo  # noqa: PLC0415 - optional by design, so import it late

    if not key or geo.geocoding_provider() == "off":
        return None, None, False, {"source": "unresolved", "reason": "no geography service configured"}
    result = geo.geocode(location or "")
    if result.ok:
        payload = result.payload
        return (
            float(payload["latitude"]),
            float(payload["longitude"]),
            True,
            {
                "source": "external geocoding",
                "matched_as": payload.get("display_name") or "",
                "fetched_at": payload.get("fetched_at") or "",
            },
        )
    return None, None, False, {"source": "unresolved", "reason": result.reason or "not found", "asked": True}


GEOGRAPHY_FAILURE_NOTE = {
    "timeout": "the geography service did not answer in time",
    "rate limited": "the geography service is throttling requests right now",
    "not found": "no map source could place that name",
    "invalid response": "the geography service returned something unreadable",
    "unreachable": "the geography service could not be reached",
    "cooling down": "the geography service has been set aside for a minute after failing",
    "unsupported provider": "the geography service configured here is not one Symbio knows",
    "unconfigured": "the geography service is configured without its key",
}


def place_fields(location: str | None) -> dict[str, Any]:
    """The fields a record needs in order to state a place honestly.

    Used by facilities and listings, which are places too, and by exactly the same rule
    as an analysis: text is always kept, and coordinates appear only if the recorded
    network or a configured geocoder actually resolves them. `location_source` says
    which it was, because "who placed this" is a fact a reader can check (§7).
    """
    text = (location or "").strip()
    lat, lng, exact, info = resolve_coordinates_detailed(text, None, None)
    source = str(info.get("source") or "unresolved")
    if exact and source == "recorded place":
        note = "coordinates taken from the place recorded for this location"
    elif exact and source == "external geocoding":
        note = "coordinates from an external place lookup" + (
            f", matched as {info['matched_as']}" if info.get("matched_as") else ""
        )
    elif exact:
        note = "coordinates as given"
    else:
        note = "no coordinates for this place - it is matched on material, quantity and price, not distance"
    return {
        "location": text or None,
        "latitude": lat,
        "longitude": lng,
        "location_resolved": exact,
        "location_source": source if exact else "unresolved",
        "location_note": note,
    }


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


def _owner() -> str | None:
    """The organisation an analysis belongs to, if anyone was signed in.

    Both the main run and a scenario variant are saved; both belong to whoever ran
    them, and a variant saved without an owner would leak a tenant's figures into the
    public pool.
    """
    from services import request_scope  # noqa: PLC0415 - the store has no request of its own

    return request_scope.organization_id()


def build_analysis(request: dict[str, Any]) -> dict[str, Any]:
    """Run the whole pipeline and return a serialisable analysis record."""
    analysis_id = f"an_{uuid.uuid4().hex[:10]}"
    warnings: list[str] = []

    stated_location = (request.get("location") or "").strip()
    lat, lng, exact, place_info = resolve_coordinates_detailed(
        stated_location, request.get("latitude"), request.get("longitude")
    )
    if not exact:
        note = (
            f"'{stated_location}' is not a place Symbio can place on a map, so this analysis has no coordinates. "
            "Distances, haulage estimates and the distance part of every score are left uncalculated rather than "
            "measured from another city - the location text you entered still stands and every other component is scored."
        )
        reason = str(place_info.get("reason") or "")
        if place_info.get("asked") and reason in GEOGRAPHY_FAILURE_NOTE:
            # Say which kind of unavailability this is, in words, so a reader knows
            # whether to fix the place name or try again later.
            note += f" The place name was also put to the geography service: {GEOGRAPHY_FAILURE_NOTE[reason]}."
        warnings.append(note)

    monthly = to_tonnes_per_month(request["quantity"], request.get("unit", "tonnes"), Frequency(request["frequency"]))
    if monthly <= 0:
        warnings.append("Quantity converted to zero tonnes/month. Check the unit you entered.")

    source = {
        "source_type": request["source_type"],
        # Exactly what the user stated. Never defaulted to a city.
        "location": stated_location,
        "latitude": lat,
        "longitude": lng,
        # Whether the place could be placed. `False` means the coordinates below are
        # null on purpose, and every distance-dependent figure says so too.
        "location_resolved": exact,
        # Who placed it, for the provenance panel: `coordinates as given`,
        # `recorded place`, `external geocoding`, or `unresolved`.
        "location_source": str(place_info.get("source") or "unresolved"),
        "location_matched_as": place_info.get("matched_as") or None,
        "location_checked_at": place_info.get("fetched_at") or None,
        "quantity_t_per_month": monthly,
        "unit": request.get("unit", "tonnes"),
        "frequency": request["frequency"],
        # Optional detail travels with the source so a what-if re-runs against the
        # same picture rather than silently degrading to the required fields only.
        "physical_state": request.get("physical_state"),
        "moisture_percent": request.get("moisture_percent"),
        "contaminants": list(request.get("contaminants") or []),
        "intended_use": request.get("intended_use"),
    }

    # --- AI identification (LLM, or deterministic fallback) -------------------
    ident = ai_identification.identify(
        description=request["material_description"],
        composition=request.get("composition"),
        attached_text=request.get("attached_text"),
        warnings=warnings,
    )

    # --- human-in-the-loop correction --------------------------------------
    # The user may override what the model read, using a knowledge-base material
    # id. The override changes the identity only: the knowledge base, the safety
    # layer and the matching engine run exactly as they would have anyway, so a
    # correction cannot be used to talk the system into an unsafe route.
    user_corrected = False
    requested_override = request.get("material_override_id")
    if requested_override:
        chosen = MATERIALS_BY_ID.get(requested_override)
        if not chosen:
            raise ValueError(
                f"'{requested_override}' is not a material in the Symbio knowledge base. "
                "Only known materials can be selected."
            )
        previous = ident.material
        ident = ident.model_copy(
            update={
                "material": chosen["name"],
                "material_id": chosen["id"],
                "engine": "user_correction",
                "confidence": 1.0,
                "reasoning": (
                    f"Material selected by the user from the knowledge base. The system had read the "
                    f"description as '{previous}'."
                ),
                "uncertainty_note": None,
            }
        )
        user_corrected = True
        warnings.append(
            f"Material manually corrected by user: {chosen['name']} (identified as {previous} before correction)."
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
        "user_corrected": user_corrected,
        "seeded": False,
    }

    # §3 last, because it reads the outcome: completeness is about the input, but
    # the cross-checks are only meaningful against the partners that survived the
    # safety layer. Declared contamination writes cautions onto those matches - it
    # can add a requirement, never remove one.
    declared_contaminants = list(request.get("contaminants") or [])
    if declared_contaminants:
        analysis["contaminant_cautions_applied"] = completeness.apply_declared_contaminants(
            analysis["matches"], declared_contaminants
        )

    analysis["completeness"] = completeness.assess(
        {**request, **{"location": source["location"], "quantity": request["quantity"]}},
        material,
        candidates,
        matched_recipients=[m.recipient.model_dump() for m in matches],
    )

    storage.save(analysis, owner=_owner())
    return analysis


def build_scenario(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Re-run matching for a temporary "what if" of a stored analysis.

    Same engine, same safety layer, same weights - only the source record
    changes. The analysis passed in is never mutated and nothing is written to
    storage, so "reset" is simply "stop showing the scenario".
    """
    source = dict(base["source"])
    warnings: list[str] = []
    changed: dict[str, Any] = {}

    frequency = overrides.get("frequency") or source["frequency"]
    stated_quantity = overrides.get("quantity")
    stated_unit = overrides.get("unit") or source.get("unit") or "tonnes"
    if stated_quantity is None and overrides.get("frequency") and overrides["frequency"] != source["frequency"]:
        # Only the cadence changed: read the current monthly figure as the amount
        # arriving per period, then normalise it again. Without this rule a
        # frequency edit would silently do nothing.
        stated_quantity = float(source["quantity_t_per_month"])
        stated_unit = "tonnes"

    if stated_quantity is None:
        monthly = float(source["quantity_t_per_month"])
    else:
        monthly = to_tonnes_per_month(stated_quantity, stated_unit, Frequency(frequency))
    if monthly <= 0:
        warnings.append("The scenario quantity converts to zero tonnes/month - no route can be scored against it.")

    if overrides.get("frequency") and frequency != source["frequency"]:
        changed["frequency"] = {"from": source["frequency"], "to": frequency}
    if abs(monthly - float(source["quantity_t_per_month"])) > 1e-9:
        # Report the effect in the unit the engine actually ranks on, whatever
        # the user touched: a cadence change lands here too.
        changed["quantity"] = {
            "from": f"{source['quantity_t_per_month']} t/month",
            "to": f"{monthly} t/month",
        }

    location = overrides.get("location") or source["location"]
    lat, lng, exact, place_info = resolve_coordinates_detailed(location, None, None)
    if location != source["location"]:
        changed["location"] = {"from": source["location"], "to": location}
        if not exact:
            note = (
                f"'{location}' is not in the recorded gazetteer, so this scenario has no coordinates for it. "
                "Distances and haulage are left uncalculated rather than measured from another city."
            )
            reason = str(place_info.get("reason") or "")
            if place_info.get("asked") and reason in GEOGRAPHY_FAILURE_NOTE:
                note += f" The place name was also put to the geography service: {GEOGRAPHY_FAILURE_NOTE[reason]}."
            warnings.append(note)
    scenario_source = {
        **source,
        "location": location,
        "latitude": lat,
        "longitude": lng,
        "location_resolved": exact,
        # Who placed it, for the provenance panel: `coordinates as given`,
        # `recorded place`, `external geocoding`, or `unresolved`.
        "location_source": str(place_info.get("source") or "unresolved"),
        "location_matched_as": place_info.get("matched_as") or None,
        "location_checked_at": place_info.get("fetched_at") or None,
        "quantity_t_per_month": monthly,
        "frequency": frequency,
    }

    material = get_material(base["identification"]["material_id"])
    identification = dict(base["identification"])
    candidates = loader.get_recipients()
    scenario_id = base["id"]
    matches, excluded = engine.find_matches(
        analysis_id=scenario_id,
        material=material,
        identification=identification,
        source=scenario_source,
        candidates=candidates,
    )
    matches = engine.allocate_impact(matches, monthly)
    totals = engine.totals_for(matches, monthly, material)

    scenario = {
        "id": scenario_id,
        "scenario": True,
        "created_at": base["created_at"],
        "source": scenario_source,
        "raw_description": base["raw_description"],
        "composition_raw": base.get("composition_raw"),
        "attached_filename": base.get("attached_filename"),
        "identification": identification,
        "material": engine.material_record(material),
        "matches": [m.model_dump() for m in matches],
        "excluded": excluded,
        "totals": totals,
        "warnings": warnings,
        "changed": changed,
        "user_corrected": base.get("user_corrected", False),
        "seeded": base.get("seeded", False),
        # Same rule in a scenario: contamination that was declared on the real
        # analysis is still declared here, so the caution has to survive the what-if.
        # §3: recomputed from the same inputs rather than copied, so a scenario that
        # clears a field reports a lower completeness for itself.
        "completeness": completeness.assess(
            {
                "material_description": base["raw_description"],
                "composition": base.get("composition_raw"),
                "quantity": monthly,
                "unit": "tonnes",
                "location": location,
                "frequency": frequency,
                "physical_state": source.get("physical_state"),
                "moisture_percent": source.get("moisture_percent"),
                "contaminants": source.get("contaminants") or [],
                "intended_use": source.get("intended_use"),
            },
            material,
            candidates,
            matched_recipients=[m.recipient.model_dump() for m in matches],
        ),
    }
    # A what-if inherits the caution, not just the score: contamination declared on
    # the real analysis is still contamination here.
    scenario_contaminants = list(source.get("contaminants") or [])
    if scenario_contaminants:
        completeness.apply_declared_contaminants(scenario["matches"], scenario_contaminants)
    return scenario


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
            # Optional detail, so the demo opens on a profile that is not empty.
            "physical_state": "powder",
            "moisture_percent": 1.2,
            "intended_use": "cement replacement in concrete blocks",
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
            "physical_state": "solid",
            "contaminants": ["plastic strapping tape", "food residue on two bales"],
        },
    ]
    created = []
    for seed in seeds:
        try:
            analysis = build_analysis(seed)
            analysis["seeded"] = True
            storage.save(analysis, owner=_owner())
            created.append(analysis)
        except Exception:  # noqa: BLE001 - a failed seed must never stop startup
            continue
    return created
