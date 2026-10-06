"""Deterministic fallback material classifier.

This is NOT a fake LLM stub. It is a real, explainable keyword + composition
evidence classifier used when Ollama is unavailable (or when the LLM returns
something unusable). Its confidence is deliberately capped below the LLM path
because it is less flexible, and the uncertainty is surfaced to the user.

The matching engine and the safety layer behave identically regardless of which
engine produced the identification.
"""

from __future__ import annotations

import math
import re

from knowledge_base.materials import MATERIALS, UNKNOWN_MATERIAL_ID

MAX_FALLBACK_CONFIDENCE = 0.78
# Each matched keyword scores KEYWORD_SCORE. The keyword lists in the knowledge
# base contain no bare generic words ("waste", "plastic", "metal"), so a single
# match is meaningful evidence; anything below one match is treated as unknown.
KEYWORD_SCORE = 1.0
ALIAS_SCORE = 0.5
MIN_EVIDENCE_SCORE = 0.9
COMPOSITION_TOKEN_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*)\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)

# Composition evidence: if these constituents appear with a percentage, the
# material on the right becomes more likely. (Demo heuristics, not a chemistry engine.)
COMPOSITION_EVIDENCE: dict[str, list[tuple[str, float]]] = {
    "sio2": [("fly_ash", 1.4), ("rice_husk_ash", 0.8), ("bottom_ash", 0.5)],
    "sio₂": [("fly_ash", 1.4), ("rice_husk_ash", 0.8)],
    "al2o3": [("fly_ash", 1.0)],
    "al₂o₃": [("fly_ash", 1.0)],
    "cao": [("fly_ash", 0.6), ("lime_sludge", 0.9), ("marble_slurry", 0.9)],
    "fe2o3": [("fly_ash", 0.6), ("steel_slag", 0.5)],
    "caco3": [("marble_slurry", 1.2), ("lime_sludge", 1.2)],
    "caso4": [("gypsum_waste", 1.2), ("phosphogypsum", 1.0)],
}


def parse_composition(text: str | None) -> dict[str, str]:
    """Extract 'SiO2: 55%' style pairs from free text."""
    if not text:
        return {}
    out: dict[str, str] = {}
    for name, value in COMPOSITION_TOKEN_RE.findall(text):
        key = name.strip().lower()
        if len(key) < 2:
            continue
        out[key] = f"{float(value):g}%"
    return out


def _score_material(mat: dict, needle: str, composition_keys: set[str]) -> float:
    score = 0.0
    for kw in mat["keywords"]:
        if kw.lower() in needle:
            score += KEYWORD_SCORE
    for alias in mat.get("aliases", []):
        a = alias.lower()
        if a and a in needle:
            score += ALIAS_SCORE
    for key in composition_keys:
        for candidate, weight in COMPOSITION_EVIDENCE.get(key, []):
            if candidate == mat["id"]:
                score += weight
    return score


def classify(description: str, composition: str | None = None, attached_text: str | None = None) -> dict:
    """Return a MaterialIdentification-shaped dict without calling any model."""
    blob = " ".join(filter(None, [description, composition or "", (attached_text or "")[:2000]])).lower()
    comp = parse_composition(composition or attached_text)
    comp_keys = set(comp.keys())

    scored = [
        (mat, _score_material(mat, blob, comp_keys))
        for mat in MATERIALS
        if mat["id"] != UNKNOWN_MATERIAL_ID
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    best, best_score = scored[0]
    runner_up = scored[1] if len(scored) > 1 else (None, 0.0)

    if best_score < MIN_EVIDENCE_SCORE:
        unknown = next(m for m in MATERIALS if m["id"] == UNKNOWN_MATERIAL_ID)
        return {
            "material": unknown["name"],
            "material_id": unknown["id"],
            "confidence": round(max(0.05, min(0.35, best_score * 0.4)), 2),
            "category": unknown["category"],
            "properties": ["unknown"],
            "composition": comp,
            "alternatives": [
                {"material": m["name"], "material_id": m["id"], "confidence": round(min(0.4, s / 4), 2)}
                for m, s in scored[:3]
                if s > 0
            ],
            "reuse_categories": [],
            "safety_level": "unknown",
            "requires_processing": True,
            "engine": "fallback_keyword",
            "reasoning": "No known material keyword or composition marker matched strongly enough.",
            "uncertainty_note": (
                "Identification confidence is low. Symbio will only route this stream to a licensed "
                "waste processor for assessment."
            ),
        }

    # Separation from the runner-up increases confidence; a near-tie lowers it.
    margin = 0.0 if runner_up[1] == 0 else 1.0 - (runner_up[1] / max(best_score, 1e-9))
    raw = math.tanh(best_score / 1.8) * (0.85 + 0.15 * margin)
    confidence = round(max(0.30, min(MAX_FALLBACK_CONFIDENCE, raw)), 2)

    alternatives = [
        {"material": m["name"], "material_id": m["id"], "confidence": round(min(0.6, s / 4), 2)}
        for m, s in scored[1:4]
        if s > 0
    ]

    return {
        "material": best["name"],
        "material_id": best["id"],
        "confidence": confidence,
        "category": best["category"],
        "properties": list(best["properties"]),
        "composition": comp,
        "alternatives": alternatives,
        "reuse_categories": list(best["reuse_categories"]),
        "safety_level": best["safety_level"],
        "requires_processing": best["requires_processing"],
        "engine": "fallback_keyword",
        "reasoning": f"Keyword and composition evidence pointed to {best['name']}.",
        "uncertainty_note": (
            None if confidence >= 0.6 else
            "Confidence is moderate. Verify the material before acting on the ranked matches."
        ),
    }
