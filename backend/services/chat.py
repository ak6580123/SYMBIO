"""Grounded assistant.

This is NOT a general chatbot. It answers a fixed set of questions about the
analysis the user is currently looking at, using only:

  * the stored analysis record (identification + KB material record)
  * the stored match records
  * the recipient knowledge base

When the question falls outside that scope, or the data simply is not there, it
replies: "I don't have enough information to determine that."

If Ollama is running, an out-of-scope question is answered by the model with the
analysis summary as context, and the answer is labelled as coming from the LLM.
"""

from __future__ import annotations

import re
from typing import Any

from ai.identification import OLLAMA_URL, active_model
from knowledge_base import loader
from matching.engine import REUSE_END_USE, SAFETY_RANK, SECTOR_LABELS
from models.schemas import plain
from services import analysis as analysis_service

NO_INFO = "I don't have enough information to determine that."

CAN_ANSWER = (
    "I can answer questions about this analysis: what the material is, which sectors could use it, "
    "why a specific recipient was recommended, whether processing is required, which option is "
    "safest, which route avoids the most CO2e, and the estimated impact figures (labelled as demo "
    "calculations)."
)


# ---------------------------------------------------------------------------
# Intent detection - deliberately simple and readable
# ---------------------------------------------------------------------------

# Order matters: the first pattern that matches wins. Deliberately narrow -
# a bare "what is" used to catch anything containing those words, so genuinely
# out-of-scope questions got an answer instead of an honest "I don't know".
INTENTS = [
    # "ranked first" is how people actually ask this, so it has to be in the
    # pattern - matching only "ranking" sent it to the refusal branch.
    ("match_reason", r"\b(why|reason|reasons|how did|explain|ranking|ranked?)\b.*\b(match|matches|recommend|recommended|chosen|winner|top|score|scores|rank|first|best)\b"),
    # Before processing/impact/material: "safest handling" and "highest
    # environmental benefit" both contain words those broader patterns catch.
    ("safest", r"\b(safe|safest|safety|risk|riskiest|caution|cautious)\b"),
    ("environmental_ranking", r"\b(highest|best|most|biggest|largest|greatest|maximum)\b[^?]*\b(environmental|environment|co2e?|carbon|benefit|impact)\b"),
    ("processing", r"\b(process|processing|processed|treatment|treat|treated|handling|handle)\b"),
    ("impact", r"\b(impact|co2|co2e|carbon|emission|emissions|environment|environmental|value|money|worth|price|savings|divert|diverted)\b"),
    ("reuse_options", r"\b(reuse|re-use|application|applications|do with|useful|purpose|what can)\b"),
    ("sectors", r"\b(sector|sectors|industry|industries|company|companies|buyer|buyers)\b"),
    ("material", r"\b(material|composition|properties|property|hazard|hazardous|safety|contaminat)\b"),
]


def _detect_intent(question: str, match_id: str | None) -> str:
    q = question.lower()

    # "Why was X recommended / ranked first?" is the single most common question
    # on a match page, and "company"/"recipient"/"sector" in it would otherwise
    # be caught by the broader patterns. Give it outright priority.
    if re.search(r"\b(why|reason|explain)\b", q) and re.search(r"\b(recommend\w*|rank\w*|first|top|winner)\b", q):
        return "match_reason"

    if match_id and re.search(r"\b(why|reason|explain|score)\b", q):
        return "match_reason"

    for name, pattern in INTENTS:
        if re.search(pattern, q):
            return name
    return "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sector_label(sector: str) -> str:
    return SECTOR_LABELS.get(sector, sector.replace("_", " ").title())


# `_plain` is the schemas helper: enum fields must never appear as
# 'SafetyLevel.moderate' inside a sentence.
_plain = plain


def _plain_text(text: str) -> str:
    """Answers are displayed as plain text, so markdown markers are removed here
    instead of pulling a renderer into the frontend. Emphasis and heading markers
    only - bullets and line breaks are what makes a list readable, so they stay.
    """
    text = re.sub(r"^#{1,4}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    return text.replace("`", "").strip()


def _fmt(value: float) -> str:
    return f"{value:,.0f}"


def _sectors_using(analysis: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in analysis["matches"]:
        if match["matched_quantity_t_per_month"] > 0:
            counts[match["recipient"]["sector"]] = counts.get(match["recipient"]["sector"], 0) + 1
    return counts


def _recipient_from_question(analysis: dict, question: str, match_id: str | None) -> dict | None:
    if match_id:
        found = analysis_service.find_match(match_id)
        if found and found["analysis_id"] == analysis["id"]:
            return found
    q = question.lower()
    for match in analysis["matches"]:
        name = match["recipient"]["company_name"]
        if name.lower() in q or name.lower().split()[0] in q:
            return match
    return analysis["matches"][0] if analysis["matches"] else None


# ---------------------------------------------------------------------------
# Deterministic, grounded answers
# ---------------------------------------------------------------------------


def _answer_safest(analysis: dict) -> str:
    """Rank routes by the safety layer's own classification, never by opinion.

    The order comes from the level the knowledge base assigned and the routing
    decision the gate made, so the assistant cannot talk its way into calling a
    hazardous stream safe.
    """
    matches = analysis["matches"]
    if not matches:
        return (
            f"No reuse route passed the safety layer for {analysis['material']['name']}, so there is "
            "nothing to rank by safety."
        )
    ranked = sorted(matches, key=lambda m: (SAFETY_RANK.get(m["safety_level"], 9), -m["overall_score"]))
    lines = [
        f"- {m['recipient']['company_name']} ({_sector_label(m['recipient']['sector'])}) — "
        f"{_plain(m['safety_level'])} risk, {_plain(m['reuse_type']).replace('_', ' ').lower()}"
        for m in ranked[:5]
    ]
    direct = [m for m in matches if m["reuse_type"] == "DIRECT_REUSE"]
    lead = (
        f"{len(direct)} of {len(matches)} routes can be used without further processing"
        if direct
        else f"all {len(matches)} routes carry processing or handling conditions"
    )
    return (
        f"Safest reuse options for **{analysis['material']['name']}**, ranked by knowledge-base safety "
        f"level and the routing decision ({lead}):\n"
        + "\n".join(lines)
        + "\n\nThese are demo classifications. They do not replace a site-specific risk assessment "
        "or the handling instructions of the receiving plant."
    )


def _answer_environmental_ranking(analysis: dict) -> str:
    """Which route avoids the most CO2e, from the figures the engine computed."""
    matches = analysis["matches"]
    if not matches:
        return "No reuse route was scored for this stream, so there is no environmental benefit to rank."
    ranked = sorted(matches, key=lambda m: (-m["estimated_co2e_t_per_month"], -m["overall_score"]))
    best = ranked[0]
    lines = "\n".join(
        f"- {m['recipient']['company_name']} — {m['estimated_co2e_t_per_month']} t CO₂e/mo, with "
        f"{m['allocated_t_per_month']} t/mo allocated to this route"
        for m in ranked[:5]
    )
    return (
        f"Highest estimated environmental benefit: **{best['recipient']['company_name']}** at "
        f"{best['estimated_co2e_t_per_month']} t CO₂e/month, via "
        f"{' → '.join(best['reuse_pathway']['steps'])}.\n\n{lines}\n\n"
        "Estimated impact — demo calculation: avoided CO₂e = routed tonnes × the knowledge-base "
        f"avoidance factor ({analysis['totals']['co2e_factor_used_t_per_tonne']} t per tonne). Each "
        "route above is priced as if it took the matched quantity on its own; the totals then share "
        "the single stream out, so the route figures do not add up."
    )


def _answer_material(analysis: dict) -> str:
    ident = analysis["identification"]
    mat = analysis["material"]
    comp = ident.get("composition") or {}
    comp_txt = ", ".join(f"{k.upper()} {v}" for k, v in comp.items()) or "not reported"
    return (
        f"Symbio identified this as **{mat['name']}** ({mat['category'].replace('_', ' ')}) with "
        f"{ident['confidence']:.0%} confidence, using {ident['engine']}.\n\n"
        f"- Reported composition: {comp_txt}\n"
        f"- Properties from the knowledge base: {', '.join(mat['properties'])}\n"
        f"- Knowledge-base safety level: {mat['safety_level']}\n\n"
        f"{mat.get('notes', '')}"
    )


def _answer_reuse(analysis: dict) -> str:
    mat = analysis["material"]
    routes = [f"{r.replace('_', ' ')} → {REUSE_END_USE.get(r, 'assessed use')}" for r in mat["reuse_categories"]]
    if not routes:
        return (
            f"{mat['name']} has no reuse route recorded in the knowledge base, so Symbio only offers "
            "assessment by a licensed waste processor."
        )
    sectors = _sectors_using(analysis)
    sector_txt = ", ".join(f"{_sector_label(s)} ({n})" for s, n in sectors.items()) or "none in this dataset"
    return (
        f"Recorded reuse routes for **{mat['name']}**:\n"
        + "\n".join(f"- {r}" for r in routes)
        + f"\n\nIn this analysis, {len(analysis['matches'])} recipients are compatible. "
        f"Sectors with an allocated route: {sector_txt}.\n\n"
        "Economic and emission figures shown against each route are demo calculations."
    )


def _answer_processing(analysis: dict) -> str:
    mat = analysis["material"]
    ident = analysis["identification"]
    lines = [
        f"**{mat['name']}** requires processing before reuse: **{mat['requires_processing']}** "
        f"(knowledge base). KB safety level: {mat['safety_level']}.",
    ]
    if ident.get("uncertainty_note"):
        lines.append(f"Identification note: {ident['uncertainty_note']}")

    seen: dict[str, list[str]] = {}
    for match in analysis["matches"][:5]:
        seen.setdefault(match["reuse_type"], []).append(match["recipient"]["company_name"])
    for reuse_type, names in seen.items():
        lines.append(f"- {reuse_type}: {', '.join(names[:3])}")

    cautions = [c for m in analysis["matches"][:3] for c in m["cautions"]]
    if cautions:
        lines.append("\nHandling notes from the safety layer:\n" + "\n".join(f"- {c}" for c in cautions[:3]))
    return "\n".join(lines)


def _answer_sectors(analysis: dict) -> str:
    mat = analysis["material"]
    compat = [_sector_label(s) for s in mat["compatible_sectors"]]
    if not compat:
        return f"No sector is recorded as compatible with {mat['name']} in the knowledge base."
    ranked = sorted(analysis["matches"], key=lambda m: -m["overall_score"])[:5]
    table = "\n".join(
        f"- {m['recipient']['company_name']} ({_sector_label(m['recipient']['sector'])}) — {m['overall_score']:.0f}%"
        for m in ranked
    )
    return (
        f"Sectors that can use **{mat['name']}**: {', '.join(compat)}.\n\n"
        f"Highest-ranked recipients in the demo dataset:\n{table}"
    )


def _answer_impact(analysis: dict) -> str:
    t = analysis["totals"]
    top = analysis["matches"][0] if analysis["matches"] else None
    lines = [
        "**Estimated impact (demo calculation, not a certified figure)**",
        f"- Waste diverted: {t['allocated_t_per_month']:g} of {t['available_t_per_month']:g} t/month "
        f"({t['diversion_rate']:.0%})",
        f"- Estimated value: ₹{_fmt(t['estimated_value_inr_per_month'])}/month",
        f"- Estimated CO2e avoided: {t['estimated_co2e_avoided_t_per_month']:g} t/month "
        f"(factor {t['co2e_factor_used_t_per_tonne']} t CO2e per tonne)",
    ]
    if top:
        haul = (
            f"{top['distance_km']:g} km away"
            if top.get("distance_km") is not None
            else "at a distance Symbio could not calculate"
        )
        lines.append(
            f"- Best route: {top['recipient']['company_name']} at {top['overall_score']:.0f}% match, {haul}"
        )
    return "\n".join(lines)


def _answer_match_reason(analysis: dict, question: str, match_id: str | None) -> str:
    match = _recipient_from_question(analysis, question, match_id)
    if not match:
        return NO_INFO
    b = match["breakdown"]
    weights = {"compatibility": 30, "quantity": 20, "location": 15, "sector": 15, "value": 10, "environmental": 10}
    rows = "\n".join(
        f"- {k.replace('_', ' ').title()}: {b[k]:.2f} × {w}% = {b[k] * w:.1f} pts" for k, w in weights.items()
    )
    reasons = "\n".join(f"✓ {r}" for r in match["reasons"])
    caution_txt = ""
    if match["cautions"]:
        caution_txt = "\n\nCautions:\n" + "\n".join(f"! {c}" for c in match["cautions"][:3])
    return (
        f"**{match['recipient']['company_name']}** scored **{match['overall_score']:.0f}%**.\n\n"
        f"Score breakdown (deterministic weighted sum):\n{rows}\n\n"
        f"Why it was recommended:\n{reasons}{caution_txt}"
    )


# ---------------------------------------------------------------------------
# Optional LLM augmentation for out-of-scope questions
# ---------------------------------------------------------------------------


def _llm_answer(analysis: dict, question: str) -> tuple[str, str] | None:
    """Grounded free-form answer from the local model, or None to stay deterministic.

    Returns (text, model_used) so the caller can label the engine truthfully.
    `active_model` also keeps a wedged Ollama from stalling the chat panel: if
    the probe does not answer in ~2s we skip the LLM entirely.
    """
    import httpx

    model = active_model()
    if model is None:
        return None

    summary = (
        f"Material: {analysis['material']['name']} ({analysis['material']['category']}), "
        f"confidence {analysis['identification']['confidence']:.0%}.\n"
        f"Quantity: {analysis['source']['quantity_t_per_month']} t/month from {analysis['source']['location']}.\n"
        f"Compatible sectors: {', '.join(SECTOR_LABELS.get(s, s) for s in analysis['material']['compatible_sectors'])}.\n"
        f"Top matches: "
        + "; ".join(
            f"{m['recipient']['company_name']} {m['overall_score']:.0f}%" for m in analysis["matches"][:5]
        )
        + ".\n"
        f"Totals (demo calculation): {analysis['totals']}."
    )
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 320},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Symbio's assistant. Answer ONLY from the analysis facts given. "
                    "Never invent companies, prices, emissions or safety claims. "
                    "If the facts do not cover the question, reply exactly: "
                    + NO_INFO
                ),
            },
            {"role": "user", "content": f"ANALYSIS FACTS:\n{summary}\n\nQUESTION:\n{question}"},
        ],
    }
    try:
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=45.0)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "").strip()
        return (content, model) if content else None
    except (httpx.HTTPError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def answer(analysis: dict, question: str, match_id: str | None = None) -> dict[str, Any]:
    intent = _detect_intent(question, match_id)

    if intent == "match_reason":
        text = _answer_match_reason(analysis, question, match_id)
        grounded = ["match.breakdown", "match.reasons"]
    elif intent == "processing":
        text = _answer_processing(analysis)
        grounded = ["material.requires_processing", "material.safety_level", "match.cautions"]
    elif intent == "reuse_options":
        text = _answer_reuse(analysis)
        grounded = ["material.reuse_categories", "match.recipient.sector"]
    elif intent == "sectors":
        text = _answer_sectors(analysis)
        grounded = ["material.compatible_sectors", "match.recipient"]
    elif intent == "safest":
        text = _answer_safest(analysis)
        grounded = ["match.safety_level", "match.reuse_type", "material.safety_level"]
    elif intent == "environmental_ranking":
        text = _answer_environmental_ranking(analysis)
        grounded = ["match.estimated_co2e_t_per_month", "match.reuse_pathway", "analysis.totals"]
    elif intent == "impact":
        text = _answer_impact(analysis)
        grounded = ["analysis.totals"]
    elif intent == "material":
        text = _answer_material(analysis)
        grounded = ["identification", "material"]
    else:
        result = _llm_answer(analysis, question)
        if result:
            llm_text, model = result
            return {
                "answer": _plain_text(llm_text),
                "grounded_in": ["analysis summary (LLM-augmented answer)"],
                "engine": f"ollama:{model}",
                "confident": NO_INFO not in llm_text,
            }
        return {
            "answer": f"{NO_INFO}\n\n{CAN_ANSWER}",
            "grounded_in": [],
            "engine": "deterministic",
            "confident": False,
        }

    if text == NO_INFO:
        return {"answer": f"{NO_INFO}\n\n{CAN_ANSWER}", "grounded_in": [], "engine": "deterministic", "confident": False}

    return {"answer": _plain_text(text), "grounded_in": grounded, "engine": "deterministic", "confident": True}


def recipient_directory() -> list[dict]:
    return loader.get_recipients()
