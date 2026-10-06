"""Pydantic models shared by the API, the matching engine and the AI layer."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceSector(str, Enum):
    industry = "industry"
    household = "household"
    sme = "sme"
    agriculture = "agriculture"
    other = "other"


class Frequency(str, Enum):
    one_time = "one_time"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    continuous = "continuous"


class ReuseType(str, Enum):
    DIRECT_REUSE = "DIRECT_REUSE"
    REQUIRES_PROCESSING = "REQUIRES_PROCESSING"
    INDUSTRIAL_ONLY = "INDUSTRIAL_ONLY"
    RESTRICTED = "RESTRICTED"
    UNKNOWN = "UNKNOWN"


class SafetyLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    hazardous = "hazardous"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """What the Analyze Waste form sends."""

    source_type: SourceSector = Field(default=SourceSector.industry)
    material_description: str = Field(min_length=1, max_length=4000)
    quantity: float = Field(default=1.0, gt=0, le=1_000_000)
    unit: str = Field(default="tonnes")
    location: str = Field(default="Chennai, Tamil Nadu", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    frequency: Frequency = Field(default=Frequency.monthly)
    composition: str | None = Field(default=None, max_length=1000)
    attached_text: str | None = Field(default=None, max_length=20000)
    attached_filename: str | None = None


class MatchFilters(BaseModel):
    analysis_id: str | None = None
    sector: str | None = None
    max_distance_km: float | None = Field(default=None, gt=0, le=2000)
    min_match_score: float = Field(default=0, ge=0, le=100)
    min_quantity: float | None = Field(default=None, ge=0)
    reuse_type: ReuseType | None = None
    processing: Literal["direct", "processing_required"] | None = None
    min_estimated_value: float | None = Field(default=None, ge=0)


class ChatRequest(BaseModel):
    analysis_id: str
    question: str = Field(min_length=1, max_length=1000)
    match_id: str | None = None


# ---------------------------------------------------------------------------
# AI / material identification
# ---------------------------------------------------------------------------


class MaterialIdentification(BaseModel):
    """Structured output of the identification stage.

    Produced either by the LLM (validated + constrained against the KB) or by
    the deterministic fallback classifier. It never carries invented facts:
    `properties`, `reuse_categories` and `safety_level` are re-read from the
    knowledge base in the service layer.
    """

    material: str
    material_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    category: str | None = None
    properties: list[str] = Field(default_factory=list)
    composition: dict[str, str] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    reuse_categories: list[str] = Field(default_factory=list)
    safety_level: SafetyLevel = SafetyLevel.unknown
    requires_processing: bool = True
    engine: str = "unknown"
    reasoning: str = ""
    uncertainty_note: str | None = None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    compatibility: float
    quantity: float
    location: float
    sector: float
    value: float
    environmental: float
    weighted_total: float


class EstimatedImpact(BaseModel):
    """All figures here are DEMO calculations, not certified values."""

    quantity_t_per_month: float
    quantity_share_of_source: float
    estimated_value_inr_per_month: float
    estimated_co2e_avoided_t_per_month: float
    estimated_co2e_avoided_t_per_year: float


class ReusePathway(BaseModel):
    steps: list[str]


class Recipient(BaseModel):
    id: str
    company_name: str
    sector: str
    location: str
    latitude: float
    longitude: float
    accepted_materials: list[str]
    accepted_categories: list[str] = Field(default_factory=list)
    min_quantity_t_per_month: float
    max_quantity_t_per_month: float
    processing_capability: list[str]
    estimated_price_inr_per_tonne: float
    reuse_type: ReuseType
    safety_level: SafetyLevel
    notes: str = ""


class Match(BaseModel):
    id: str
    analysis_id: str
    recipient: Recipient
    overall_score: float
    breakdown: ScoreBreakdown
    reuse_type: ReuseType
    safety_level: SafetyLevel
    reasons: list[str]
    cautions: list[str] = Field(default_factory=list)
    distance_km: float
    matched_quantity_t_per_month: float
    allocated_t_per_month: float = 0.0
    required_quantity_range_t_per_month: list[float]
    available_quantity_t_per_month: float
    estimated_value_inr_per_month: float
    estimated_co2e_t_per_month: float
    reuse_pathway: ReusePathway
    demo_data: bool = True


class MaterialRecord(BaseModel):
    id: str
    name: str
    category: str
    description: str
    properties: list[str]
    reuse_categories: list[str]
    compatible_sectors: list[str]
    safety_level: SafetyLevel
    requires_processing: bool
    default_reuse_type: ReuseType
    typical_price_inr_per_tonne: float
    co2e_avoided_t_per_tonne: float
    notes: str = ""


# ---------------------------------------------------------------------------
# Analysis / responses
# ---------------------------------------------------------------------------


class SourceInfo(BaseModel):
    source_type: SourceSector
    location: str
    latitude: float
    longitude: float
    quantity_t_per_month: float
    unit: str
    frequency: Frequency


class Analysis(BaseModel):
    id: str
    created_at: datetime
    source: SourceInfo
    raw_description: str
    composition_raw: str | None = None
    attached_filename: str | None = None
    identification: MaterialIdentification
    material: MaterialRecord
    matches: list[Match] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    analysis: Analysis
    matches: list[Match]
    totals: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    demo_data: bool = True


class MapNode(BaseModel):
    id: str
    name: str
    kind: Literal["source", "recipient"]
    sector: str
    latitude: float
    longitude: float
    location: str
    extra: dict[str, Any] = Field(default_factory=dict)


class MapLink(BaseModel):
    id: str
    source: str
    target: str
    material: str
    match_score: float
    distance_km: float
    quantity_t_per_month: float
    estimated_value_inr_per_month: float
    reuse_type: ReuseType


class MapResponse(BaseModel):
    analysis_id: str | None = None
    nodes: list[MapNode]
    links: list[MapLink]
    demo_data: bool = True


class FlowStage(BaseModel):
    label: str
    value: float
    children: list[FlowStage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    grounded_in: list[str] = Field(default_factory=list)
    engine: str
    confident: bool = True


class UploadResponse(BaseModel):
    filename: str
    extracted_text: str
    char_count: int
    ok: bool
    message: str
    engine: str | None = None  # which PDF engine ran; null for txt/docx
