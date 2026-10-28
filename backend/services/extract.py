"""Deterministic field extraction from a waste report or a plain sentence.

Two rules shape this module:

  1. No model, no guessing. Every field carries the exact substring it was read
     from, so the UI can show *why* it filled a box in and the user can correct
     it. A wrong number that arrives with its evidence is recoverable; a wrong
     number that arrives looking authoritative is not.
  2. Nothing is defaulted here. If quantity or location cannot be found the
     field is reported as missing and the user is asked for it. The analysis
     pipeline has its own defaults and the UI shows them - silently applying
     them at extraction time would make it look like the report said so.

The material guess reuses `ai/fallback.classify`, the same keyword +
composition classifier the analysis falls back to. That keeps "what we read from
your file" and "what the pipeline would identify" the same calculation, so the
preview can never promise more than the run will deliver.
"""

from __future__ import annotations

import re

from ai.fallback import classify, parse_composition
from knowledge_base.materials import UNKNOWN_MATERIAL_ID
from services.analysis import KNOWN_PLACES

# Units we accept, normalised to the vocabulary AnalyzeRequest expects.
UNIT_ALIASES = {
    "t": "tonnes",
    "tonne": "tonnes",
    "tonnes": "tonnes",
    "ton": "tonnes",
    "tons": "tonnes",
    "mt": "tonnes",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "l": "litres",
    "litre": "litres",
    "litres": "litres",
    "liter": "litres",
    "liters": "litres",
    "unit": "units",
    "units": "units",
    "bags": "units",
    "trips": "units",
}

_QUANTITY_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(tonnes?|tons?|metric\s+tons?|mt|kgs?|kilograms?|lit(?:re|er)s?|units?|bags?|trips?|t)\b",
    re.IGNORECASE,
)

FREQUENCY_PATTERNS: list[tuple[str, str, str]] = [
    # (value, human label, pattern)
    ("continuous", "Continuous", r"\bcontinu(?:ous|ously)\b|\b24\s*/\s*7\b|\baround the clock\b|\bnon-?stop\b"),
    ("daily", "Daily", r"\b(?:per|a|each|every|/)\s*day\b|\bdaily\b|\bper\s*annum\s*per\s*day\b"),
    ("weekly", "Weekly", r"\b(?:per|a|each|every|/)\s*week\b|\bweekly\b"),
    ("monthly", "Monthly", r"\b(?:per|a|each|every|/)\s*month\b|\bmonthly\b|\bmonth-?wise\b"),
    ("one_time", "One-time", r"\bone[- ]time\b|\bsingle\s+(?:load|trip|shipment|delivery)\b|\boccasional(?:ly)?\b"),
]

SOURCE_TYPE_PATTERNS: list[tuple[str, str, str]] = [
    (
        "industry",
        "Industrial source",
        r"\b(?:plant|factory|refinery|mill|foundry|manufactur\w*|industrial|boiler|precipitator|shop\s*floor|"
        r"process(?:ing)?\s*(?:unit|line)|workshop\s*unit|power\s+station|generation\s+station|kiln|quarry|"
        r"smelt\w*|extraction\s+unit)\b",
    ),
    ("sme", "Small / medium enterprise", r"\b(?:sme|small[- ]scale|artisan|cottage\s*industry|micro\s*enterprise)\b"),
    (
        "agriculture",
        "Farm / agricultural",
        r"\b(?:farm(?:ers?|ing)?|agriculture|agricultural|husbandry|plantation|paddy|harvest\w*)\b",
    ),
    (
        "construction",
        "Construction / demolition site",
        r"\b(?:construction\s+site|demolition|site\s*works|builder|infra(?:structure)?\s*project)\b",
    ),
    (
        "municipality",
        "Municipal / ward",
        r"\b(?:municipal(?:ity)?|corporation|ulb|\bward\s*\d+|city\s*municipal|garbage\s*collection\s*area)\b",
    ),
    (
        "household",
        "Household / community",
        r"\b(?:household|apartment\w*|residential|housing\s*society|gated\s*community|villa|domestic|"
        r"apartment\s*complex|housing\s*board)\b",
    ),
]

# Words that mean "handle this carefully". These are flags, not conclusions:
# the safety layer in matching/engine.py decides what a route may do, and it
# reads the material record rather than this list. Surfacing them here is only
# so the user sees that the report mentioned them.
SAFETY_MARKERS = (
    "hazardous",
    "toxic",
    "carcinogenic",
    "asbestos",
    "contaminated",
    "contamination",
    "heavy metal",
    "lead",
    "mercury",
    "radioactive",
    "oil-contaminated",
    "biohazard",
    "infectious",
    "cyanide",
    "acidic",
    "caustic",
    "licensed handling",
    "ewaste",
    "e-waste",
)


_NEGATION_RE = re.compile(
    r"\b(?:no|not|none|never|without|free\s+of|absent|non|lacks?|does\s+not|cannot|zero|tested?\s+clean)\b",
    re.IGNORECASE,
)


def _evidence(text: str, start: int, end: int, window: int = 48) -> str:
    """A readable slice of the source around a match, for the review panel."""
    lo, hi = max(0, start - window), min(len(text), end + window)
    snippet = " ".join(text[lo:hi].split())
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def _number(raw: str) -> float | None:
    """Parse a count that may use thousands separators or a decimal comma.

    '1,200' is one thousand two hundred; '5,5' is five and a half. The rule is
    the one Indian and most European documents follow, and it is stated here so
    a reviewer can disagree with it.
    """
    cleaned = raw.strip()
    if "," in cleaned and re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", cleaned):
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".", 1)
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return round(value, 4) if value > 0 else None


def _field(value: object, evidence: str | None = None, note: str | None = None) -> dict:
    return {"value": value, "evidence": evidence, "found": value is not None and value != {}, "note": note}


# The user-editable fields, in the order the review form shows them. Kept here
# so the API, this module and the UI agree on one list.
FIELD_KEYS = ("quantity", "unit", "frequency", "location", "source_type")


def extract_fields(text: str | None) -> dict:
    """Pull out material, quantity, unit, frequency, location, composition, source.

    Flat on purpose: one key per field, plus `composition`, `material`,
    `safety_flags`, `missing`, `notes` and `description`. Nesting a "fields"
    group inside a response that is itself called "fields" only produces code
    that reads `body["fields"]["fields"]["quantity"]`.
    """
    source = " ".join((text or "").split())
    notes: list[str] = []

    if not source:
        return {
            **{name: _field(None) for name in FIELD_KEYS},
            "composition": _field({}),
            "material": _field(None),
            "safety_flags": [],
            "missing": ["quantity", "location", "material"],
            "notes": ["No text to read."],
            "description": "",
        }

    # --- quantity + unit -----------------------------------------------------
    quantity: float | None = None
    unit: str | None = None
    quantity_evidence: str | None = None
    match = _QUANTITY_RE.search(source)
    if match:
        quantity = _number(match.group(1))
        raw_unit = match.group(2).lower().replace(" ", "")
        unit = UNIT_ALIASES.get(raw_unit) or UNIT_ALIASES.get(raw_unit.rstrip("s"), "tonnes")
        quantity_evidence = _evidence(source, match.start(), match.end())
        if quantity is None:
            notes.append("A number was found but could not be read as a quantity, so it was left for you to enter.")
    else:
        # A bare count next to a unit word on separate lines still counts.
        loose = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(?:tonnes|tons|kg|litres|liters)\b", source, re.IGNORECASE)
        if loose:
            quantity = _number(loose.group(1))
            quantity_evidence = _evidence(source, loose.start(), loose.end())
            notes.append("Unit could not be read from the number, so 'tonnes' is assumed - check it.")
            unit = "tonnes"

    # --- frequency -----------------------------------------------------------
    frequency: str | None = None
    frequency_evidence: str | None = None
    for value, label, pattern in FREQUENCY_PATTERNS:
        found = re.search(pattern, source, re.IGNORECASE)
        if found:
            frequency, frequency_evidence = value, _evidence(source, found.start(), found.end())
            break
    if frequency is None and quantity is not None:
        notes.append("No delivery frequency was found. Per-month figures are assumed, so a total can look too high.")

    # --- location ------------------------------------------------------------
    # Only places the demo gazetteer can geocode are offered, so a location that
    # survives to the analysis always has real coordinates behind it.
    location: str | None = None
    location_evidence: str | None = None
    lowered = source.lower()
    for place in sorted(KNOWN_PLACES, key=len, reverse=True):
        found = re.search(rf"\b{re.escape(place)}\b", lowered)
        if found:
            location = place.title()
            location_evidence = _evidence(source, found.start(), found.end())
            break

    # --- source type ---------------------------------------------------------
    source_type: str | None = None
    source_type_evidence: str | None = None
    for value, label, pattern in SOURCE_TYPE_PATTERNS:
        found = re.search(pattern, source, re.IGNORECASE)
        if found:
            source_type, source_type_evidence = value, _evidence(source, found.start(), found.end())
            break

    # --- composition ---------------------------------------------------------
    composition = parse_composition(source)

    # --- safety markers -----------------------------------------------------
    # Negation-blind matching would flag "No hazardous constituents detected" as
    # a hazard, which is worse than saying nothing, so a small windowed check
    # skips markers that the sentence just took back. It is not full negation
    # scope resolution - it only has to handle report prose.
    safety_flags: list[dict] = []
    for marker in SAFETY_MARKERS:
        for found in re.finditer(rf"\b{re.escape(marker)}\b", source, re.IGNORECASE):
            clause = source[max(0, found.start() - 28) : found.start()].rsplit(".", 1)[-1]
            if _NEGATION_RE.search(clause):
                continue
            safety_flags.append({"marker": marker, "evidence": _evidence(source, found.start(), found.end())})
            break

    # --- material guess (same classifier the pipeline falls back to) --------
    guess = classify(source, None, None)
    material_id = guess["material_id"]
    material = _field(
        {"name": guess["material"], "material_id": material_id, "confidence": guess["confidence"]},
        evidence=guess.get("reasoning"),
        note=None if material_id != UNKNOWN_MATERIAL_ID else guess.get("uncertainty_note"),
    )

    fields = {
        "quantity": _field(quantity, quantity_evidence),
        "unit": _field(unit, quantity_evidence),
        "frequency": _field(frequency, frequency_evidence),
        "location": _field(location, location_evidence),
        "source_type": _field(source_type, source_type_evidence),
    }
    # `unit` rides along with `quantity`; asking for both would be noise, and the
    # review form edits them in one row anyway.
    missing = [name for name, value in fields.items() if not value["found"] and name != "unit"]
    if material_id == UNKNOWN_MATERIAL_ID:
        missing.append("material")
    if not composition:
        notes.append("No oxide percentages were found. Composition is optional, but it sharpens identification.")
    if safety_flags:
        notes.append(
            f"{len(safety_flags)} caution word(s) found ({', '.join(f['marker'] for f in safety_flags[:3])}). "
            "The safety layer decides routing - these words are only shown so nothing is missed."
        )

    return {
        **fields,
        "composition": _field(composition, None),
        "material": material,
        "safety_flags": safety_flags,
        "missing": missing,
        "notes": notes,
        "description": source[:1200],
    }
