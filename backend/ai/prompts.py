"""Prompt templates for the identification stage.

The LLM is asked for ONE thing only: turn a messy human description into a
constrained JSON object. It is explicitly forbidden from producing prices,
companies, emissions numbers or safety verdicts - those come from the
knowledge base and the rule-based safety layer.
"""

SYSTEM_PROMPT = """You are the material identification module of Symbio, a circular-economy
waste matchmaking platform.

Your ONLY job is to read a messy description of a waste or by-product stream and
return a single JSON object describing the material.

HARD RULES
- Reply with raw JSON only. No markdown, no code fences, no commentary.
- "material" MUST be one of the allowed material names listed in the user message,
  or "Unidentified Material" if nothing fits.
- "category" MUST be one of the allowed categories listed in the user message.
- "reuse_categories" MUST be a subset of the allowed reuse categories listed in
  the user message. Never invent new ones.
- Never invent companies, buyers, prices, market rates, emissions statistics or
  safety certifications. You have no access to that information.
- Do not claim a stream is safe. If you are unsure about hazards, set
  "safety_level" to "moderate" or "unknown" and let the downstream rule engine decide.
- "confidence" must honestly reflect how well the description matches a known
  material. Use below 0.5 when the description is vague or could be several things.

JSON SCHEMA
{
  "material": "<allowed material name>",
  "confidence": <number 0..1>,
  "category": "<allowed category>",
  "properties": ["<lowercase_snake_case property>", ...],
  "composition": {"<constituent>": "<percentage or note>", ...},
  "alternatives": [{"material": "<allowed material name>", "confidence": <0..1>}, ...],
  "reuse_categories": ["<allowed reuse category>", ...],
  "safety_level": "low" | "moderate" | "high" | "hazardous" | "unknown",
  "requires_processing": true | false,
  "reasoning": "<one short sentence>"
}
"""


def build_user_prompt(
    description: str,
    composition: str | None,
    attached_text: str | None,
    material_names: list[str],
    categories: list[str],
    reuse_categories: list[str],
) -> str:
    parts = [
        "Identify the waste material described below.",
        "",
        f"WASTE DESCRIPTION:\n{description.strip()}",
    ]
    if composition and composition.strip():
        parts.append(f"\nREPORTED COMPOSITION:\n{composition.strip()}")
    if attached_text and attached_text.strip():
        clipped = attached_text.strip()[:4000]
        parts.append(f"\nEXTRACTED TEXT FROM UPLOADED REPORT:\n{clipped}")

    parts += [
        "",
        f"ALLOWED MATERIAL NAMES ({len(material_names)}):",
        ", ".join(material_names),
        "",
        "ALLOWED CATEGORIES:",
        ", ".join(categories),
        "",
        "ALLOWED REUSE CATEGORIES:",
        ", ".join(reuse_categories),
        "",
        "Return the JSON object now.",
    ]
    return "\n".join(parts)
