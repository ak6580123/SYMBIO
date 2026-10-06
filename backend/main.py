"""Symbio API - FastAPI application entry point.

Run from the backend directory:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from ai.identification import ollama_status
from knowledge_base import loader
from knowledge_base.materials import MATERIALS, MATERIALS_BY_ID
from matching.engine import SECTOR_LABELS, haversine_km
from models.schemas import AnalyzeRequest, ChatRequest, MapLink, MapNode, MapResponse, UploadResponse
from services import analysis as analysis_service
from services import chat as chat_service
from services import dashboard as dashboard_service
from services import files as file_service
from services import storage

app = FastAPI(
    title="Symbio API",
    version="0.1.0",
    description=(
        "Circular-economy waste matchmaking. The LLM only identifies materials; all match scores come "
        "from a deterministic engine over a knowledge base. All prices and emission factors are demo values."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo-only; tighten for any real deployment
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return JSONResponse(
        status_code=500,
        content={"detail": f"Unexpected server error: {exc.__class__.__name__}", "path": str(request.url.path)},
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
    return {
        "status": "ok",
        "demo_data": True,
        "materials": len(MATERIALS),
        "recipients": len(loader.get_recipients()),
        "analyses_stored": storage.count(),
        "ollama": ollama_status(),
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        analysis = analysis_service.build_analysis(request.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Seed data missing: {exc}") from exc
    return {
        "analysis": analysis,
        "matches": analysis["matches"],
        "totals": analysis["totals"],
        "warnings": analysis["warnings"],
        "demo_data": True,
    }


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


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


def _apply_filters(analysis: dict, params: dict[str, Any]) -> list[dict]:
    out = []
    for m in analysis["matches"]:
        if params.get("sector") and m["recipient"]["sector"] != params["sector"]:
            continue
        if params.get("max_distance_km") is not None and m["distance_km"] > params["max_distance_km"]:
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
        out.append(m)
    return out


def _cards(matches: list[dict], analyses: dict[str, dict]) -> list[dict]:
    cards = []
    for m in matches:
        analysis = analyses[m["analysis_id"]]
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
            }
        )
    return sorted(cards, key=lambda c: -c["score"])


@app.post("/api/matches")
def matches(
    analysis_id: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    max_distance_km: float | None = Query(default=None, gt=0, le=2000),
    min_match_score: float = Query(default=0, ge=0, le=100),
    min_quantity: float | None = Query(default=None, ge=0),
    reuse_type: str | None = Query(default=None),
    processing: str | None = Query(default=None, pattern="^(direct|processing_required)$"),
    min_estimated_value: float | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    params = {
        "sector": sector,
        "max_distance_km": max_distance_km,
        "min_match_score": min_match_score,
        "min_quantity": min_quantity,
        "reuse_type": reuse_type,
        "processing": processing,
        "min_estimated_value": min_estimated_value,
    }

    if analysis_id:
        analysis = storage.get(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
        analyses = {analysis["id"]: analysis}
        filtered = _apply_filters(analysis, params)
        source_count = len(analysis["matches"])
    else:
        stored = storage.all_newest_first()
        if not stored:
            raise HTTPException(status_code=404, detail="No analyses yet - run POST /api/analyze first")
        analyses = {a["id"]: a for a in stored}
        filtered = [m for a in stored for m in _apply_filters(a, params)]
        source_count = sum(len(a["matches"]) for a in stored)

    return {
        "analysis_id": analysis_id,
        "matches": _cards(filtered, analyses),
        "count": len(filtered),
        "filtered_from": source_count,
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
    return {
        "match": match,
        "analysis": {
            "id": analysis["id"],
            "source": analysis["source"],
            "material": analysis["material"],
            "identification": analysis["identification"],
            "totals": analysis["totals"],
        },
        "weights_used": {
            "compatibility": 0.30,
            "quantity": 0.20,
            "location": 0.15,
            "sector": 0.15,
            "value": 0.10,
            "environmental": 0.10,
        },
        "demo_data": True,
    }


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------


@app.get("/api/materials")
def materials() -> dict[str, Any]:
    return {
        "materials": [
            {k: v for k, v in m.items() if k not in {"keywords", "aliases"}} for m in MATERIALS
        ],
        "count": len(MATERIALS),
        "note": "Prices and CO2e factors are demo values stored in the knowledge base.",
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
# Dashboard / impact
# ---------------------------------------------------------------------------


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    return dashboard_service.dashboard()


@app.get("/api/impact")
def impact() -> dict[str, Any]:
    return dashboard_service.impact_summary()


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------


@app.get("/api/map")
def map_data(analysis_id: str | None = Query(default=None)) -> MapResponse:
    if analysis_id:
        analysis = storage.get(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
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
            },
        )
        nodes: list[MapNode] = [source_node]
        links: list[MapLink] = []
        for m in analysis["matches"][:15]:
            r = m["recipient"]
            nodes.append(
                MapNode(
                    id=r["id"],
                    name=r["company_name"],
                    kind="recipient",
                    sector=r["sector"],
                    latitude=r["latitude"],
                    longitude=r["longitude"],
                    location=r["location"],
                    extra={
                        "sector_label": SECTOR_LABELS.get(r["sector"], r["sector"]),
                        "match_score": m["overall_score"],
                        "reuse_type": m["reuse_type"],
                    },
                )
            )
            links.append(
                MapLink(
                    id=m["id"],
                    source=analysis["id"],
                    target=r["id"],
                    material=analysis["material"]["name"],
                    match_score=m["overall_score"],
                    distance_km=m["distance_km"],
                    quantity_t_per_month=m["matched_quantity_t_per_month"],
                    estimated_value_inr_per_month=m["estimated_value_inr_per_month"],
                    reuse_type=m["reuse_type"],
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
            if material["id"] in r["accepted_materials"] or material["category"] in r["accepted_categories"]:
                nodes.append(
                    MapNode(
                        id=r["id"],
                        name=r["company_name"],
                        kind="recipient",
                        sector=r["sector"],
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        location=r["location"],
                        extra={"sector_label": SECTOR_LABELS.get(r["sector"], r["sector"])},
                    )
                )
                links.append(
                    MapLink(
                        id=f"{src['id']}:{r['id']}",
                        source=src["id"],
                        target=r["id"],
                        material=material["name"],
                        match_score=0.0,
                        distance_km=haversine_km(src["latitude"], src["longitude"], r["latitude"], r["longitude"]),
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
    raw = await file.read()
    return UploadResponse(**file_service.extract(file.filename or "upload", raw))


# ---------------------------------------------------------------------------
# Startup: seed the primary demo scenario
# ---------------------------------------------------------------------------


@app.on_event("startup")
def _startup() -> None:
    if storage.count() == 0:
        analysis_service.seed_demo_analyses()
