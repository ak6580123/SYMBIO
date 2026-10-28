"""How much of the picture the engine was actually given (§3).

Two things are deliberately separated here:

* **Completeness** - a percentage and a list of what is missing. It is a statement
  about the *input*, never a modifier of the ranking. A thin description still gets
  real matches, with the uncertainty shown next to them rather than hidden inside
  the score.
* **Insights** - what a field that *was* supplied changes downstream. These are
  deterministic cross-checks against the knowledge base and against each recipient's
  recorded processing capability, so "your slurry arrives at 55% moisture and three
  of the eight partners record no drying capability" is a fact about the seeded data,
  not a generated platitude.

Nothing in this module can widen a safety decision. A declared contaminant can only
ever add a caution or a testing requirement; an absent one never removes the caution
the safety layer already applied.
"""

from __future__ import annotations

from typing import Any

# --- demo thresholds, documented as constants so a test can pin them ---------
WET_TONNE_THRESHOLD_PERCENT = 20.0
"""Above this, a stream that the knowledge base calls moisture-sensitive is treated
as arriving wet for the purpose of the drying-capacity check."""

MOISTURE_SENSITIVE_PROPERTIES = {"high_moisture", "moisture_sensitive", "hygroscopic", "fine_particle"}
CONTAMINANT_PROPERTIES = {"trace_contaminants", "hazardous_residue", "putrescible"}

# What a physical form needs on the receiving side before it can be taken in at all.
# Each entry is a set of capability *substrings* because recipient capability lists are
# free-form in the seed data ("slip_preparation", "dewatering_press").
STATE_HANDLING: dict[str, tuple[str, ...]] = {
    "liquid": ("silo", "pump", "slip", "tank"),
    "sludge": ("dewater", "dry", "wash", "press", "curing"),
    "powder": ("silo", "blend", "grind", "mill"),
    "granular": ("screen", "convey", "blend", "crush"),
    "solid": ("crush", "shred", "cut", "sort", "yard"),
}

CONTAMINANT_TESTING_CAPABILITIES = ("lab", "test", "analysis", "separation", "sorting", "licensed_handling")


class FieldSpec:
    """One input, what it is worth to the analysis, and what it changes."""

    __slots__ = ("key", "label", "weight", "group", "why", "changes", "optional_advice")

    def __init__(
        self,
        key: str,
        label: str,
        weight: float,
        group: str,
        why: str,
        changes: str,
        optional_advice: str | None = None,
    ) -> None:
        self.key = key
        self.label = label
        self.weight = weight
        self.group = group
        self.why = why
        self.changes = changes
        self.optional_advice = optional_advice


# Weights sum to 100 and split into the jobs the pipeline actually does: read the
# material (34), score the fit (30), screen it for handling (18) and for safety (18).
FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "material_description",
        "Material description",
        20,
        "identification",
        "What the model and the fallback classifier both read.",
        "changes which material the knowledge base resolves",
    ),
    FieldSpec(
        "composition",
        "Composition notes",
        14,
        "identification",
        "A second signal for the identification, and the one that raises confidence "
        "above a keyword match.",
        "changes identification confidence, not the score",
        "Add one line on composition (for example 'Class F, loss on ignition under 5%'). "
        "It is the difference between a keyword guess and a confident identification.",
    ),
    FieldSpec(
        "quantity",
        "Quantity",
        12,
        "scoring",
        "Normalised to tonnes/month and compared with each partner's intake window.",
        "changes the quantity component of every score",
    ),
    FieldSpec(
        "location",
        "Location",
        12,
        "scoring",
        "Drives the distance component and the map.",
        "changes the distance component of every score",
    ),
    FieldSpec(
        "frequency",
        "How often it arrives",
        6,
        "scoring",
        "Decides how a stated quantity converts to tonnes/month.",
        "changes the quantity component of every score",
    ),
    FieldSpec(
        "physical_state",
        "Physical state",
        8,
        "handling",
        "Powder, sludge, liquid or solid decides what a receiver has to be able to do "
        "with the load before it is even weighed in.",
        "adds handling notes; never changes a score",
        "Say whether it arrives as powder, granules, sludge, liquid or solid lumps. "
        "Partners with no matching handling capability are flagged instead of quietly ranked.",
    ),
    FieldSpec(
        "moisture_percent",
        "Moisture",
        10,
        "handling",
        "Water is weight you pay to move and, for moisture-sensitive materials, a "
        "processing step someone has to own.",
        "adds drying-capacity notes; never changes a score",
        "Give a moisture percentage. A wet stream costs the same freight per tonne as a "
        "dry one, and the partner that has to dry it needs to know before you call.",
    ),
    FieldSpec(
        "contaminants",
        "Known contaminants",
        12,
        "safety",
        "The safety layer runs on this: declared contaminants can only tighten what a "
        "route requires, never loosen it.",
        "can only add a safety caution or a testing requirement",
        "List anything known to be in it - oil, paint, plasterboard, food residue. "
        "Naming it never removes a caution; leaving it out does not make the route safe.",
    ),
    FieldSpec(
        "intended_use",
        "Intended use",
        6,
        "safety",
        "What you were already planning to do with it, checked against the reuse "
        "applications the knowledge base records.",
        "adds an application note; never changes a score",
        "If you already have a use in mind, say so - the ranking ignores it, but a "
        "partner that already makes that product is worth calling first.",
    ),
)

SPEC_BY_KEY = {spec.key: spec for spec in FIELD_SPECS}

LEVELS = (
    (85.0, "complete"),
    (65.0, "solid"),
    (40.0, "workable"),
    (0.0, "thin"),
)


def _provided(request: dict[str, Any], key: str) -> Any:
    """The raw value, or None when the field is effectively empty."""
    value = request.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (list, tuple)):
        return list(value) or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 0 is a real answer for moisture, but a 0-tonne quantity is not an input.
        return value
    return value


def _capable(recipient: dict[str, Any], needles: tuple[str, ...]) -> bool:
    capabilities = [str(c).lower() for c in recipient.get("processing_capability") or []]
    return any(needle in capability for capability in capabilities for needle in needles)


def assess(
    request: dict[str, Any],
    material: dict[str, Any],
    recipients: list[dict[str, Any]],
    matched_recipients: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score completeness and derive the insights the supplied fields unlock.

    `recipients` is the pool the engine scored; `matched_recipients` is the subset
    that survived safety, so an insight that says "three partners" means three
    partners the user can actually see.
    """
    pool = matched_recipients if matched_recipients is not None else recipients

    values = {spec.key: _provided(request, spec.key) for spec in FIELD_SPECS}
    percent = round(sum(spec.weight for spec in FIELD_SPECS if values[spec.key] is not None), 1)
    level = next(label for floor, label in LEVELS if percent >= floor)

    fields: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for spec in FIELD_SPECS:
        value = values[spec.key]
        entry = {
            "key": spec.key,
            "label": spec.label,
            "weight": spec.weight,
            "group": spec.group,
            "provided": value is not None,
            "value": value,
            "why": spec.why,
            "changes": spec.changes,
        }
        fields.append(entry)
        if value is None:
            missing.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "weight": spec.weight,
                    "group": spec.group,
                    "advice": spec.optional_advice or spec.why,
                    "changes": spec.changes,
                }
            )

    insights = _insights(values, material, pool)
    advice = [item["advice"] for item in missing if item["group"] != "identification" or item["key"] == "composition"]
    if not missing:
        advice = ["Nothing outstanding - every field the pipeline reads has a value."]

    return {
        "percent": percent,
        "level": level,
        "fields": fields,
        "missing": missing,
        "insights": insights,
        "advice": advice,
        "blocks_analysis": False,
        "note": (
            "Completeness describes the input, not the ranking. Every score below was "
            "computed by the same deterministic engine with the fields that were present."
        ),
    }



def apply_declared_contaminants(matches: list[dict[str, Any]], contaminants: list[str]) -> int:
    """Add the caution a declared contaminant earns. Tightening only, always.

    Called after matching and before storage. It changes no score, no ordering and
    no safety level; it writes one line into `cautions` on the affected matches,
    because a route the sender knows is contaminated has to say so on the route.
    Returns how many matches were touched, which is what the tests pin.
    """
    named = [str(c).strip() for c in (contaminants or []) if str(c).strip()]
    if not named:
        return 0
    listing = ", ".join(named)
    touched = 0
    for match in matches:
        recipient = match.get("recipient") or {}
        capabilities = " ".join(str(c).lower() for c in recipient.get("processing_capability") or [])
        can_test = any(word in capabilities for word in CONTAMINANT_TESTING_CAPABILITIES)
        direct = match.get("reuse_type") == "DIRECT_REUSE"
        caution = (
            f"Source declared contaminants ({listing}); "
            + (
                f"{recipient.get('company_name', 'this partner')} records its own screening or testing step, "
                "so ask for the result before collection"
                if can_test
                else f"{recipient.get('company_name', 'this partner')} records no testing or separation "
                "capability, so this load needs third-party clearance first"
            )
            + (
                " - and this route is direct reuse, which means the material goes in as it arrives"
                if direct
                else ""
            )
            + "."
        )
        cautions = match.setdefault("cautions", [])
        if caution not in cautions:
            cautions.append(caution)
            touched += 1
    return touched

def _insights(values: dict[str, Any], material: dict[str, Any], pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic cross-checks on what the user *did* supply."""
    insights: list[dict[str, Any]] = []
    names = [str(r.get("company_name") or r.get("id")) for r in pool]

    # --- moisture against drying capacity -----------------------------------
    moisture = values.get("moisture_percent")
    properties = set(material.get("properties") or [])
    if moisture is not None:
        sensitive = bool(properties & MOISTURE_SENSITIVE_PROPERTIES)
        if float(moisture) >= WET_TONNE_THRESHOLD_PERCENT and sensitive:
            wet = [r for r in pool if not _capable(r, ("dry", "dewater", "wash", "press"))]
            insights.append(
                {
                    "field": "moisture_percent",
                    "tone": "warn" if wet else "info",
                    "title": f"{float(moisture):g}% moisture on a material the knowledge base calls moisture-sensitive",
                    "note": (
                        f"{len(wet)} of {len(pool)} partners in range record no drying or dewatering "
                        "capability"
                        if wet
                        else "Every partner in range records a drying, dewatering or washing step, so the "
                        "moisture figure does not rule anyone out."
                    ),
                    "affects": "explanation and who you call first - not the score",
                    "affected_recipients": [str(r.get("company_name")) for r in wet],
                    "value": float(moisture),
                    "unit": "percent",
                }
            )
        elif float(moisture) >= WET_TONNE_THRESHOLD_PERCENT:
            insights.append(
                {
                    "field": "moisture_percent",
                    "tone": "info",
                    "title": f"{float(moisture):g}% moisture",
                    "note": "The knowledge base does not treat this material as moisture-sensitive, so the "
                    "figure is recorded but rules nobody out.",
                    "affects": "nothing in the ranking",
                    "affected_recipients": [],
                    "value": float(moisture),
                    "unit": "percent",
                }
            )

    # --- physical state against handling capability -------------------------
    state = values.get("physical_state")
    if state:
        needle = STATE_HANDLING.get(str(state).lower())
        if needle:
            unhandled = [r for r in pool if not _capable(r, needle)]
            insights.append(
                {
                    "field": "physical_state",
                    "tone": "warn" if unhandled else "info",
                    "title": f"Arrives as {state}",
                    "note": (
                        f"{len(unhandled)} of {len(pool)} partners record no handling step that suits a "
                        f"{state} stream"
                        if unhandled
                        else f"Every partner in range records a handling step suited to a {state} stream"
                    ),
                    "affects": "explanation only - the engine has no handling score",
                    "affected_recipients": [str(r.get("company_name")) for r in unhandled],
                    "value": str(state),
                }
            )
        else:
            insights.append(
                {
                    "field": "physical_state",
                    "tone": "info",
                    "title": f"Arrives as {state}",
                    "note": "That form is not in the handling table this build ships with, so no capability "
                    "check was run against it.",
                    "affects": "nothing",
                    "affected_recipients": [],
                    "value": str(state),
                }
            )

    # --- declared contaminants: tighten, never relax -------------------------
    contaminants = values.get("contaminants")
    if contaminants:
        untested = [r for r in pool if not _capable(r, CONTAMINANT_TESTING_CAPABILITIES)]
        direct = [r for r in pool if r.get("reuse_type") == "DIRECT_REUSE"]
        parts = []
        if direct:
            parts.append(
                f"{len(direct)} of these routes are direct-reuse routes, which a declared contaminant has to be "
                "cleared for before collection"
            )
        if untested:
            parts.append(f"{len(untested)} partners record no testing or separation capability of their own")
        insights.append(
            {
                "field": "contaminants",
                "tone": "danger" if direct else "warn",
                "title": "Contaminants declared: " + ", ".join(str(c) for c in contaminants),
                "note": "; ".join(parts) if parts else "Every partner in range records its own screening step.",
                "affects": "adds a caution on top of the safety layer - it can never remove one",
                "affected_recipients": sorted({str(r.get("company_name")) for r in direct + untested}),
                "value": [str(c) for c in contaminants],
            }
        )
    elif properties & CONTAMINANT_PROPERTIES:
        insights.append(
            {
                "field": "contaminants",
                "tone": "warn",
                "title": "Contaminants not declared",
                "note": f"The knowledge base records {material.get('name', 'this material')} as carrying "
                "residual contamination, so the cautions on these routes stand whether or not you list anything.",
                "affects": "nothing was changed by this note",
                "affected_recipients": [],
                "value": None,
            }
        )

    # --- intended use against the knowledge base ----------------------------
    intended = values.get("intended_use")
    if intended:
        applications = [str(a) for a in (material.get("reuse_categories") or [])]
        haystack = " ".join(applications + [str(material.get("notes", ""))]).lower().replace("_", " ")
        words = [w for w in str(intended).lower().replace(",", " ").split() if len(w) > 3]
        hits = [w for w in words if w in haystack]
        insights.append(
            {
                "field": "intended_use",
                "tone": "info" if hits else "warn",
                "title": f"Intended use: {intended}",
                "note": (
                    "The knowledge base records " + ", ".join(sorted({a.replace('_', ' ') for a in applications}))
                    if not applications
                    else (
                        f"'{intended}' shares wording with the reuse applications recorded for "
                        f"{material.get('name', 'this material')}: {', '.join(hits)}."
                        if hits
                        else f"'{intended}' is not among the reuse applications the knowledge base records for "
                        f"{material.get('name', 'this material')}. The ranking ignores it either way, so read the "
                        "pathways as suggestions for your material, not for your plan."
                    )
                ),
                "affects": "nothing in the ranking",
                "affected_recipients": names[:0],
                "value": str(intended),
            }
        )

    return insights
