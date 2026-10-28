"""Material similarity (§12) - deterministic, descriptive, and subordinate to safety.

Two waste streams are *similar* when the knowledge base describes them with
overlapping properties, reuse categories and receiving sectors. That is a statement
about the materials. It is not a statement about whether a particular plant can take
one in place of the other, which is what the safety layer and each recipient's
accepted list decide.

So this module is deliberately read-only and non-authoritative:

* the score is a Jaccard overlap over KB fields - no model, no weights, nothing a
  caller can nudge;
* every row carries the other material's own safety level and processing requirement,
  plus an explicit `safety_delta` when the substitute is the stricter of the two;
* nothing here is allowed to widen a match. The ranking pipeline never imports it.
"""

from __future__ import annotations

from typing import Any

from knowledge_base.materials import MATERIALS, MATERIALS_BY_ID

SAFETY_ORDER = {"low": 0, "moderate": 1, "high": 2, "hazardous": 3, "unknown": 4}
"""Ranking of the five states from least to most restrictive. `unknown` sits last on
purpose: not knowing is treated as the strictest case, never as a free pass."""

# Field weights for the overlap. Properties are the most specific signal, sector
# compatibility the broadest; keeping them separate is what makes `shared` readable.
ASPECT_WEIGHTS = {"properties": 0.45, "reuse_categories": 0.35, "compatible_sectors": 0.20}
CATEGORY_BONUS = 0.08


def _tokens(material: dict[str, Any], field: str) -> set[str]:
    return {str(value).lower() for value in material.get(field) or []}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compare(source: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    """One number plus the evidence behind it. Pure: no lookups, no globals."""
    shared: dict[str, list[str]] = {}
    score = 0.0
    for field, weight in ASPECT_WEIGHTS.items():
        a, b = _tokens(source, field), _tokens(other, field)
        overlap = _jaccard(a, b)
        score += weight * overlap
        shared[field] = sorted(a & b)

    same_category = bool(source.get("category")) and source.get("category") == other.get("category")
    if same_category:
        score += CATEGORY_BONUS
    score = round(min(score, 1.0), 4)

    source_level = str(source.get("safety_level", "unknown"))
    other_level = str(other.get("safety_level", "unknown"))
    stricter = SAFETY_ORDER.get(other_level, 4) > SAFETY_ORDER.get(source_level, 4)
    differences: list[str] = []
    if stricter:
        differences.append(f"safety level is {other_level} against {source_level} for {source.get('name')}")
    elif SAFETY_ORDER.get(other_level, 4) < SAFETY_ORDER.get(source_level, 4):
        differences.append(f"safety level is {other_level}; the {source.get('name')} cautions still apply to you")
    if bool(other.get("requires_processing")) != bool(source.get("requires_processing")):
        differences.append(
            "it "
            + ("needs processing before reuse" if other.get("requires_processing") else "does not need processing")
        )
    price_delta = None
    try:
        price_delta = round(float(other.get("typical_price_inr_per_tonne", 0)) - float(source.get("typical_price_inr_per_tonne", 0)), 2)
    except (TypeError, ValueError):  # pragma: no cover - seed data is numeric
        price_delta = None

    return {
        "material_id": other["id"],
        "name": other["name"],
        "category": other.get("category"),
        "similarity": round(score * 100, 1),
        "shared": {key: value for key, value in shared.items() if value},
        "shared_aspect_count": sum(1 for value in shared.values() if value),
        "same_category": same_category,
        "safety_level": other_level,
        "requires_processing": bool(other.get("requires_processing")),
        "safety_delta": differences[0] if stricter else None,
        "differences": differences,
        "typical_price_inr_per_tonne": other.get("typical_price_inr_per_tonne"),
        "price_delta_inr_per_tonne": price_delta,
        "acceptance_note": (
            "Similarity describes the material. Whether it can be reused here is still decided by the "
            "safety layer and by each recipient's own accepted-material list."
        ),
    }


def similar_to(material_id: str, limit: int = 6, min_score: float = 0.0) -> list[dict[str, Any]]:
    """Everything else in the knowledge base, best overlap first."""
    source = MATERIALS_BY_ID.get(material_id)
    if not source:
        return []
    rows = [compare(source, other) for other in MATERIALS if other["id"] != source["id"]]
    rows = [row for row in rows if row["similarity"] >= min_score]
    # Similarity first, then the name: a tie must resolve the same way twice.
    rows.sort(key=lambda row: (-row["similarity"], row["name"]))
    return rows[:limit]


def most_distinct(material_id: str, limit: int = 3) -> list[dict[str, Any]]:
    """The opposite end of the table, shown so the list cannot look like a club of
    near-identical materials when the overlap is genuinely thin."""
    source = MATERIALS_BY_ID.get(material_id)
    if not source:
        return []
    rows = [compare(source, other) for other in MATERIALS if other["id"] != source["id"]]
    rows.sort(key=lambda row: (row["similarity"], row["name"]))
    return rows[:limit]
