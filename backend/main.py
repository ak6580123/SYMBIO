"""Symbio API - FastAPI application entry point.

Run from the backend directory:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import os
import threading

from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from ai.identification import ollama_status
from knowledge_base import loader
from knowledge_base import similarity
from knowledge_base.materials import MATERIALS, MATERIALS_BY_ID
from matching.engine import (
    PARTNER_TYPE_LABELS,
    SECTOR_LABELS,
    WEIGHTS,
    gate_rules_for,
    haversine_km,
    partner_type,
    processing_burden,
)
from models.schemas import (
    ListingRequest,
    AnalyzeRequest,
    ChatRequest,
    ScenarioCompareRequest,
    ScenarioRequest,
    ExtractRequest,
    MapLink,
    MapNode,
    MapResponse,
    ReuseType,
    SafetyLevel,
    UploadResponse,
)
from matching import logistics
from services import analysis as analysis_service
from services import demand_forecast as demand_service
from services import listings as listings_service
from services import material_flow as material_flow_service
from services import completeness as completeness_service
from services import scenarios as scenarios_service
from services import profiles as profiles_service
from services import explain as explain_service
from services import chat as chat_service
from services import dashboard as dashboard_service
from services import extract as extract_service
from services import files as file_service
from services import persistence
from services import storage
from api import auth as auth_api
from api import marketplace as marketplace_api
from api import organization as organization_api
from api import security as security_api

# Storage and the protection layer are attached to the app rather than imported by
# every module, so a test can hand the same routes a different database without
# monkeypatching an import somewhere else.
from db import get as _get_database  # noqa: E402

app = FastAPI(
    title="Symbio API",
    version="0.1.0",
    description=(
        "Circular-economy waste matchmaking. The LLM only identifies materials; all match scores come "
        "from a deterministic engine over a knowledge base. All prices and emission factors are demo values."
    ),
)

# Where the browser may call this API from. Cookies carry the session, so an
# authenticated deployment has to name its origins - "*" and credentials cannot both
# be true, and the code says so rather than silently choosing one.
_ALLOW_ORIGINS = [origin.strip() for origin in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if origin.strip()]

if _ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
# With nothing configured, no cross-origin middleware is installed at all: a request from
# another site then simply gets no `Access-Control-Allow-Origin` header, and the browser
# keeps its answer to itself. That is the right default for an API whose cookie is the
# session - `*` alongside credentials is not a thing a browser will honour anyway, and a
# deployment that forgets to name its origins should fail closed rather than open.
app.state.database = _get_database()
for _router in (auth_api.router, organization_api.router, marketplace_api.router):
    app.include_router(_router)
security_api.install(app)


# ---------------------------------------------------------------------------
# Error handling - every failure returns JSON the UI can render
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    """A reader gets one sentence and something to quote; the log gets the traceback.

    Nothing else leaves: no file paths, no SQL, no provider URLs. An operator who has
    the id can find the frames, a visitor who does not can be told "try again".
    """
    import logging

    correlation = str(request.scope.get("symbio_correlation") or "")[:8]
    logging.getLogger("symbio").exception("unhandled error %s on %s", correlation, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Symbio could not complete that request. The problem is recorded - try again, and if it "
            "persists, quote this reference.",
            "correlation": correlation or None,
            "error_class": exc.__class__.__name__,
        },
    )


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "Symbio API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": [
            "POST /api/analyze",
            "POST /api/matches",
            "GET  /api/matches/{analysis_id}/{recipient_id}",
            "GET  /api/analyses",
            "GET  /api/analyses/{analysis_id}",
            "GET  /api/materials",
            "GET  /api/recipients",
            "GET  /api/dashboard",
            "GET  /api/impact",
            "GET  /api/map",
            "POST /api/chat",
            "POST /api/upload",
            "GET  /api/health",
        ],
        "demo_data": True,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    """The short answer: is this process serving requests, and on what."""
    from services import geo  # noqa: PLC0415

    storage_state = persistence.describe()
    # "degraded" means one thing here: storage that was configured and is not
    # answering. Running with no database at all is a supported mode - the seeded
    # network, the analysis pipeline and the public marketplace all work - and saying
    # "degraded" about it would teach a reader to ignore the word.
    degraded = storage_state["configured"] and not storage_state["reachable"]
    return {
        "status": "degraded" if degraded else "ok",
        "persistence": (
            "database" if storage_state["reachable"] else ("unreachable" if degraded else "session-only")
        ),
        "demo_data": True,
        "materials": len(MATERIALS),
        "recipients": len(loader.get_recipients()),
        "analyses_stored": storage.count(),
        "ollama": ollama_status(),
        "storage": storage_state,
        "geography": {
            "geocoding": geo.status()["geocoding"]["state"],
            "routing": geo.status()["routing"]["state"],
        },
    }


@app.get("/api/status")
def status() -> dict[str, Any]:
    """What is real in this deployment, in one screen.

    Three kinds of data, kept apart because they behave differently: the seeded network
    (read-only, ships with the code), an organisation's own records (in the database,
    survive a restart), and a visitor's session (in memory, do not).
    """
    from services import geo  # noqa: PLC0415

    listing_state = listings_service.stats()
    return {
        "service": "Symbio API",
        "version": "0.1.0",
        "storage": persistence.describe(),
        "authentication": {
            "mode": "sessions" if persistence.describe()["reachable"] else "unavailable",
            "note": (
                "Accounts live in the same database as the rest of an organisation's data. With no database "
                "there are no accounts, and the public demo keeps working."
                if not persistence.describe()["reachable"]
                else "Argon2id password hashes, server-side sessions in an HttpOnly cookie."
            ),
        },
        "geography": geo.status(),
        "data": {
            "seeded": {
                "materials": len(MATERIALS),
                "recipients": len(loader.get_recipients()),
                "sources": len(loader.get_sources()),
                "listings": listing_state.get("seeded", 0),
            },
            "persistent": {**persistence.counts(), "listings": listing_state.get("persisted", 0)},
            "session": {
                "analyses": storage.count(),
                "listings": listing_state.get("session_published", 0),
            },
        },
        "limits": {
            "upload_bytes": file_service.MAX_BYTES,
            "upload_kinds": list(file_service.SUPPORTED),
            "rate_limiting": security_api._flag("SYMBIO_RATE_LIMIT", "on"),
        },
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest, http_request: Request) -> dict[str, Any]:
    if not (request.location or "").strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Tell us where this material is. The location is what distances are worked out from, and Symbio "
                "will not guess a city in your place."
            ),
        )
    if request.material_override_id and request.material_override_id not in MATERIALS_BY_ID:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{request.material_override_id}' is not a material in the Symbio knowledge base. "
                "A correction can only select a known material."
            ),
        )
    try:
        analysis = analysis_service.build_analysis(request.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Seed data missing: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from api.deps import actor_of

    actor = actor_of(http_request)
    saved = persistence.persist_analysis(analysis, actor=actor) if actor is not None else None
    return {
        "analysis": analysis,
        "matches": analysis["matches"],
        "totals": analysis["totals"],
        "warnings": analysis["warnings"],
        "intelligence": explain_service.material_intelligence(analysis),
        "demo_data": True,
        # Which of the three kinds of data this is: a signed-in tenant's saved record,
        # or a visitor's session result. The page says so in the same words.
        "saved": bool(saved),
        "reference": (saved or {}).get("reference"),
        "organization_id": (saved or {}).get("organization_id"),
        "persistence": persistence.describe(),
    }


@app.get("/api/intelligence")
def intelligence(analysis_id: str = Query(...)) -> dict[str, Any]:
    """The material card for a stored analysis (the analyze response carries the same block)."""
    analysis = storage.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
    return {**explain_service.material_intelligence(analysis), "analysis_id": analysis_id, "demo_data": True}


@app.get("/api/analyses")
def list_analyses(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    analyses = storage.all_newest_first()[:limit]
    return {
        "analyses": [
            {
                "id": a["id"],
                "created_at": a["created_at"],
                "material": a["material"]["name"],
                "source_type": a["source"]["source_type"],
                "location": a["source"]["location"],
                "quantity_t_per_month": a["source"]["quantity_t_per_month"],
                "confidence": a["identification"]["confidence"],
                "matches": len(a["matches"]),
                "seeded": a.get("seeded", False),
            }
            for a in analyses
        ],
        "count": len(analyses),
    }


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict[str, Any]:
    analysis = storage.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
    return analysis


@app.get("/api/analyses/{analysis_id}/completeness")
def analysis_completeness(analysis_id: str) -> dict[str, Any]:
    """How complete this analysis's input is, and what to ask for (§3).

    Recomputed from the stored record rather than replayed from the cached response,
    so a corrected analysis cannot report a stale percentage.
    """
    analysis = storage.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
    stored = analysis.get("completeness")
    if stored:
        return stored
    # A seeded analysis written before this field existed: rebuild the input the
    # assessment reads out of the stored record rather than reporting a gap.
    source = analysis["source"]
    return completeness_service.assess(
        {
            "material_description": analysis.get("raw_description"),
            "composition": analysis.get("composition_raw"),
            "quantity": source["quantity_t_per_month"],
            "unit": source["unit"],
            "location": source["location"],
            "frequency": source["frequency"],
            "physical_state": analysis.get("physical_state"),
            "moisture_percent": analysis.get("moisture_percent"),
            "contaminants": analysis.get("contaminants"),
            "intended_use": analysis.get("intended_use"),
        },
        analysis["material"],
        loader.get_recipients(),
        [match["recipient"] for match in analysis.get("matches") or []],
    )


@app.get("/api/logistics")
def logistics_assumptions(
    distance_km: float | None = Query(default=None, ge=0, le=2000),
    quantity_t_per_month: float | None = Query(default=None, ge=0, le=100_000),
    value_inr_per_tonne: float | None = Query(default=None, ge=0, le=10_000_000),
) -> dict[str, Any]:
    """The freight assumptions behind every transport figure, and a calculator.

    The same eight constants go into every card's `transport` block, so publishing
    them here is what lets a reader check the arithmetic instead of trusting it. Pass
    all three numbers to run the same function the cards use - a partial query returns
    the assumptions only, rather than a plausible-looking half-calculation.
    """
    payload: dict[str, Any] = {
        "assumptions": [dict(zip(("key", "value", "unit", "note"), row)) for row in logistics.ASSUMPTIONS],
        "bands": {
            "viable_at_most": logistics.MARGINAL_RATIO,
            "marginal_at_most": logistics.VIABLE_RATIO,
            "meaning": (
                "burden to value ratio: haulage cost divided by the material value it moves. Under "
                f"{logistics.MARGINAL_RATIO:.0%} the load pays for its own trip easily; above "
                f"{logistics.VIABLE_RATIO:.0%} the freight costs more than the material."
            ),
        },
        "note": (
            "These are published demo figures, not a tariff. They are deliberately visible so that a transport "
            "verdict can be recomputed by hand; a real deployment would replace them with contracted rates."
        ),
        "estimate": None,
        "demo_data": True,
    }
    given = [distance_km, quantity_t_per_month, value_inr_per_tonne]
    if all(value is not None for value in given):
        tonnes = float(quantity_t_per_month or 0.0)
        per_tonne = float(value_inr_per_tonne or 0.0)
        estimate = logistics.estimate(float(distance_km or 0.0), tonnes, round(tonnes * per_tonne, 2), per_tonne)
        payload["estimate"] = estimate
        # Quote the disclaimer from the estimate itself, so this route can never
        # carry a different copy of that sentence from the one the cards show.
        payload["disclaimer"] = estimate["disclaimer"]
        payload["inputs"] = {
            "distance_km": distance_km,
            "quantity_t_per_month": quantity_t_per_month,
            "value_inr_per_tonne": value_inr_per_tonne,
        }
    else:
        payload["estimate"] = None
        payload["how_to_calculate"] = (
            "Pass distance_km, quantity_t_per_month and value_inr_per_tonne to run the calculation this build uses."
        )
    return payload


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


def _apply_filters(analysis: dict, params: dict[str, Any]) -> list[dict]:
    out = []
    for m in analysis["matches"]:
        if params.get("sector") and m["recipient"]["sector"] != params["sector"]:
            continue
        # A route with no measurable distance is kept, not dropped: the sender's town
        # being unplaced is not evidence that the partner is too far away. It stays
        # flagged as unplaced in every view that reads it.
        if (
            params.get("max_distance_km") is not None
            and m["distance_km"] is not None
            and m["distance_km"] > params["max_distance_km"]
        ):
            continue
        if m["overall_score"] < (params.get("min_match_score") or 0):
            continue
        if params.get("min_quantity") is not None and m["matched_quantity_t_per_month"] < params["min_quantity"]:
            continue
        if params.get("reuse_type") and m["reuse_type"] != params["reuse_type"]:
            continue
        if params.get("processing") == "direct" and m["reuse_type"] != "DIRECT_REUSE":
            continue
        if params.get("processing") == "processing_required" and m["reuse_type"] == "DIRECT_REUSE":
            continue
        if params.get("min_estimated_value") is not None and m["estimated_value_inr_per_month"] < params["min_estimated_value"]:
            continue
        if params.get("safety_level") and m["safety_level"] != params["safety_level"]:
            continue
        if params.get("partner_type") and partner_type(m["recipient"]["sector"]) != params["partner_type"]:
            continue
        out.append(m)
    return out


def _cards(matches: list[dict], analyses: dict[str, dict]) -> list[dict]:
    cards = []
    for m in matches:
        analysis = analyses[m["analysis_id"]]
        # An external route is attached only from the cache here: fourteen cards must
        # not become fourteen calls to a shared public router on one page load. The
        # detail page for the route someone is reading makes the live call.
        route = _route_for(analysis, m, live=False)
        estimate = _transport_for(m)
        if route and estimate is not None:
            estimate = {**estimate, "route": route}
        cards.append(
            {
                "id": m["id"],
                "analysis_id": m["analysis_id"],
                "material": analysis["material"]["name"],
                "material_id": analysis["material"]["id"],
                "company_name": m["recipient"]["company_name"],
                "sector": m["recipient"]["sector"],
                "sector_label": SECTOR_LABELS.get(m["recipient"]["sector"], m["recipient"]["sector"]),
                "location": m["recipient"]["location"],
                "latitude": m["recipient"]["latitude"],
                "longitude": m["recipient"]["longitude"],
                "score": m["overall_score"],
                "distance_km": m["distance_km"],
                "reuse_type": m["reuse_type"],
                "safety_level": m["safety_level"],
                "matched_quantity_t_per_month": m["matched_quantity_t_per_month"],
                "allocated_t_per_month": m.get("allocated_t_per_month", 0.0),
                "required_quantity_range_t_per_month": m["required_quantity_range_t_per_month"],
                "available_quantity_t_per_month": m["available_quantity_t_per_month"],
                "estimated_value_inr_per_month": m["estimated_value_inr_per_month"],
                "estimated_co2e_t_per_month": m["estimated_co2e_t_per_month"],
                "breakdown": m["breakdown"],
                "reasons": m["reasons"],
                "cautions": m["cautions"],
                "reuse_pathway": m["reuse_pathway"]["steps"],
                "source_location": analysis["source"]["location"],
                "source_latitude": analysis["source"]["latitude"],
                "source_longitude": analysis["source"]["longitude"],
                "partner_type": partner_type(m["recipient"]["sector"]),
                "partner_type_label": PARTNER_TYPE_LABELS[partner_type(m["recipient"]["sector"])],
                "processing_capability": m["recipient"]["processing_capability"],
                "accepted_materials": _material_names(m["recipient"]["accepted_materials"]),
                "estimated_price_inr_per_tonne": m["recipient"]["estimated_price_inr_per_tonne"],
                # The full record travels along so the map popup and the match
                # card can never disagree about what a recipient accepts.
                "recipient": m["recipient"],
                "summary": m["summary"],
                # §8: the haul, priced from the demo freight assumptions. It rides on
                # the card so the list, the map, Compare and the scenario table all
                # quote one number instead of each deriving their own.
                "transport": estimate,
                **({"route": route} if route else {}),
            }
        )
    return cards


def _route_for(analysis: dict, match: dict, *, live: bool) -> dict | None:
    """Road distance and drive time for one route, from the configured provider.

    This is an overlay, not an input. The engine scored a straight-line distance and the
    freight estimate was built on that number; what comes back from here is shown next
    to it, labelled as external, with the time it was fetched. So a provider going away,
    changing its mind or changing its prices cannot silently move a recommendation (§8).

    `live=False` is the results list: it may answer from cache but must not start a
    routing call per card. `live=True` is the detail page for the one route someone is
    actually reading.
    """
    from services import geo  # noqa: PLC0415

    source = analysis.get("source") or {}
    if not source.get("location_resolved") or source.get("latitude") is None:
        return None
    recipient = match.get("recipient") or {}
    if recipient.get("latitude") is None or recipient.get("longitude") is None:
        return None
    result = geo.route(
        (float(source["latitude"]), float(source["longitude"])),
        (float(recipient["latitude"]), float(recipient["longitude"])),
        live=live,
    )
    if not result.ok:
        return None
    payload = result.payload
    straight_line = match.get("distance_km")
    route_km = float(payload.get("route_distance_km") or 0.0)
    if not route_km:
        return None
    return {
        "distance_km": round(route_km, 1),
        "duration_minutes": payload.get("route_duration_minutes"),
        "straight_line_km": straight_line,
        "difference_percent": (
            round(((route_km - float(straight_line)) / float(straight_line)) * 100.0, 1)
            if straight_line
            else None
        ),
        "fetched_at": payload.get("fetched_at"),
        "source": "external routing",
        "note": (
            "Road distance and drive time from an external routing service. The freight estimate is calculated on "
            "the straight-line distance the engine scored, so this figure is shown for context and never replaces "
            "it."
        ),
    }


def _transport_for(match: dict) -> dict | None:
    """The §8 estimate for one serialised match, or None when it cannot be priced.

    `unit_value` is the engine's own `unit_value_inr_per_tonne` applied to the stored
    dict form, so the per-tonne figure the freight model reads is the same one the
    value score used. This function adds no judgement of its own.
    """
    if match.get("distance_km") is None:
        # No coordinates, so no distance, so no haulage figure. Returning nothing is
        # the whole point: `logistics.estimate(0, ...)` would read as a free trip and
        # a route that is always viable.
        return None
    quantity = float(match.get("matched_quantity_t_per_month") or 0.0)
    value = float(match.get("estimated_value_inr_per_month") or 0.0)
    return logistics.estimate(
        float(match.get("distance_km") or 0.0),
        quantity,
        value,
        value / quantity if quantity > 0 else 0.0,
    )


"""Optimisation modes: what "best" means for this list.

Each mode re-orders the *same* filtered result set by a different measured
quantity, so switching mode changes the ranking rather than relabelling it. The
canonical weighted score is never recomputed here, and no mode can rescue a
route the safety layer refused: filtering and gating happen before this runs.

Ties break on distance then id, so the same input always renders the same list -
a ranking that reshuffles itself between page loads is not credible in a demo.
"""
def _km(c: dict) -> tuple[bool, float]:
    """Sort key for distance: unplaced routes come last instead of posing as 0 km."""
    value = c["distance_km"]
    return (value is None, float(value or 0.0))


SORTS = {
    "score": lambda c: (-c["score"], *_km(c), c["id"]),
    "distance": lambda c: (*_km(c), -c["score"], c["id"]),
    "value": lambda c: (-c["estimated_value_inr_per_month"], -c["score"], c["id"]),
    "environmental": lambda c: (-c["estimated_co2e_t_per_month"], -c["score"], c["id"]),
    "least_processing": lambda c: (
        processing_burden(c["reuse_type"]),
        -c["score"],
        *_km(c),
        c["id"],
    ),
}


def sort_cards(cards: list[dict], sort: str | None) -> list[dict]:
    return sorted(cards, key=SORTS.get(sort or "score", SORTS["score"]))


SORT_LABELS = {
    "score": "best overall score",
    "distance": "distance",
    "value": "estimated value",
    "environmental": "CO₂e avoided",
    "least_processing": "processing burden",
}


def mode_note(cards: list[dict], sort: str) -> str | None:
    """Say out loud when an optimisation mode cannot change the order.

    A ranking that looks frozen is otherwise read as a broken control. The demo
    data really does contain cases where every route is identical on one measure
    (fly ash, for instance, is never direct reuse here), and the honest answer is
    to explain that rather than to invent a difference.
    """
    if sort == "score" or not cards:
        return None
    key = {
        "distance": lambda c: _km(c),
        "value": lambda c: c["estimated_value_inr_per_month"],
        "environmental": lambda c: c["estimated_co2e_t_per_month"],
        "least_processing": lambda c: processing_burden(c["reuse_type"]),
    }[sort]
    label = SORT_LABELS[sort]
    if len({key(c) for c in cards}) == 1:
        return f"Every route in this result set is the same on {label}, so the order stays as best overall."
    if [c["id"] for c in cards] == [c["id"] for c in sort_cards(list(cards), "score")]:
        return f"The best overall route is also the best on {label}, so this order matches best overall."
    return None


def match_filters(
    sector: str | None = Query(default=None),
    max_distance_km: float | None = Query(default=None, gt=0, le=2000),
    min_match_score: float = Query(default=0, ge=0, le=100),
    min_quantity: float | None = Query(default=None, ge=0),
    reuse_type: ReuseType | None = Query(default=None),
    processing: str | None = Query(default=None, pattern="^(direct|processing_required)$"),
    min_estimated_value: float | None = Query(default=None, ge=0),
    safety_level: SafetyLevel | None = Query(default=None),
    partner_type_value: str | None = Query(
        default=None,
        alias="partner_type",
        pattern="^(industry|sme|recycler|processing|agriculture|community)$",
    ),
    sort: str = Query(default="score", pattern="^(score|distance|value|environmental|least_processing)$"),
) -> dict[str, Any]:
    """Filters and sort shared by /api/matches and /api/map.

    Declared once on purpose. The map has to show *the same result set* as the
    list, and two independent copies of a parameter list is exactly how those
    drift apart.
    """
    return {
        "sector": sector,
        "max_distance_km": max_distance_km,
        "min_match_score": min_match_score,
        "min_quantity": min_quantity,
        "reuse_type": reuse_type.value if reuse_type else None,
        "processing": processing,
        "min_estimated_value": min_estimated_value,
        "safety_level": safety_level.value if safety_level else None,
        "partner_type": partner_type_value,
        "sort": sort,
    }


def _ranked_analysis(analysis: dict, params: dict[str, Any]) -> tuple[list[dict], int, int]:
    """Filter, card and sort one analysis. Used by the list, the map and What-If."""
    filtered = _apply_filters(analysis, params)
    cards = sort_cards(_cards(filtered, {analysis["id"]: analysis}), params.get("sort"))
    return cards, len(cards), len(analysis["matches"])


def _ranked(analysis_id: str | None, params: dict[str, Any]) -> tuple[list[dict], int, int]:
    """Filter, card and sort. Shared by the matches list and the map view."""
    if analysis_id:
        analysis = storage.get(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
        return _ranked_analysis(analysis, params)

    stored = storage.all_newest_first()
    if not stored:
        raise HTTPException(status_code=404, detail="No analyses yet - run POST /api/analyze first")
    analyses = {a["id"]: a for a in stored}
    filtered = [m for a in stored for m in _apply_filters(a, params)]
    cards = sort_cards(_cards(filtered, analyses), params.get("sort"))
    return cards, len(cards), sum(len(a["matches"]) for a in stored)


@app.post("/api/matches")
def matches(
    analysis_id: str | None = Query(default=None),
    params: dict[str, Any] = Depends(match_filters),
) -> dict[str, Any]:
    cards, count, source_count = _ranked(analysis_id, params)
    return {
        "analysis_id": analysis_id,
        "matches": cards,
        "count": count,
        "filtered_from": source_count,
        "sort": params["sort"],
        "sort_label": SORT_LABELS[params["sort"]],
        "sort_note": mode_note(cards, params["sort"]),
        "demo_data": True,
    }


@app.get("/api/matches/{analysis_id}/{recipient_id}")
def match_detail(analysis_id: str, recipient_id: str) -> dict[str, Any]:
    analysis = storage.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
    match = analysis_service.get_match(analysis_id, recipient_id)
    if not match:
        raise HTTPException(status_code=404, detail=f"No match for recipient '{recipient_id}' in this analysis")
    # Copied before the external route is attached: the stored analysis must not gain
    # fields a later request would read as if the engine had produced them.
    transport_estimate = _transport_for(match)
    route = _route_for(analysis, match, live=True)
    if route is not None:
        match = {**match, "route": route}
        if transport_estimate is not None:
            transport_estimate = {**transport_estimate, "route": route}
    return {
        "match": match,
        "analysis": {
            "id": analysis["id"],
            "source": analysis["source"],
            "material": analysis["material"],
            "identification": analysis["identification"],
            "totals": analysis["totals"],
        },
        # Read from the engine, so this page cannot show a weighting the
        # scoring code has moved away from.
        "weights_used": dict(WEIGHTS),
        "provenance": explain_service.provenance_for(analysis, match),
        # §5/§7: what this partner actually makes, and where the stream lands in
        # their process. Explanation only - the score above was computed without it.
        "industry_profile": profiles_service.intelligence_note(
            analysis["identification"]["material_id"], match["recipient"]
        ),
        # §8: the same estimate the cards carry, from the same helper. `route` is the
        # external overlay described above, and it is None when nothing could be routed.
        "transport": transport_estimate,
        "route": route,
        "demo_data": True,
    }


def _pathway_rows(cards: list[dict]) -> list[dict]:
    """Collapse ranked matches into the distinct routes they represent.

    Two partners that turn the same material into the same product in the same
    sector are one pathway, shown with its best-ranked partner and the others
    named alongside it. Nothing is re-scored: this is a grouping of the engine's
    own output, and the order follows whichever optimisation mode produced the
    cards - so "highest value" really does make a different pathway primary.
    """
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for card in cards:
        steps = card["reuse_pathway"]
        if len(steps) != 5:
            continue
        key = (steps[2], steps[3], steps[4])
        row = grouped.get(key)
        if row is None:
            grouped[key] = {
                "pathway": list(steps),
                "processing": steps[2],
                "sector_label": steps[3],
                "product": steps[4],
                "match_id": card["id"],
                "partner": card["company_name"],
                "partner_type_label": card["partner_type_label"],
                "score": card["score"],
                "distance_km": card["distance_km"],
                "reuse_type": card["reuse_type"],
                "safety_level": card["safety_level"],
                "processing_capability": card["processing_capability"],
                "matched_quantity_t_per_month": card["matched_quantity_t_per_month"],
                "estimated_value_inr_per_month": card["estimated_value_inr_per_month"],
                "estimated_co2e_t_per_month": card["estimated_co2e_t_per_month"],
                "summary": card["summary"],
                "other_partners": [],
            }
        else:
            row["other_partners"].append(card["company_name"])
    return list(grouped.values())


@app.get("/api/pathways")
def pathways(
    analysis_id: str = Query(...),
    params: dict[str, Any] = Depends(match_filters),
) -> dict[str, Any]:
    """Primary and alternative reuse pathways for one analysis.

    The alternatives exist only where the engine produced them: a material with
    one compatible recipient gets one pathway row, not a padded list.
    """
    cards, shown, source_count = _ranked(analysis_id, params)
    rows = _pathway_rows(cards)
    analysis = storage.get(analysis_id)
    excluded = analysis.get("excluded", []) if analysis else []
    return {
        "analysis_id": analysis_id,
        "material": analysis["material"]["name"] if analysis else None,
        "material_id": analysis["material"]["id"] if analysis else None,
        "sort": params.get("sort") or "score",
        "filters_applied": {k: v for k, v in params.items() if v not in (None, 0, "score")},
        "primary": rows[0] if rows else None,
        "alternatives": rows[1:] if len(rows) > 1 else [],
        "pathway_count": len(rows),
        "sort_label": SORT_LABELS[params.get("sort") or "score"],
        "sort_note": mode_note(cards, params.get("sort") or "score"),
        "partner_count": shown,
        "scored_partners": source_count,
        "excluded_by_safety": len(excluded),
        "demo_data": True,
    }


@app.post("/api/scenario")
def scenario(request: ScenarioRequest, params: dict[str, Any] = Depends(match_filters)) -> dict[str, Any]:
    """A temporary re-run of the matching for changed quantity / cadence / place.

    Reuses the same engine call the analysis used, so the numbers are comparable
    by construction. The stored analysis is not touched and the scenario is not
    saved - clearing it is enough to return to the original.
    """
    base = storage.get(request.analysis_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"Analysis '{request.analysis_id}' not found")

    variant = analysis_service.build_scenario(
        base,
        {
            "quantity": request.quantity,
            "unit": request.unit,
            "frequency": request.frequency.value if request.frequency else None,
            "location": request.location,
        },
    )

    cards, shown, source_count = _ranked_analysis(variant, params)

    # §11 rules narrow the list the engine produced. They run after safety and after
    # scoring, so a scenario can hide a route it does not want but cannot surface one
    # the safety layer refused.
    rules = scenarios_service.rules_from(request.model_dump())
    dropped_by_rule: list[dict[str, Any]] = []
    if rules:
        cards, dropped_by_rule = scenarios_service.apply_rules(cards, rules)
        shown = len(cards)

    # Rank comparison: what this change did to each partner's standing.
    original_ranks = {m["recipient"]["id"]: i + 1 for i, m in enumerate(base["matches"])}
    for position, card in enumerate(cards):
        recipient_id = card["id"].split(":", 1)[1]
        before = original_ranks.get(recipient_id)
        card["original_rank"] = before
        card["scenario_rank"] = position + 1
        card["rank_change"] = None if before is None else before - (position + 1)
        card["is_new"] = before is None

    original_totals = base["totals"]
    return {
        "analysis_id": request.analysis_id,
        "scenario": {
            "changed": variant["changed"],
            "source": variant["source"],
            "warnings": variant["warnings"],
            "completeness": variant["completeness"],
        },
        "matches": cards,
        "count": shown,
        "scored_partners": source_count,
        "totals": variant["totals"],
        "totals_change": {
            "allocated_t_per_month": round(variant["totals"]["allocated_t_per_month"] - original_totals["allocated_t_per_month"], 3),
            "estimated_value_inr_per_month": round(
                variant["totals"]["estimated_value_inr_per_month"] - original_totals["estimated_value_inr_per_month"], 2
            ),
            "estimated_co2e_avoided_t_per_month": round(
                variant["totals"]["estimated_co2e_avoided_t_per_month"]
                - original_totals["estimated_co2e_avoided_t_per_month"],
                3,
            ),
            "viable_matches": variant["totals"]["viable_matches"] - original_totals["viable_matches"],
            "potential_matches": variant["totals"]["potential_matches"] - original_totals["potential_matches"],
        },
        "original": {
            "source": base["source"],
            "totals": original_totals,
            "top_partner": base["matches"][0]["recipient"]["company_name"] if base["matches"] else None,
        },
        "sort": params.get("sort") or "score",
        # Named back to the user, so a filtered list always says what filtered it.
        "rules": {scenarios_service.RULE_LABELS[key]: value for key, value in rules.items()},
        "dropped_by_rule": dropped_by_rule,
        "transport": scenarios_service.transport_rollup(cards),
        "demo_data": True,
        "note": "Temporary scenario. The stored analysis is unchanged and safety rules were applied again.",
    }


@app.post("/api/scenarios/compare")
def compare_scenarios(request: ScenarioCompareRequest) -> dict[str, Any]:
    """Two to four configurations of one analysis, side by side (§11).

    Each configuration is the same `build_scenario` call the single what-if uses -
    same engine, same safety layer, same freight estimate - so the columns are
    comparable and nothing here is a second scoring system. The first configuration
    is the baseline every other one is measured against; it is normal for it to carry
    no changes at all, which is what makes the deltas mean something.
    """
    base = storage.get(request.analysis_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"Analysis '{request.analysis_id}' not found")

    params = {"sort": "score", "analysis_id": request.analysis_id}
    columns = []
    for config in request.configs:
        payload = config.model_dump()
        variant = analysis_service.build_scenario(
            base,
            {
                "quantity": payload.get("quantity"),
                "unit": payload.get("unit"),
                "frequency": payload["frequency"].value if payload.get("frequency") else None,
                "location": payload.get("location"),
            },
        )
        cards, _shown, source_count = _ranked_analysis(variant, params)
        rules = scenarios_service.rules_from(payload)
        cards, dropped = scenarios_service.apply_rules(cards, rules) if rules else (cards, [])
        columns.append(
            scenarios_service.summarise(
                label=config.label,
                changed=variant["changed"],
                warnings=variant["warnings"],
                cards=cards,
                totals=variant["totals"],
                scored_partners=source_count,
                rules=rules,
                dropped=dropped,
                sort_label="Best by match score",
            )
        )

    baseline = columns[0]
    for column in columns[1:]:
        column["delta_vs_baseline"] = {
            "match_count": column["match_count"] - baseline["match_count"],
            "estimated_value_inr_per_month": round(
                column["totals"]["estimated_value_inr_per_month"] - baseline["totals"]["estimated_value_inr_per_month"], 2
            ),
            "allocated_t_per_month": round(
                column["totals"]["allocated_t_per_month"] - baseline["totals"]["allocated_t_per_month"], 3
            ),
            "estimated_co2e_t_per_month": round(
                column["totals"]["estimated_co2e_avoided_t_per_month"]
                - baseline["totals"]["estimated_co2e_avoided_t_per_month"],
                3,
            ),
            "transport_cost_inr_per_month": round(
                column["transport"]["transport_cost_inr_per_month"] - baseline["transport"]["transport_cost_inr_per_month"], 2
            ),
            "net_economic_potential_inr_per_month": round(
                column["transport"]["net_economic_potential_inr_per_month"]
                - baseline["transport"]["net_economic_potential_inr_per_month"],
                2,
            ),
            "best_match_moved": (column["best_match"] or {}).get("company_name") != (baseline["best_match"] or {}).get(
                "company_name"
            ),
        }

    return {
        "analysis_id": request.analysis_id,
        "configurations": columns,
        "baseline_label": baseline["label"],
        "columns": [
            "best_match",
            "score",
            "distance",
            "value",
            "co2e",
            "transport_viability",
            "net_economic_potential",
            "viable_at",
        ],
        "note": (
            "Each configuration re-runs the deterministic engine over the same stored analysis; the first one is the "
            "baseline. Transport figures are this build's estimate from demo freight assumptions, never a quote."
        ),
        "demo_data": True,
    }


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------


@app.get("/api/materials")
def materials() -> dict[str, Any]:
    """The knowledge base, as the UI reads it.

    `keywords` are the matcher's trigger tokens; they are shown here under the
    name they deserve on a reference page - the hints a material is recognised
    from - rather than hidden, because "how do I know this is fly ash" is a
    question the roadmap asks of the KB. `gate_rules` is generated by the safety
    layer from this same record, so the page states the rules that will actually
    be applied instead of a second copy of them in prose.
    """
    rows = []
    for m in MATERIALS:
        row = {k: v for k, v in m.items() if k != "keywords"}
        row["identification_hints"] = m["keywords"]
        row["gate_rules"] = gate_rules_for(m)
        # Every record in this build was authored for the demo; none has been
        # checked against a lab report or a regulatory source.
        row["verification"] = "demo"
        rows.append(row)
    return {
        "materials": rows,
        "count": len(MATERIALS),
        "note": "Prices and CO2e factors are demo values stored in the knowledge base.",
        "verification_note": (
            f"Demo knowledge base: {len(MATERIALS)} material records in this build. Nothing here is verified against a "
            "laboratory report or a regulatory source, and a verified record would be marked verification: \"verified\"."
        ),
        "demo_data": True,
    }


@app.get("/api/materials/{material_id}/similar")
def similar_materials(
    material_id: str,
    limit: int = Query(default=6, ge=1, le=30),
    min_similarity: float = Query(default=0.0, ge=0, le=100),
) -> dict[str, Any]:
    """Which knowledge-base materials this one resembles - and what that does not mean.

    The number is a Jaccard overlap over the KB's own fields, computed by
    `knowledge_base/similarity.py`. No model is involved, and nothing in the ranking
    pipeline imports that module: a similar material is a lead worth checking, not an
    approval. Where the lookalike is the more hazardous of the two, it is said in
    `differences` before the score is.
    """
    source = MATERIALS_BY_ID.get(material_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"'{material_id}' is not a material in the Symbio knowledge base.",
        )
    return {
        "material": {
            "id": source["id"],
            "name": source["name"],
            "category": source.get("category"),
            "safety_level": source.get("safety_level"),
            "requires_processing": bool(source.get("requires_processing")),
            "typical_price_inr_per_tonne": source.get("typical_price_inr_per_tonne"),
        },
        "results": similarity.similar_to(material_id, limit=limit, min_score=min_similarity),
        "least_similar": similarity.most_distinct(material_id, limit=3),
        "knowledge_base_size": len(MATERIALS),
        "method": (
            "Jaccard overlap of properties, reuse categories and compatible sectors, "
            "plus a bonus for sharing a category"
        ),
        "score_note": (
            "Similarity is a description of the material, not a compatibility ruling. The safety layer and each "
            "recipient's accepted-material list still decide whether a substitute can be used, and this endpoint "
            "cannot change either."
        ),
        "demo_data": True,
    }


@app.get("/api/recipients")
def recipients(sector: str | None = Query(default=None)) -> dict[str, Any]:
    rows = loader.get_recipients()
    if sector:
        rows = [r for r in rows if r["sector"] == sector]
    return {
        "recipients": rows,
        "count": len(rows),
        "sectors": [{"sector": s, "label": label} for s, label in sorted(SECTOR_LABELS.items())],
        "note": "Demo data - fictional companies with plausible coordinates around Chennai.",
        "demo_data": True,
    }


# ---------------------------------------------------------------------------
# Marketplace listings (§6)
# ---------------------------------------------------------------------------


@app.get("/api/listings")
def listings(
    kind: str | None = Query(default=None),
    material_id: str | None = Query(default=None),
    status: str | None = Query(default="open"),
) -> dict[str, Any]:
    """Demand and supply listings, plus the balance between them."""
    if kind and kind not in ("demand", "supply"):
        raise HTTPException(status_code=422, detail="kind must be 'demand' or 'supply'")
    rows = listings_service.all_listings(kind=kind, material_id=material_id, status=status)
    return {
        "listings": rows,
        "count": len(rows),
        "stats": listings_service.stats(),
        "persistence_note": (
            "Three sources, kept distinguishable on every row: the seeded network (backend/data/listings.json, "
            "read-only), listings saved to an organisation (the database, they survive a restart), and anything "
            "published in this session by someone not signed in (memory, gone on restart)."
        ),
        "persistence": persistence.describe(),
        "note": (
            "A listing is one party's stated need or offer. Prices and quantities are copied from the partner and "
            "source records they belong to rather than entered freely, so a listing can never drift from what that "
            "organisation actually handles."
        ),
        "demo_data": True,
    }


@app.post("/api/listings", status_code=201)
def publish_listing(request: ListingRequest, http_request: Request) -> dict[str, Any]:
    """Publish a listing for this session, or for an organisation if someone is signed in.

    Every field is validated against the knowledge base and the demo partner records,
    and the language model is never consulted: an invented demand listing would look
    exactly like a real one in the UI, which is the failure mode this endpoint exists
    to prevent.

    One route serves both a visitor and a member, so the role check is inside it: a
    signed-in viewer reads the marketplace, it does not add to it. The permission is
    the same `publish_listing` row the edit and pause routes use, so the table in
    `services/rbac.py` stays the only place the three roles are defined.
    """
    from api.deps import actor_of  # noqa: PLC0415 - same local import the analyze route uses

    actor = actor_of(http_request)
    if actor is not None and not actor.can("publish_listing"):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Your role in {actor.organization['name']} is {actor.role_label}: it can read the marketplace but "
                "not publish to it. An operator or an administrator has to add the listing."
            ),
        )
    try:
        created = listings_service.publish(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except persistence.PersistenceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    persisted = bool(created.get("persisted"))
    return {
        "listing": created,
        "persisted": persisted,
        "note": (
            "Saved to your organisation. It is here after a restart, and your members can see it under "
            "Marketplace - Yours."
            if persisted
            else "Held in memory for this session only: nobody is signed in, so there is no organisation to "
            "save it to. Publish it from an account to keep it."
        ),
        "demo_data": not persisted,
    }


@app.get("/api/listings/{listing_id}")
def listing_detail(listing_id: str) -> dict[str, Any]:
    listing = listings_service.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing '{listing_id}' does not exist.")
    return {"listing": listing, "as_row": listings_service.to_row(listing), "demo_data": True}


@app.post("/api/listings/match")
def match_listing(payload: dict[str, Any]) -> dict[str, Any]:
    """Counterparties and engine-ranked partners for one listing.

    Accepts `{"listing_id": "..."}` - the usual case, since a listing that exists has
    already been validated. An inline listing is accepted for what-if work, but then
    the same validation as a publish runs on it, so a hypothetical cannot skip the
    rules a real listing has to meet.
    """
    listing_id = payload.get("listing_id")
    if listing_id:
        listing = listings_service.get(listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail=f"Listing '{listing_id}' does not exist.")
        source = "stored listing"
    else:
        try:
            # Validated by the same rules as a publish, then dropped: a draft has to
            # meet them, but a what-if must not silently enter the marketplace.
            listing = listings_service.draft({**payload, "kind": payload.get("kind", "supply")})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        source = "draft listing (validated, not published)"
    result = listings_service.match(listing, limit=int(payload.get("limit", 8)))
    return {**result, "listing_source": source, "demo_data": True}


# ---------------------------------------------------------------------------
# Industry profiles (§5/§7)
# ---------------------------------------------------------------------------


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    """The seeded source records, for a supply listing that has to name a real one.

    A listing is only admissible if its party exists, so the form that creates one has
    to read from the same list the validator does - never from a free-text guess.
    """
    rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "sector": row["sector"],
            "location": row["location"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "material_hint": row["material_hint"],
            "description": row["description"],
        }
        for row in loader.get_sources()
    ]
    return {
        "sources": rows,
        "count": len(rows),
        "note": "Seeded demo facilities. A supply listing must name one of these ids.",
        "demo_data": True,
    }


@app.get("/api/profiles")
def sector_profiles() -> dict[str, Any]:
    """The sector templates behind the profiles, and how far they cover the pool.

    Coverage is reported because it is the honest number: 22 sectors in this build,
    a partner is either described by a template or it is not, and the UI has to say
    which of the two it is looking at.
    """
    rows = profiles_service.summary_rows()
    recipients = loader.get_recipients()
    covered = {row["sector"] for row in rows}
    return {
        "profiles": rows,
        "count": len(rows),
        "source": "backend/data/sector_profiles.json",
        "note": (
            "Per-sector templates authored for this demo build. A partner's own record - accepted materials, "
            "capabilities, quantity window, price - always takes precedence over a template line."
        ),
        "coverage": {
            "recipients_total": len(recipients),
            "recipients_with_template": len([r for r in recipients if r["sector"] in covered]),
            "uncovered_sectors": sorted({r["sector"] for r in recipients} - covered),
        },
        "demo_data": True,
    }


@app.get("/api/profiles/{recipient_id}")
def recipient_profile(recipient_id: str) -> dict[str, Any]:
    """One partner as a profile: supply, demand, capability and what it could become."""
    recipient = loader.get_recipient(recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail=f"Recipient '{recipient_id}' is not in the demo dataset.")
    return profiles_service.for_recipient(recipient)


# ---------------------------------------------------------------------------
# Dashboard / impact
# ---------------------------------------------------------------------------


@app.get("/api/material-flow")
def material_flow(analysis_id: str | None = Query(default=None)) -> dict[str, Any]:
    """The six-stage funnel (§9): generated, reusable, viable, matched, processed, reused.

    Every stage carries its own definition, and the two stages this dataset cannot
    tell apart - processed and reused - are reported as equal with the reason
    attached, rather than separated by an invented processing loss.
    """
    flow = material_flow_service.flow(analysis_id=analysis_id)
    if not analysis_id:
        # Reconciliation, not repetition: the funnel is computed from the same stored
        # analyses the impact numbers come from, so the two must agree. If they ever
        # stop agreeing, that is a bug in one of them.
        impact = dashboard_service.dashboard()["impact"]
        processed = flow["stages"][4]["tonnes_per_month"]
        gap = round(abs(processed - float(impact["tonnes_diverted"])), 3)
        flow["impact_dashboard"] = {
            "processed_tonnes_per_month": processed,
            "tonnes_analysed": impact["tonnes_analysed"],
            "tonnes_diverted": impact["tonnes_diverted"],
            "estimated_value_inr_per_month": impact["estimated_value_inr_per_month"],
            "estimated_co2e_t_per_month": impact["estimated_co2e_t_per_month"],
            "diversion_rate": impact["diversion_rate"],
            "matches_generated_tonnes": abs(flow["stages"][0]["tonnes_per_month"] - impact["tonnes_analysed"]) < 1e-6,
            "matches_diverted_tonnes": gap < 1e-6,
            "difference_tonnes": gap,
            "note": (
                "The same stored analyses the impact dashboard totals come from, so the funnel and the dashboard "
                "reconcile."
                if gap < 1e-6
                else "The dashboard sums what every partner was allocated, which can add up to more than the stream "
                f"itself when several partners take a share; the funnel caps each stage at the tonnage on offer. "
                f"The two differ by {gap} t/month here for that reason."
            ),
        }
    return flow


@app.get("/api/demand")
def demand_potential(
    material_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=40),
) -> dict[str, Any]:
    """Regional demand potential by area (§10) - capacity, not prediction.

    Areas are localities in the demo dataset, ranked by unfilled intake capacity,
    partner breadth, open listings and nearby unplaced supply. Nothing in here claims
    that a named company will buy anything; the dataset has no purchase intention in
    it, so a forecast would be a fabrication.
    """
    return demand_service.forecast(material_id, limit=limit)


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    return dashboard_service.dashboard()


@app.get("/api/impact")
def impact() -> dict[str, Any]:
    return dashboard_service.impact_summary()


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------


def _material_names(material_ids: list[str]) -> list[str]:
    """Accepted material ids as readable names.

    Recipients store ids like ``fly_ash`` because that is what the engine
    compares. A popup showing ``fly_ash`` is not the same thing as a claim about
    a material, so ids become knowledge-base names here and nowhere else.
    """
    return [MATERIALS_BY_ID.get(mid, {}).get("name", mid.replace("_", " ").title()) for mid in material_ids]


def _recipient_node(recipient: dict, card: dict | None = None) -> MapNode:
    """A recipient as a map node.

    The popup has to answer "could I actually send material here", so it carries
    the acceptance range and processing capability, not just a name. When the
    node comes from a scored match the match-level values win, because the
    safety layer can downgrade reuse type and safety below what the recipient
    record says.
    """
    kind = partner_type(recipient["sector"])
    extra: dict[str, Any] = {
        "sector_label": SECTOR_LABELS.get(recipient["sector"], recipient["sector"]),
        "partner_type": kind,
        "partner_type_label": PARTNER_TYPE_LABELS[kind],
        "accepted_materials": _material_names(recipient["accepted_materials"]),
        "required_quantity_range_t_per_month": [
            recipient["min_quantity_t_per_month"],
            recipient["max_quantity_t_per_month"],
        ],
        "processing_capability": recipient["processing_capability"],
        "safety_level": recipient["safety_level"],
        "reuse_type": recipient["reuse_type"],
        "estimated_price_inr_per_tonne": recipient["estimated_price_inr_per_tonne"],
        "scored": False,
    }
    if card:
        extra.update(
            {
                "scored": True,
                "match_score": card["score"],
                "distance_km": card["distance_km"],
                "material": card["material"],
                "reuse_type": card["reuse_type"],
                "safety_level": card["safety_level"],
                "matched_quantity_t_per_month": card["matched_quantity_t_per_month"],
                "estimated_value_inr_per_month": card["estimated_value_inr_per_month"],
                "summary": card["summary"],
            }
        )
    return MapNode(
        id=recipient["id"],
        name=recipient["company_name"],
        kind="recipient",
        sector=recipient["sector"],
        latitude=recipient["latitude"],
        longitude=recipient["longitude"],
        location=recipient["location"],
        extra=extra,
    )


@app.get("/api/map")
def map_data(
    analysis_id: str | None = Query(default=None),
    params: dict[str, Any] = Depends(match_filters),
) -> MapResponse:
    if analysis_id:
        analysis = storage.get(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
        exact_source = analysis["source"].get("latitude") is not None and analysis["source"].get("longitude") is not None
        source_node = MapNode(
            id=analysis["id"],
            name=f"{analysis['material']['name']} source",
            kind="source",
            sector=analysis["source"]["source_type"],
            latitude=analysis["source"]["latitude"],
            longitude=analysis["source"]["longitude"],
            location=analysis["source"]["location"],
            extra={
                "material": analysis["material"]["name"],
                "quantity_t_per_month": analysis["source"]["quantity_t_per_month"],
                "confidence": analysis["identification"]["confidence"],
                "frequency": analysis["source"].get("frequency"),
                "engine": analysis["identification"]["engine"],
            },
        )
        # Deliberately the same filtered, sorted result set the Matches page
        # renders - the map is a view of it, not a second implementation.
        cards, _, _ = _ranked(analysis_id, params)
        # The source is only plottable when its location resolved. Dropping the node
        # is better than drawing it on top of whichever city the analysis did not say.
        nodes: list[MapNode] = [source_node] if exact_source else []
        links: list[MapLink] = []
        for card in cards:
            nodes.append(_recipient_node(card["recipient"], card))
            if not exact_source:
                # Lines need both ends; without the source there is nothing to draw
                # between, so the routes are listed as nodes and left unlinked.
                continue
            links.append(
                MapLink(
                    id=card["id"],
                    source=analysis["id"],
                    target=card["id"].split(":", 1)[1],
                    material=card["material"],
                    match_score=card["score"],
                    distance_km=card["distance_km"],
                    quantity_t_per_month=card["matched_quantity_t_per_month"],
                    estimated_value_inr_per_month=card["estimated_value_inr_per_month"],
                    reuse_type=card["reuse_type"],
                )
            )
        return MapResponse(analysis_id=analysis_id, nodes=nodes, links=links)

    # Network view: every seeded source plus the recipients it can actually reach.
    nodes = []
    links = []
    for src in loader.get_sources():
        nodes.append(
            MapNode(
                id=src["id"],
                name=src["name"],
                kind="source",
                sector=src["sector"],
                latitude=src["latitude"],
                longitude=src["longitude"],
                location=src["location"],
                extra={"material_hint": src.get("material_hint"), "description": src.get("description", "")},
            )
        )
        material = MATERIALS_BY_ID.get(src.get("material_hint") or "", MATERIALS_BY_ID["unknown_material"])
        for r in loader.get_recipients():
            if not (material["id"] in r["accepted_materials"] or material["category"] in r["accepted_categories"]):
                continue
            # Score-based filters cannot apply here - nothing in this view has
            # been scored - but the structural ones use the same vocabulary.
            if params.get("sector") and r["sector"] != params["sector"]:
                continue
            if params.get("partner_type") and partner_type(r["sector"]) != params["partner_type"]:
                continue
            distance = haversine_km(src["latitude"], src["longitude"], r["latitude"], r["longitude"])
            if params.get("max_distance_km") is not None and distance > params["max_distance_km"]:
                continue
            node = _recipient_node(r)
            node.extra["distance_km"] = round(distance, 1)
            nodes.append(node)
            links.append(
                MapLink(
                    id=f"{src['id']}:{r['id']}",
                    source=src["id"],
                    target=r["id"],
                    material=material["name"],
                    match_score=0.0,
                    distance_km=round(distance, 1),
                    quantity_t_per_month=0.0,
                    estimated_value_inr_per_month=0.0,
                    reuse_type=r["reuse_type"],
                )
            )
    seen: set[str] = set()
    unique_nodes = []
    for n in nodes:
        if n.id not in seen:
            seen.add(n.id)
            unique_nodes.append(n)
    return MapResponse(nodes=unique_nodes, links=links)


# ---------------------------------------------------------------------------
# Assistant + upload
# ---------------------------------------------------------------------------


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    analysis = storage.get(request.analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{request.analysis_id}' not found")
    result = chat_service.answer(analysis, request.question, request.match_id)
    return result


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    # Read at most one chunk past the limit, then refuse: a 4 GB upload should not
    # become a 4 GB allocation on the way to a "no" message.
    header = file.headers.get("content-length") if file.headers else None
    if header and header.isdigit() and int(header) > file_service.MAX_BYTES + 1_000_000:
        raise HTTPException(
            status_code=413,
            detail=f"That file is larger than Symbio reads ({file_service.MAX_BYTES // (1024 * 1024)} MB).",
        )
    raw = await file.read()
    if len(raw) > file_service.MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That file is larger than Symbio reads ({file_service.MAX_BYTES // (1024 * 1024)} MB).",
        )
    result = file_service.extract(file.filename or "upload", raw)
    if result["ok"]:
        # Extraction is advisory only: the UI reviews these values before they
        # are ever sent to the analysis pipeline.
        result["fields"] = extract_service.extract_fields(result["extracted_text"])
    return UploadResponse(**result)


@app.post("/api/extract")
def extract(request: ExtractRequest) -> dict[str, Any]:
    """Read candidate fields out of free text without analysing anything.

    The same extractor the upload path runs, so a typed sentence and a dropped
    report produce the same shape, the same evidence and the same caveats.
    """
    return {**extract_service.extract_fields(request.text), "demo_data": True}


# ---------------------------------------------------------------------------
# Startup: seed the primary demo scenario
# ---------------------------------------------------------------------------


@app.on_event("startup")
def _startup() -> None:
    # Migrations first, then the seeded demo analyses: the store may be the database,
    # and seeding into a schema that does not exist yet is a startup crash nobody
    # can read.
    app.state.database = _get_database()
    persistence.startup()
    if storage.count() == 0:
        # Each seed runs through the real identification pipeline, so with a live
        # Ollama server this is genuine LLM inference - seconds per item, not the
        # near-instant deterministic fallback used when no model is running. Doing
        # that inline here would make the server (including its own Ollama health
        # probe) unresponsive for the whole duration on every restart, which looks
        # indistinguishable from Ollama not being detected at all. Seed off the
        # startup path instead; storage.save() is lock-protected, so requests that
        # land before seeding finishes just see an empty list briefly.
        threading.Thread(target=analysis_service.seed_demo_analyses, daemon=True).start()
