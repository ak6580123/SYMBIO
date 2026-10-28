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


def plain(value: object) -> str:
    """Render an enum - or a plain string - as the word stored in it.

    `SafetyLevel` and `ReuseType` subclass `str`, so `str(SafetyLevel.moderate)`
    is 'SafetyLevel.moderate': correct Python, useless inside a sentence shown to
    a user. Any text built from these fields goes through here.
    """
    return str(getattr(value, "value", value))


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
    # The same bound the scenario models use: a unit is a short word, and this one is
    # stored, echoed back on every card and printed in an e-mail.
    unit: str = Field(default="tonnes", max_length=20)
    # Stated by whoever describes the stream. There is deliberately no default: an
    # empty location is a validation error, never a silent substitution of another
    # city. Coordinates are optional and only used when the place itself is unknown.
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    frequency: Frequency = Field(default=Frequency.monthly)
    composition: str | None = Field(default=None, max_length=1000)
    attached_text: str | None = Field(default=None, max_length=20000)
    attached_filename: str | None = None
    # Human-in-the-loop correction: a knowledge-base material id chosen by the
    # user overrides the identification for THIS analysis only. It cannot add
    # or edit a material, because the id must already exist in the knowledge base.
    material_override_id: str | None = Field(default=None, max_length=100)

    # --- optional detail (§3) ------------------------------------------------
    # None of these are required, and none of them move a score. They buy two
    # things: a higher completeness percentage, and deterministic cross-checks
    # against each partner's recorded handling capability. Leaving them out is a
    # legitimate answer, so it is shown as one rather than punished.
    physical_state: Literal[
        "powder", "granular", "solid", "sludge", "liquid", "fiber", "mixed"
    ] | None = None
    moisture_percent: float | None = Field(default=None, ge=0, le=100)
    contaminants: list[str] = Field(default_factory=list, max_length=20)
    intended_use: str | None = Field(default=None, max_length=300)


class ListingRequest(BaseModel):
    """What POST /api/listings accepts.

    Deliberately narrow: a listing states a kind, a party, materials the knowledge
    base already knows, a quantity, a price and a range. There is no `suggested_material`
    or `summary` field for a model to fill in, because a listing is a claim about the
    world and only a person or a seeded record can make one.
    """

    kind: str
    material_ids: list[str]
    quantity_t_per_month: float
    party_id: str | None = None
    party_name: str | None = None
    party_sector: str | None = None
    location: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    offer_price_inr_per_tonne: float | None = Field(default=None, ge=0)
    asking_price_inr_per_tonne: float | None = Field(default=None, ge=0)
    max_distance_km: float | None = Field(default=None, gt=0, le=500)
    requirements: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    frequency: str | None = None
    application_use: str | None = None


class MatchFilters(BaseModel):
    analysis_id: str | None = None
    sector: str | None = None
    max_distance_km: float | None = Field(default=None, gt=0, le=2000)
    min_match_score: float = Field(default=0, ge=0, le=100)
    min_quantity: float | None = Field(default=None, ge=0)
    reuse_type: ReuseType | None = None
    processing: Literal["direct", "processing_required"] | None = None
    min_estimated_value: float | None = Field(default=None, ge=0)
    safety_level: SafetyLevel | None = None
    partner_type: Literal["industry", "sme", "recycler", "processing", "agriculture", "community"] | None = None
    sort: Literal["score", "distance", "value", "environmental", "least_processing"] = "score"


class ScenarioRequest(BaseModel):
    """A temporary 'what if' variation of a stored analysis.

    Only the four variables a source record actually carries can be changed. The
    material identity is carried over from the analysis rather than re-derived,
    so a re-ranking is attributable to what the user changed and not to a second
    guess by the model. Nothing is stored.
    """

    analysis_id: str
    quantity: float | None = Field(default=None, gt=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=20)
    frequency: Frequency | None = None
    location: str | None = Field(default=None, max_length=200)

    # §11 - what to *look at* in the re-ranked result. These filter the cards the
    # engine produced; they cannot add a route, and they run after the safety layer,
    # so a scenario can narrow a list but never widen it past a refusal.
    destination_recipient_id: str | None = Field(default=None, max_length=60)
    require_viable_transport: bool = False
    max_transport_cost_inr_per_tonne: float | None = Field(default=None, ge=0)
    processing_capability_required: str | None = Field(default=None, max_length=60)
    max_processing_burden: int | None = Field(default=None, ge=0, le=9)


class ScenarioConfig(BaseModel):
    """One configuration inside `POST /api/scenarios/compare`.

    The same variables as a single scenario, plus a label, because a comparison
    without names is a table of anonymous numbers. `analysis_id` is *not* per config:
    configurations are compared against one another, so they must start from the same
    stored analysis - comparing two different sources is not a scenario, it is two
    analyses.
    """

    label: str = Field(min_length=1, max_length=80)
    quantity: float | None = Field(default=None, gt=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=20)
    frequency: Frequency | None = None
    location: str | None = Field(default=None, max_length=200)
    destination_recipient_id: str | None = Field(default=None, max_length=60)
    require_viable_transport: bool = False
    max_transport_cost_inr_per_tonne: float | None = Field(default=None, ge=0)
    processing_capability_required: str | None = Field(default=None, max_length=60)
    max_processing_burden: int | None = Field(default=None, ge=0, le=9)


class ScenarioCompareRequest(BaseModel):
    """Two to four configurations of the same analysis, side by side."""

    analysis_id: str
    configs: list[ScenarioConfig] = Field(min_length=2, max_length=4)


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
    summary: str = ""  # plain-language justification, built from the scored values
    # None when the source location has no coordinates: no distance is invented.
    distance_km: float | None = None
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
    # Added for the knowledge-base page: what the material is also called, the
    # wording it is recognised from, and the safety rules that apply to it.
    aliases: list[str] = []
    identification_hints: list[str] = []
    gate_rules: list[str] = []
    verification: str = "demo"


# ---------------------------------------------------------------------------
# Analysis / responses
# ---------------------------------------------------------------------------


class SourceInfo(BaseModel):
    source_type: SourceSector
    location: str
    # Null when the stated place could not be placed. Distances are then not
    # calculated at all - see `location_resolved`.
    latitude: float | None = None
    longitude: float | None = None
    location_resolved: bool = True
    quantity_t_per_month: float
    unit: str
    frequency: Frequency

    # Optional detail, stored with the source so a what-if can be re-scored
    # against the same input. `database/schema.sql` mirrors these columns.
    physical_state: str | None = None
    moisture_percent: float | None = None
    contaminants: list[str] = Field(default_factory=list)
    intended_use: str | None = None


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
    # §3: how complete the input was, and what the optional fields bought.
    completeness: dict[str, Any] = Field(default_factory=dict)


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
    latitude: float | None = None
    longitude: float | None = None
    location: str
    extra: dict[str, Any] = Field(default_factory=dict)


class MapLink(BaseModel):
    id: str
    source: str
    target: str
    material: str
    match_score: float
    # None when either end of the link has no coordinates.
    distance_km: float | None = None
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
    # Field candidates read from the extracted text, each with its evidence.
    # The UI shows this and lets the user correct it before anything is analysed.
    fields: dict[str, Any] | None = None


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)

# ---------------------------------------------------------------------------
# Accounts, organisations and the persistent marketplace (production sprint)
#
# These models exist so that a signed-in action cannot carry a field that means
# something else. `verification_status` is deliberately absent: a tenant cannot
# mark itself verified, so no request body is offered that would let it try.
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    """Create a person, the organisation they administer, and a live session."""

    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)
    organization_name: str = Field(min_length=2, max_length=200)
    sector: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    sector: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=300)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)


class ProfileRequest(BaseModel):
    """The persistent organisation profile (§4).

    Lists of plain strings for what an organisation states about itself, and objects
    where a material id is involved so the knowledge base can be checked. Nothing in
    here is scored: the profile is a declaration, and the engine's inputs stay where
    they were.
    """

    sector: str | None = Field(default=None, max_length=120)
    products_produced: list[str] = Field(default_factory=list, max_length=40)
    materials_required: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    waste_streams: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    processing_capabilities: list[str] = Field(default_factory=list, max_length=40)
    certifications: list[str] = Field(default_factory=list, max_length=40)
    contact: dict[str, Any] = Field(default_factory=dict)


class FacilityRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=1000)


class MemberRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    role: str = Field(default="viewer", max_length=40)


class OrganizationSwitch(BaseModel):
    organization_id: str = Field(min_length=4, max_length=60)


class ListingPatch(BaseModel):
    """Everything a publisher may change later. `kind` and ownership are not among them."""

    quantity_t_per_month: float | None = Field(default=None, gt=0, le=1_000_000)
    price_inr_per_tonne: float | None = Field(default=None, ge=0)
    max_distance_km: float | None = Field(default=None, gt=0, le=500)
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    frequency: str | None = Field(default=None, max_length=40)
    application_use: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    material_ids: list[str] | None = Field(default=None, max_length=12)
    requirements: dict[str, Any] | None = None
    # A create form calls the same number `asking_price_inr_per_tonne` or
    # `offer_price_inr_per_tonne` depending on the kind of listing. Editing accepts those
    # names as well, so the form that published a listing can also change it; at most one
    # of the three may be sent, and all three mean the stored price.
    asking_price_inr_per_tonne: float | None = Field(default=None, ge=0)
    offer_price_inr_per_tonne: float | None = Field(default=None, ge=0)


class ListingStatusRequest(BaseModel):
    status: str = Field(min_length=6, max_length=6)
