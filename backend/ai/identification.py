"""Identification pipeline: LLM first, deterministic fallback second.

Whatever produced the raw JSON, the result is *validated and re-grounded*
against the material knowledge base before it leaves this module:

  * `material_id` must resolve to a KB record (otherwise -> unknown material)
  * `category`, `properties`, `reuse_categories`, `safety_level` and
    `requires_processing` are taken FROM THE KB, never from the model
  * LLM-suggested reuse categories are intersected with the KB set, so the
    model can only ever narrow the candidate list, never expand it
"""

from __future__ import annotations

import json
import os
import re

import httpx
from pydantic import ValidationError

from ai import fallback
from ai.prompts import SYSTEM_PROMPT, build_user_prompt
from knowledge_base.materials import (
    MATERIALS,
    MATERIALS_BY_ID,
    MATERIAL_CATEGORIES,
    REUSE_CATEGORIES,
    UNKNOWN_MATERIAL_ID,
)
from models.schemas import MaterialIdentification

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
# Cheap reachability probe. Keeps an unresponsive-but-listening Ollama from
# burning the whole inference timeout before we fall back.
OLLAMA_PROBE_TIMEOUT = float(os.environ.get("OLLAMA_PROBE_TIMEOUT_SECONDS", "2"))


class OllamaUnavailable(Exception):
    pass


class OllamaUnresponsive(OllamaUnavailable):
    """Ollama accepted the connection but never answered the probe.

    Kept distinct so the warning can name the real cause - a wedged or
    overloaded server - rather than blaming the inference timeout.
    """


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def probe_ollama() -> None:
    """Fail fast if Ollama is not answering.

    Raises OllamaUnavailable immediately (within ~OLLAMA_PROBE_TIMEOUT seconds)
    when the server is down or wedged, so the caller can fall back to the
    deterministic classifier instead of blocking for the full inference
    timeout - which is what previously left the browser proxy hanging.
    """
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=OLLAMA_PROBE_TIMEOUT)
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise OllamaUnresponsive(
            f"Ollama at {OLLAMA_URL} accepted the connection but did not respond "
            f"within {OLLAMA_PROBE_TIMEOUT:g}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise OllamaUnavailable(f"Ollama not reachable at {OLLAMA_URL}: {exc}") from exc


def ollama_status() -> dict:
    """Cheap probe used by the /api/health endpoint and the UI badge."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        resp.raise_for_status()
        tags = resp.json().get("models", [])
        names = [t.get("name", "") for t in tags]
        return {
            "available": True,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "model_present": any(n.startswith(OLLAMA_MODEL) for n in names),
            "installed_models": names[:20],
        }
    except Exception as exc:  # connection refused, timeout, bad JSON...
        return {
            "available": False,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "model_present": False,
            "error": str(exc),
        }


def _call_ollama(description: str, composition: str | None, attached_text: str | None) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 700},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(
                    description,
                    composition,
                    attached_text,
                    [m["name"] for m in MATERIALS],
                    MATERIAL_CATEGORIES,
                    REUSE_CATEGORIES,
                ),
            },
        ],
    }
    try:
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaUnavailable(f"Ollama request failed: {exc}") from exc

    content = resp.json().get("message", {}).get("content", "")
    if not content:
        raise OllamaUnavailable("Ollama returned an empty response")
    return content


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(raw)
        if not match:
            raise
        return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Grounding: make the model's answer conform to the knowledge base
# ---------------------------------------------------------------------------


def _resolve_material(data: dict) -> tuple[str | None, float]:
    """Map a model-supplied name onto a KB material id."""
    raw_name = str(data.get("material", "")).strip().lower()
    if not raw_name:
        return None, 0.0
    for mat in MATERIALS:
        if raw_name == mat["name"].lower():
            return mat["id"], float(data.get("confidence") or 0.0)
    for mat in MATERIALS:
        if raw_name == mat["id"].lower() or raw_name in mat["name"].lower():
            return mat["id"], float(data.get("confidence") or 0.0) * 0.9
    for mat in MATERIALS:
        if any(raw_name == a.lower() for a in mat.get("aliases", [])):
            return mat["id"], float(data.get("confidence") or 0.0) * 0.85
    return None, float(data.get("confidence") or 0.0) * 0.5


def _ground(raw: dict, engine: str) -> MaterialIdentification:
    material_id, model_confidence = _resolve_material(raw)
    confidence = max(0.0, min(1.0, model_confidence))

    if material_id is None:
        material_id = UNKNOWN_MATERIAL_ID
        confidence = min(confidence, 0.35)

    mat = MATERIALS_BY_ID[material_id]
    is_unknown = material_id == UNKNOWN_MATERIAL_ID

    # The model may only NARROW the KB's reuse categories.
    kb_reuse = list(mat["reuse_categories"])
    suggested = [r for r in (raw.get("reuse_categories") or []) if r in REUSE_CATEGORIES]
    reuse = [r for r in kb_reuse if r in suggested] or kb_reuse

    safety = str(raw.get("safety_level") or mat["safety_level"]).lower()
    if safety not in {"low", "moderate", "high", "hazardous", "unknown"}:
        safety = mat["safety_level"]
    # Never let the model downgrade a hazard below the KB record.
    order = ["low", "moderate", "high", "hazardous", "unknown"]
    if order.index(safety) < order.index(mat["safety_level"]) and mat["safety_level"] != "unknown":
        safety = mat["safety_level"]

    composition = raw.get("composition") or {}
    if not isinstance(composition, dict):
        composition = {}
    composition = {str(k)[:40]: str(v)[:40] for k, v in list(composition.items())[:12]}

    properties = [str(p)[:40] for p in (raw.get("properties") or []) if isinstance(p, (str, int))][:12]
    if not properties:
        properties = list(mat["properties"])

    alternatives = []
    for alt in (raw.get("alternatives") or [])[:3]:
        if not isinstance(alt, dict):
            continue
        alt_id, alt_conf = _resolve_material({"material": alt.get("material"), "confidence": alt.get("confidence", 0.3)})
        if alt_id and alt_id != material_id:
            alternatives.append(
                {
                    "material": MATERIALS_BY_ID[alt_id]["name"],
                    "material_id": alt_id,
                    "confidence": round(max(0.0, min(1.0, alt_conf)), 2),
                }
            )

    uncertainty = None
    if is_unknown:
        uncertainty = (
            "Symbio could not confidently identify this stream. It is treated as UNKNOWN and is only "
            "routed to a licensed waste processor for assessment."
        )
    elif confidence < 0.5:
        uncertainty = (
            f"Identification confidence is low ({confidence:.0%}). Confirm the material before acting "
            "on the ranked matches."
        )
    elif confidence < 0.7:
        uncertainty = "Confidence is moderate. Worth verifying against a lab report."

    return MaterialIdentification(
        material=mat["name"],
        material_id=mat["id"],
        confidence=round(confidence, 2),
        category=mat["category"],
        properties=properties,
        composition=composition,
        alternatives=alternatives,
        reuse_categories=reuse,
        safety_level=safety,  # type: ignore[arg-type]
        requires_processing=bool(mat["requires_processing"]),
        engine=engine,
        reasoning=str(raw.get("reasoning") or "")[:400],
        uncertainty_note=uncertainty,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def identify(
    description: str,
    composition: str | None = None,
    attached_text: str | None = None,
    warnings: list[str] | None = None,
) -> MaterialIdentification:
    """Identify a material. Falls back to the deterministic classifier on error."""
    warnings = warnings if warnings is not None else []

    try:
        probe_ollama()
        raw = _extract_json(_call_ollama(description, composition, attached_text))
        ident = _ground(raw, engine=f"ollama:{OLLAMA_MODEL}")
        # Merge any composition the user typed but the model dropped.
        if not ident.composition:
            ident.composition = fallback.parse_composition(composition or attached_text)
        return ident
    except (OllamaUnavailable, json.JSONDecodeError, ValidationError, KeyError, ValueError) as exc:
        reason = _describe_failure(exc)
        warnings.append(
            f"{reason} Symbio used its built-in deterministic classifier instead, so this "
            "result is still valid - just less flexible about unusual wording."
        )
        ident = MaterialIdentification(**fallback.classify(description, composition, attached_text))
        if not ident.composition:
            ident.composition = fallback.parse_composition(composition or attached_text)
        ident.reasoning = f"{ident.reasoning} (fallback: {exc.__class__.__name__})"
        return ident


def _describe_failure(exc: Exception) -> str:
    """Turn an exception into a sentence a user can act on.

    An unexplained 500 or a silent fallback is worse than either a slow answer
    or a clear message, so name the cause and the fix.
    """
    # Check the subclass first - it needs a different remedy.
    if isinstance(exc, OllamaUnresponsive):
        return (
            f"Ollama at {OLLAMA_URL} accepted the connection but did not respond within "
            f"{OLLAMA_PROBE_TIMEOUT:g}s. It is likely still loading {OLLAMA_MODEL}, or is "
            "busy with another request - try again, or raise OLLAMA_PROBE_TIMEOUT_SECONDS."
        )
    if isinstance(exc, OllamaUnavailable):
        detail = str(exc).lower()
        if "timed out" in detail or "timeout" in detail:
            return (
                f"Ollama did not answer within {OLLAMA_TIMEOUT:g}s ({OLLAMA_MODEL}). "
                "Raise OLLAMA_TIMEOUT_SECONDS if your machine is slow, or use a smaller model."
            )
        return (
            f"Ollama is not reachable at {OLLAMA_URL}. Start it with `ollama serve` and make sure "
            f"`ollama pull {OLLAMA_MODEL}` has been run."
        )
    if isinstance(exc, json.JSONDecodeError):
        return "Ollama returned text that was not valid JSON."
    if isinstance(exc, ValidationError):
        return "Ollama returned a response that did not match the expected schema."
    return "Ollama returned an unusable answer."
