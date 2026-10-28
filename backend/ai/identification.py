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
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))

# `qwen2.5:3b` is the model this project is built and tuned around. It is a
# *preferred* tag rather than a hard requirement: if it is not installed we use
# whatever the machine already has pulled, so `ollama serve` alone is enough to
# get a working demo. Setting OLLAMA_MODEL explicitly pins the choice and turns
# the auto-selection off - it will then be honoured exactly or not used at all.
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_MODEL_PINNED = "OLLAMA_MODEL" in os.environ
if OLLAMA_MODEL_PINNED:
    OLLAMA_MODEL = os.environ["OLLAMA_MODEL"]

# Local chat models known to follow a "reply with JSON only" instruction well
# enough to be useful here. Anything we pick is still validated and re-grounded
# against the knowledge base, so a non-compliant model degrades to the fallback
# rather than producing a wrong answer.
OLLAMA_MODEL_PREFERENCE = (
    OLLAMA_MODEL.split(":")[0],  # qwen2.5 family first
    "llama3.1",
    "llama3.2",
    "llama3",
    "mistral",
    "gemma2",
    "phi3",
)

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


class OllamaDisabled(OllamaUnavailable):
    """OLLAMA_ENABLED=false - the operator turned the integration off deliberately.

    Distinct from "not reachable" so the warning does not tell someone to run
    `ollama serve` when the real instruction is to unset OLLAMA_ENABLED. Read at
    call time (not cached at import) so it can be toggled per test or per request
    without restarting the process.
    """


class OllamaModelMissing(OllamaUnavailable):
    """Ollama is running, but nothing Symbio can drive is installed.

    Needs a different remedy from "start the server": one `ollama pull`. Carries
    the installed tags so the advice can name them.
    """

    def __init__(
        self, message: str, installed: list[str] | None = None, advice: str | None = None
    ):
        super().__init__(message)
        self.installed = list(installed or [])
        # Where the caller already knows the right fix, it can say so instead of
        # letting us guess from the model list.
        self.advice = advice


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def _installed_models(timeout: float | None = None) -> list[str]:
    """Model tags Ollama reports, raising a Symbio-specific error on failure."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout or OLLAMA_PROBE_TIMEOUT)
        resp.raise_for_status()
        models = resp.json().get("models", []) or []
    except httpx.TimeoutException as exc:
        raise OllamaUnresponsive(
            f"Ollama at {OLLAMA_URL} accepted the connection but did not respond "
            f"within {OLLAMA_PROBE_TIMEOUT:g}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise OllamaUnavailable(f"Ollama not reachable at {OLLAMA_URL}: {exc}") from exc
    return [str(m.get("name") or m.get("model") or "") for m in models if m]


def select_model(installed: list[str]) -> str | None:
    """Choose which model to drive.

    The recommended tag wins when present; otherwise we use the first already
    pulled model in OLLAMA_MODEL_PREFERENCE, so a machine that merely has
    Ollama running with *some* chat model works with no further setup. When
    OLLAMA_MODEL was set explicitly we honour it exactly and substitute
    nothing - a pinned choice is deliberate, not an accident.
    """
    if OLLAMA_MODEL_PINNED:
        return next((n for n in installed if n.startswith(OLLAMA_MODEL)), None)

    if OLLAMA_MODEL in installed:
        return OLLAMA_MODEL
    for family in OLLAMA_MODEL_PREFERENCE:
        for name in installed:
            if name.startswith(family):
                return name
    return None


def probe_ollama() -> str:
    """Fail fast unless Ollama is answering, and say which model to use.

    Raises OllamaUnavailable within ~OLLAMA_PROBE_TIMEOUT seconds when the
    server is down or wedged, so the caller can fall back to the deterministic
    classifier instead of blocking for the full inference timeout - which is
    what previously left the browser proxy hanging.
    """
    if os.environ.get("OLLAMA_ENABLED", "true").strip().lower() in ("false", "0", "off", "no"):
        raise OllamaDisabled("Ollama integration is disabled (OLLAMA_ENABLED=false)")
    installed = _installed_models()
    model = select_model(installed)
    if model is None:
        raise OllamaModelMissing(
            f"Ollama is running at {OLLAMA_URL} but has no model Symbio can use", installed
        )
    return model


def active_model() -> str | None:
    """The model Symbio would use right now, or None if Ollama is not usable.

    Never raises - for callers that only want to know whether to bother.
    """
    try:
        return probe_ollama()
    except OllamaUnavailable:
        return None


def ollama_status() -> dict:
    """Cheap probe used by the /api/health endpoint and the UI badge.

    `available` means the server answered; `usable` means we also found a model
    to drive. The badge needs both, because "running with nothing pulled" is a
    real state and it needs a different fix than "not running".
    """
    base = {"url": OLLAMA_URL, "requested_model": OLLAMA_MODEL}
    if os.environ.get("OLLAMA_ENABLED", "true").strip().lower() in ("false", "0", "off", "no"):
        return {
            **base,
            "available": False,
            "usable": False,
            "model": OLLAMA_MODEL,
            "model_present": False,
            "auto_selected": False,
            "installed_models": [],
            "error": "Ollama integration is disabled (OLLAMA_ENABLED=false)",
        }
    try:
        names = _installed_models(timeout=2.0)
    except Exception as exc:  # connection refused, timeout, bad JSON...
        return {
            **base,
            "available": False,
            "usable": False,
            "model": OLLAMA_MODEL,
            "model_present": False,
            "auto_selected": False,
            "installed_models": [],
            "error": str(exc),
        }
    model = select_model(names)
    return {
        **base,
        "available": True,
        "usable": model is not None,
        "model": model or OLLAMA_MODEL,
        "model_present": OLLAMA_MODEL in names,
        "auto_selected": model is not None and model != OLLAMA_MODEL,
        "installed_models": names[:20],
    }


def _call_ollama(description: str, composition: str | None, attached_text: str | None, model: str) -> str:
    payload = {
        "model": model,
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
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise OllamaModelMissing(
                f"Ollama has no model named {model}",
                advice=(
                    f"Ollama listed `{model}` but refused to run it - it may not be fully "
                    f"downloaded. Run `ollama pull {model}` and try again."
                ),
            ) from exc
        raise OllamaUnavailable(f"Ollama request failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise OllamaUnavailable(f"Ollama request failed: {exc}") from exc
    resp.raise_for_status()

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
        # One cheap request tells us the server is alive *and* which model to use.
        model = probe_ollama()
        raw = _extract_json(_call_ollama(description, composition, attached_text, model))
        ident = _ground(raw, engine=f"ollama:{model}")
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
    if isinstance(exc, OllamaDisabled):
        return "Ollama integration is disabled (OLLAMA_ENABLED=false)."
    if isinstance(exc, OllamaUnresponsive):
        return (
            f"Ollama at {OLLAMA_URL} accepted the connection but did not respond within "
            f"{OLLAMA_PROBE_TIMEOUT:g}s. It is likely starting up, still loading a model, or "
            "busy with another request - try again shortly, or raise OLLAMA_PROBE_TIMEOUT_SECONDS."
        )
    # Ollama answered but has nothing to run. Do not tell them to start Ollama.
    if isinstance(exc, OllamaModelMissing):
        if exc.advice:
            return exc.advice
        if OLLAMA_MODEL_PINNED:
            return (
                f"Ollama is running at {OLLAMA_URL} but the model you pinned is not installed "
                f"(`OLLAMA_MODEL={OLLAMA_MODEL}`). Run `ollama pull {OLLAMA_MODEL}`, or unset "
                "OLLAMA_MODEL to let Symbio use any model you already have."
            )
        if not exc.installed:
            return (
                f"Ollama is running at {OLLAMA_URL} but has no models installed. Run "
                f"`ollama pull {OLLAMA_MODEL}` (recommended, about 1.9 GB)."
            )
        return (
            f"Ollama is running at {OLLAMA_URL} but none of the installed models "
            f"({', '.join(exc.installed)}) are ones Symbio can drive. Run "
            f"`ollama pull {OLLAMA_MODEL}` (recommended, about 1.9 GB), or any of these: "
            f"{', '.join(OLLAMA_MODEL_PREFERENCE)}."
        )
    if isinstance(exc, OllamaUnavailable):
        detail = str(exc).lower()
        if "timed out" in detail or "timeout" in detail:
            return (
                f"Ollama did not answer within {OLLAMA_TIMEOUT:g}s ({OLLAMA_MODEL}). "
                "Raise OLLAMA_TIMEOUT_SECONDS if your machine is slow, or use a smaller model."
            )
        return (
            f"Ollama is not reachable at {OLLAMA_URL}. Start it with `ollama serve` - Symbio uses "
            f"any chat model you already have pulled, and prefers {OLLAMA_MODEL}."
        )
    if isinstance(exc, json.JSONDecodeError):
        return "Ollama returned text that was not valid JSON."
    if isinstance(exc, ValidationError):
        return "Ollama returned a response that did not match the expected schema."
    return "Ollama returned an unusable answer."
