// Shapes returned by the Symbio FastAPI backend.

export type SourceSector = 'industry' | 'household' | 'sme' | 'agriculture' | 'other';
export type Frequency = 'one_time' | 'daily' | 'weekly' | 'monthly' | 'continuous';
export type ReuseType =
  | 'DIRECT_REUSE'
  | 'REQUIRES_PROCESSING'
  | 'INDUSTRIAL_ONLY'
  | 'RESTRICTED'
  | 'UNKNOWN';
export type SafetyLevel = 'low' | 'moderate' | 'high' | 'hazardous' | 'unknown';

export interface Identification {
  material: string;
  material_id: string | null;
  confidence: number;
  category: string | null;
  properties: string[];
  composition: Record<string, string>;
  alternatives: { material: string; material_id: string; confidence: number }[];
  reuse_categories: string[];
  safety_level: SafetyLevel;
  requires_processing: boolean;
  engine: string;
  reasoning: string;
  uncertainty_note: string | null;
}

export interface MaterialRecord {
  id: string;
  name: string;
  category: string;
  description: string;
  properties: string[];
  reuse_categories: string[];
  compatible_sectors: string[];
  safety_level: SafetyLevel;
  requires_processing: boolean;
  default_reuse_type: ReuseType;
  typical_price_inr_per_tonne: number;
  co2e_avoided_t_per_tonne: number;
  notes?: string;
  /** Other names this material goes by, straight from the knowledge base. */
  aliases?: string[];
  /** Wording the identifier looks for - the knowledge base's own keyword list. */
  identification_hints?: string[];
  /** Rules the safety layer applies to this record, generated from that code. */
  gate_rules?: string[];
  /** 'demo' until a record has been checked against a real source. */
  verification?: string;
}

export interface Recipient {
  id: string;
  company_name: string;
  sector: string;
  location: string;
  latitude: number;
  longitude: number;
  accepted_materials: string[];
  accepted_categories: string[];
  min_quantity_t_per_month: number;
  max_quantity_t_per_month: number;
  processing_capability: string[];
  estimated_price_inr_per_tonne: number;
  reuse_type: ReuseType;
  safety_level: SafetyLevel;
  notes?: string;
}

export interface Breakdown {
  compatibility: number;
  quantity: number;
  location: number;
  sector: number;
  value: number;
  environmental: number;
  weighted_total: number;
}

export interface Match {
  id: string;
  analysis_id: string;
  recipient: Recipient;
  overall_score: number;
  breakdown: Breakdown;
  reuse_type: ReuseType;
  safety_level: SafetyLevel;
  reasons: string[];
  cautions: string[];
  /** Null when this analysis has no coordinates - never a distance to a substitute city. */
  distance_km: number | null;
  matched_quantity_t_per_month: number;
  allocated_t_per_month: number;
  required_quantity_range_t_per_month: [number, number];
  available_quantity_t_per_month: number;
  estimated_value_inr_per_month: number;
  estimated_co2e_t_per_month: number;
  reuse_pathway: { steps: string[] };
  /** Plain-language justification, generated with the score in the engine. */
  summary: string;
}

export interface Totals {
  available_t_per_month: number;
  allocated_t_per_month: number;
  unallocated_t_per_month: number;
  potential_matches: number;
  viable_matches: number;
  estimated_value_inr_per_month: number;
  estimated_value_inr_per_year: number;
  estimated_co2e_avoided_t_per_month: number;
  estimated_co2e_avoided_t_per_year: number;
  diversion_rate: number;
  co2e_factor_used_t_per_tonne: number;
  label: string;
}

export interface Analysis {
  id: string;
  created_at: string;
  source: {
    source_type: SourceSector;
    location: string;
    /** Null when the place that was typed is not in the gazetteer. No coordinates are
     *  invented for it, so nothing downstream may quote a distance for it either. */
    latitude: number | null;
    longitude: number | null;
    /** False says those two fields are null on purpose - see `lib/format.ts`. */
    location_resolved?: boolean;
    quantity_t_per_month: number;
    unit: string;
    frequency: Frequency;
  };
  raw_description: string;
  composition_raw: string | null;
  attached_filename: string | null;
  identification: Identification;
  material: MaterialRecord;
  matches: Match[];
  excluded: { recipient_id: string; company_name: string; sector: string; reuse_type: string; reason: string }[];
  totals: Totals;
  warnings: string[];
  seeded: boolean;
  /** §3 - the structured input fields and how complete they are. */
  physical_state?: string | null;
  moisture_percent?: number | null;
  contaminants?: string[];
  intended_use?: string | null;
  completeness?: CompletenessCard;
  contaminant_cautions_applied?: string[];
}

export interface AnalyzeResponse {
  analysis: Analysis;
  matches: Match[];
  totals: Totals;
  warnings: string[];
  /** Shipped with the analysis so the material card needs no second request. */
  intelligence?: IntelligenceCard | null;
  /** §6 - true when this run is a record on the organisation, not just this session's. */
  saved?: boolean;
  /** The human-readable reference (`SYM-2026-000184`), or null when nothing was stored. */
  reference?: string | null;
  organization_id?: string | null;
  demo_data: boolean;
}

/**
 * What kind of reuse partner a recipient is. The backend derives it from the
 * recipient's sector, so a filter on this value never disagrees with the list.
 */
export type PartnerType = 'industry' | 'sme' | 'recycler' | 'processing' | 'agriculture' | 'community';

export type MatchSort = 'score' | 'distance' | 'value' | 'environmental' | 'least_processing';

export interface MatchCard {
  id: string;
  analysis_id: string;
  material: string;
  material_id: string;
  company_name: string;
  sector: string;
  sector_label: string;
  location: string;
  latitude: number;
  longitude: number;
  score: number;
  distance_km: number | null;
  reuse_type: ReuseType;
  safety_level: SafetyLevel;
  partner_type: PartnerType;
  partner_type_label: string;
  processing_capability: string[];
  accepted_materials: string[];
  estimated_price_inr_per_tonne: number;
  /** Plain-language justification, built from the same values as the score. */
  summary: string;
  matched_quantity_t_per_month: number;
  allocated_t_per_month: number;
  required_quantity_range_t_per_month: [number, number];
  available_quantity_t_per_month: number;
  estimated_value_inr_per_month: number;
  estimated_co2e_t_per_month: number;
  /** §8 - what it costs to move this load, or null when it cannot be estimated. */
  transport?: TransportEstimate | null;
  breakdown: Breakdown;
  reasons: string[];
  cautions: string[];
  reuse_pathway: string[];
  source_location: string;
  source_latitude: number | null;
  source_longitude: number | null;
}

export interface DashboardData {
  recent_analyses: {
    id: string;
    created_at: string;
    material: string;
    material_id: string;
    category: string;
    confidence: number;
    engine: string;
    source_type: SourceSector;
    location: string;
    quantity_t_per_month: number;
    allocated_t_per_month: number;
    estimated_value_inr_per_month: number;
    estimated_co2e_t_per_month: number;
    potential_matches: number;
    top_match: {
      company_name: string;
      sector: string;
      sector_label: string;
      score: number;
      distance_km: number | null;
      match_id: string;
    } | null;
    seeded: boolean;
  }[];
  top_matches: MatchCard[];
  waste_categories: { category: string; label: string; analyses: number; tonnes: number; value: number; co2e: number }[];
  sector_flow: { sector: string; label: string; tonnes: number }[];
  /** Five-stage routes for the Sankey: source > material > processing > sector > product. */
  flow_rows: {
    source: string;
    material: string;
    processing: string;
    sector: string;
    product: string;
    tonnes: number;
  }[];
  flow_tonnes_t_per_month: number;
  flow_routes_potential: number;
  impact: {
    analyses: number;
    tonnes_analysed: number;
    tonnes_diverted: number;
    potential_matches: number;
    viable_matches: number;
    estimated_value_inr_per_month: number;
    estimated_co2e_t_per_month: number;
    diversion_rate: number;
    label: string;
  };
  demo_data: boolean;
}

export interface ImpactData {
  totals: {
    tonnes_analysed: number;
    tonnes_diverted: number;
    estimated_value_inr_per_month: number;
    estimated_value_inr_per_year: number;
    estimated_co2e_t_per_month: number;
    estimated_co2e_t_per_year: number;
    diversion_rate: number;
    analyses: number;
    reuse_partners: number;
    routes: number;
    potential_reuse_t_per_month: number;
    direct_reuse_share: number;
    mean_identification_confidence: number;
  };
  processing_pathways: { capability: string; routes: number }[];
  /** Optional, deliberately simple composite - see the note on the page. */
  circularity: {
    score: number;
    formula: string;
    components: {
      diversion_rate: number;
      direct_reuse_share: number;
      mean_identification_confidence: number;
    };
    weight_of_demo_estimate: string;
    current: { min: number; label: string; rule: string } | null;
    next: { min: number; label: string; rule: string } | null;
    bands: { min: number; label: string; rule: string }[];
    note: string;
  };
  by_sector: { sector: string; label: string; tonnes: number; value: number; co2e: number; routes: number }[];
  by_source_type: {
    source_type: string;
    label: string;
    analysed_t: number;
    diverted_t: number;
    co2e_t: number;
    analyses: number;
  }[];
  factors_used: { material: string; co2e_avoided_t_per_tonne: number; typical_price_inr_per_tonne: number }[];
  formulae: Record<string, string>;
  disclaimer: string;
  demo_data: boolean;
}

/**
 * What the backend puts on a map node. Source nodes and recipient nodes carry
 * different keys, so everything is optional; a popup renders what is present.
 */
export interface MapNodeExtra {
  material?: string;
  quantity_t_per_month?: number;
  confidence?: number;
  frequency?: string;
  engine?: string;
  description?: string;
  material_hint?: string;
  sector_label?: string;
  partner_type?: string;
  partner_type_label?: string;
  accepted_materials?: string[];
  required_quantity_range_t_per_month?: [number, number];
  processing_capability?: string[];
  safety_level?: string;
  reuse_type?: string;
  estimated_price_inr_per_tonne?: number;
  scored?: boolean;
  match_score?: number;
  distance_km?: number;
  matched_quantity_t_per_month?: number;
  estimated_value_inr_per_month?: number;
  summary?: string;
}

export interface MapPayload {
  analysis_id: string | null;
  nodes: {
    id: string;
    name: string;
    kind: 'source' | 'recipient';
    sector: string;
    latitude: number | null;
    longitude: number | null;
    location: string;
    extra: Record<string, unknown>;
  }[];
  links: {
    id: string;
    source: string;
    target: string;
    material: string;
    match_score: number;
    distance_km: number | null;
    quantity_t_per_month: number;
    estimated_value_inr_per_month: number;
    reuse_type: ReuseType;
  }[];
  demo_data: boolean;
}

export interface HealthData {
  status: string;
  demo_data: boolean;
  materials: number;
  recipients: number;
  analyses_stored: number;
  ollama: {
    available: boolean;
    /** A model Symbio can actually drive was found. Differs from `available`. */
    usable: boolean;
    url: string;
    /** The model that will be used - auto-selected when the preferred one is absent. */
    model: string;
    requested_model: string;
    auto_selected: boolean;
    model_present: boolean;
    installed_models?: string[];
    error?: string;
  };
}

export interface ChatResponse {
  answer: string;
  grounded_in: string[];
  engine: string;
  confident: boolean;
}

/**
 * One extracted field, with the text it was read from. `evidence` is what makes
 * the preview reviewable rather than a guess the user has to trust, and
 * `found: false` is how the UI knows to ask instead of assuming.
 */
export interface ExtractedField<T = string | number | null> {
  value: T;
  evidence: string | null;
  found: boolean;
  note: string | null;
}

export interface ExtractionPayload {
  quantity: ExtractedField<number>;
  unit: ExtractedField<string>;
  frequency: ExtractedField<string>;
  location: ExtractedField<string>;
  source_type: ExtractedField<string>;
  composition: ExtractedField<Record<string, string>>;
  material: ExtractedField<{ name: string; material_id: string; confidence: number } | null>;
  safety_flags: { marker: string; evidence: string }[];
  missing: string[];
  notes: string[];
  description: string;
  demo_data?: boolean;
}

export interface UploadResponse {
  filename: string;
  extracted_text: string;
  char_count: number;
  ok: boolean;
  message: string;
  engine?: string | null;
  /** Field candidates read from the text, shown for review before analysis. */
  fields?: ExtractionPayload | null;
}

/* -------------------------------------------------------------------------- */
/* Provenance, pathways, intelligence and What-If                             */
/* -------------------------------------------------------------------------- */

/** Where a value shown to the user came from. Mirrors `explain.ORIGINS`. */
export type ProvenanceOrigin = 'user' | 'knowledge_base' | 'recipient' | 'calculated' | 'estimate' | 'ai' | 'external';

export interface ProvenanceRow {
  field: string;
  value: string;
  origin: ProvenanceOrigin;
  /** The sentence behind the tag: which field, which table, which formula. */
  detail: string;
  origin_label: string;
  origin_note: string;
}

/** One reuse route: the five pathway stages plus the partner that best performs it. */
export interface PathwayRow {
  pathway: string[];
  processing: string;
  sector_label: string;
  product: string;
  match_id: string;
  partner: string;
  partner_type_label: string;
  score: number;
  distance_km: number | null;
  reuse_type: ReuseType;
  safety_level: SafetyLevel;
  processing_capability: string[];
  matched_quantity_t_per_month: number;
  estimated_value_inr_per_month: number;
  estimated_co2e_t_per_month: number;
  summary: string;
  other_partners: string[];
}

export interface PathwayResponse {
  analysis_id: string;
  material: string | null;
  material_id: string | null;
  sort: MatchSort;
  sort_label: string;
  sort_note: string | null;
  filters_applied: Record<string, string | number>;
  primary: PathwayRow | null;
  alternatives: PathwayRow[];
  pathway_count: number;
  partner_count: number;
  scored_partners: number;
  excluded_by_safety: number;
  demo_data: boolean;
}

export interface IntelligenceSection {
  title: string;
  kind: 'text' | 'list' | 'kv';
  value: string | string[] | Record<string, string>;
  origin: ProvenanceOrigin;
  origin_label: string;
  origin_note: string;
  /** Shown instead of an empty value, so a gap reads as a gap. */
  empty?: string;
}

export interface IntelligenceEvidence {
  check: string;
  passed: boolean;
  detail: string;
  origin: ProvenanceOrigin;
  origin_label: string;
}

/** Everything Symbio actually knows about the identified material. */
export interface IntelligenceCard {
  material: MaterialRecord;
  identification: {
    confidence: number;
    engine: string | null;
    reasoning: string | null;
    uncertainty_note: string | null;
    alternatives: { material: string; material_id: string; confidence: number }[];
    user_corrected: boolean;
  };
  evidence: IntelligenceEvidence[];
  sections: IntelligenceSection[];
  verification: string;
  origins: Record<string, string>;
  origin_notes: Record<string, string>;
  analysis_id?: string;
  demo_data?: boolean;
}

export interface ScenarioInput {
  analysis_id: string;
  quantity?: number | null;
  unit?: string | null;
  frequency?: Frequency | null;
  location?: string | null;
}

export interface ScenarioCard extends MatchCard {
  original_rank: number | null;
  scenario_rank: number;
  rank_change: number | null;
  is_new: boolean;
}

export interface ScenarioResponse {
  analysis_id: string;
  scenario: {
    changed: Record<string, { from: string; to: string }>;
    source: Analysis['source'];
    warnings: string[];
    completeness?: CompletenessCard;
  };
  matches: ScenarioCard[];
  count: number;
  scored_partners: number;
  totals: Totals;
  totals_change: Record<string, number>;
  original: { source: Analysis['source']; totals: Totals; top_partner: string | null };
  /** §11 rules that narrowed this list, labelled by the backend. */
  rules?: Record<string, string | number | boolean>;
  dropped_by_rule?: ScenarioDrop[];
  transport?: TransportRollup;
  sort: MatchSort;
  demo_data: boolean;
  note: string;
}

/* ---------------------------------------------------------------------------
 * Sprint 3 - completeness, transport, listings, profiles, flow, demand,
 * similarity and scenario comparison. Every shape mirrors a response built in
 * backend/services or backend/matching; nothing here is invented for the UI.
 * --------------------------------------------------------------------------- */

export type CompletenessGroup = 'identification' | 'scoring' | 'handling' | 'safety';

export interface CompletenessField {
  key: string;
  label: string;
  group: CompletenessGroup;
  weight: number;
  provided: boolean;
  value?: string | number | null;
  why: string;
  changes: string;
}

export interface CompletenessGap {
  key: string;
  label: string;
  group: CompletenessGroup;
  weight: number;
  advice: string;
  changes: string;
}

export interface CompletenessInsight {
  field: string;
  tone: 'info' | 'warn' | 'danger' | 'success';
  title: string;
  note: string;
  affects: string;
  value: string;
  affected_recipients?: string[];
}

export interface CompletenessCard {
  percent: number;
  level: string;
  fields: CompletenessField[];
  missing: CompletenessGap[];
  insights: CompletenessInsight[];
  advice: string[];
  blocks_analysis: boolean;
  note: string;
}

export interface LogisticsAssumption {
  key: string;
  value: number;
  unit: string;
  /** Why this figure and not another - printed next to it everywhere it is used. */
  why: string;
}

export interface TransportEstimate {
  estimate: boolean;
  distance_km: number;
  quantity_t_per_month: number;
  trips_per_month: number;
  load_per_trip_t: number;
  truck_capacity_t: number;
  cost_per_trip_inr: number;
  cost_breakdown: Record<string, number | string>;
  transport_cost_inr_per_month: number;
  transport_cost_inr_per_tonne: number;
  material_value_inr_per_month: number;
  net_economic_potential_inr_per_month: number;
  burden_to_value_ratio: number;
  ratio_basis: string;
  status: 'viable' | 'marginal' | 'impractical' | 'unknown';
  status_label: string;
  minimum_viable_shipment_t: number | null;
  minimum_viable_explanation: string;
  assumptions: LogisticsAssumption[];
  disclaimer: string;
  /** The external route shown alongside this estimate. It never replaces it. */
  route?: RouteInfo | null;
}

export interface TransportRollup {
  /** null when no route in the set could be priced - `label` says why. */
  transport_cost_inr_per_month: number | null;
  material_value_inr_per_month: number;
  net_economic_potential_inr_per_month: number | null;
  viable_routes: number;
  marginal_routes: number;
  impractical_routes: number;
  unknown_routes: number;
  /** Routes left out of the freight total because their location has no coordinates. */
  routes_without_freight?: number;
  easiest_viable_shipment_t: number | null;
  label: string;
}

export interface ScenarioDrop {
  match_id: string;
  company_name: string;
  rule: string;
  rule_label: string;
  value: string | number | boolean;
  reason: string;
}

export interface ScenarioConfig {
  label: string;
  quantity?: number | null;
  unit?: string | null;
  frequency?: Frequency | null;
  location?: string | null;
  destination_recipient_id?: string | null;
  require_viable_transport?: boolean;
  max_transport_cost_inr_per_tonne?: number | null;
  processing_capability_required?: string | null;
  max_processing_burden?: number | null;
}

export interface ScenarioColumn {
  label: string;
  changed: Record<string, { from: string; to: string }>;
  rules: Record<string, string | number | boolean>;
  rule_labels?: Record<string, string | number | boolean>;
  warnings: string[];
  match_count: number;
  scored_partners: number;
  dropped_by_rule: ScenarioDrop[];
  best_match: {
    match_id: string;
    company_name: string;
    sector_label: string | null;
    score: number;
    distance_km: number | null;
    estimated_value_inr_per_month: number;
    estimated_co2e_t_per_month: number;
    reuse_type: ReuseType;
    safety_level: SafetyLevel;
    matched_quantity_t_per_month: number;
    transport_status?: string;
    transport_cost_inr_per_month?: number | null;
    net_economic_potential_inr_per_month?: number | null;
    minimum_viable_shipment_t?: number | null;
    ordered_by: string;
  } | null;
  totals: Totals;
  transport: TransportRollup;
  viable_at_t_per_month: number | null;
  delta_vs_baseline?: Record<string, number | boolean>;
}

export interface ScenarioCompareResponse {
  analysis_id: string;
  configurations: ScenarioColumn[];
  baseline_label: string;
  columns: string[];
  note: string;
  demo_data: boolean;
}

export interface Listing {
  id: string;
  kind: 'demand' | 'supply';
  party_id: string;
  party_name: string;
  party_sector: string;
  /** Exactly what the author stated: null when they did not state one. */
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  location_note?: string;
  material_ids: string[];
  material_names: string[];
  quantity_t_per_month: number;
  /** Demand listings carry an intake window; a source states output, not a window. */
  quantity_window_t_per_month?: [number, number];
  max_distance_km: number;
  /** Present on a demand listing: what the buyer will pay. */
  offer_price_inr_per_tonne?: number;
  /** Present on a supply listing: what the seller is asking. */
  asking_price_inr_per_tonne?: number;
  requirements: Record<string, unknown>;
  notes: string;
  status: string;
  created_at: string;
  origin: string;
  /** Recorded on the demand side, where it decides whether a load can be taken. */
  processing_capability?: string[];
  /** What the author said about cadence and use, kept out of the score. */
  frequency?: string;
  application_use?: string;
  location_resolved?: boolean;
  location_source?: string;
  /** False for a row held in memory for this session only; true once it is saved. */
  persisted?: boolean;
  /** `active` / `paused` / `closed` for an organisation's own row. */
  lifecycle?: string;
  updated_at?: string;
  organization?: { id: string; name: string; verification_status: string };
}

/** §5/§7 as the match detail page states it: an explanation, never a number. */
export interface MatchIndustryNote {
  sector_label: string | null;
  products: string[];
  product: string;
  product_note: string;
  recorded_acceptance: boolean;
  acceptance_note: string;
  intake_note: string | null;
  certifications: string[];
  origin: string;
}

export type ListingQuery = {
  kind?: 'demand' | 'supply';
  material_id?: string;
};

export interface ListingStats {
  total: number;
  demand: number;
  supply: number;
  session_published: number;
  by_material: {
    material_id: string;
    name: string;
    demand: number;
    supply: number;
    demand_t_per_month: number;
    supply_t_per_month: number;
    /** Positive means more supply than demand in this dataset. */
    balance_t_per_month: number;
  }[];
}

export interface ListingPayload {
  listings: Listing[];
  count: number;
  stats: ListingStats;
  note: string;
  persistence_note: string;
  demo_data: boolean;
}

export interface ListingCounterparty {
  fit: number;
  fit_components: Record<string, number>;
  weights_used: Record<string, number>;
  shared_material_ids: string[];
  distance_km: number | null;
  distance_note?: string | null;
  /** null when neither listing could be placed, so no range was comparable. */
  within_stated_range: boolean | null;
  gap: Record<string, number>;
  listing: Listing;
  scored_by: string;
}

/** A row of the deterministic ranking, as the engine emits it (not a card). */
export interface ListingEngineMatch {
  id: string;
  analysis_id: string;
  material_id: string;
  overall_score: number;
  distance_km: number | null;
  reuse_type: ReuseType;
  safety_level: SafetyLevel;
  matched_quantity_t_per_month: number;
  allocated_t_per_month: number;
  estimated_value_inr_per_month: number;
  summary: string;
  reasons: string[];
  cautions: string[];
  recipient: { id: string; company_name: string; sector: string; location: string };
  transport?: TransportEstimate | null;
  scored_by: string;
}

export interface ListingMatchResponse {
  listing: Listing;
  listing_source: string;
  counterparty_count: number;
  counterparties: ListingCounterparty[];
  engine_match_count: number;
  engine_matches: ListingEngineMatch[];
  excluded_by_safety: { company_name: string; reason: string }[];
  note: string;
  demo_data: boolean;
}

/** `GET /api/logistics` - the eight constants, the bands, and an optional estimate. */
export interface LogisticsResponse {
  assumptions: { key: string; value: number; unit: string; note: string }[];
  bands: { viable_at_most: number; marginal_at_most: number; meaning: string };
  note: string;
  disclaimer?: string | null;
  estimate: TransportEstimate | null;
  inputs?: Record<string, number>;
  how_to_calculate?: string;
  demo_data: boolean;
}

export interface DemandSignal {
  material_id: string | null;
  name: string;
  category?: string;
  safety_level?: SafetyLevel;
  partners_seeking: number;
  price_range_inr_per_tonne?: [number, number];
  quantity_window_t_per_month?: [number, number];
  note?: string | null;
}

/** §5 - what a receiver's record and its sector template say about it. */
export interface IndustryProfile {
  recipient_id: string;
  company_name: string;
  sector: string;
  sector_label: string;
  location: string;
  has_sector_template: boolean;
  profile_source: string;
  products: string[];
  certifications: string[];
  intake_note: string;
  capability: {
    processing: string[];
    reuse_type: ReuseType;
    safety_level: SafetyLevel;
    summary: string;
    quantity_window_t_per_month: [number, number];
    price_inr_per_tonne: number;
  };
  /** The accepted-material list, enriched only with what the knowledge base knows. */
  materials_required: { material_id: string | null; name: string; category: string | null; note: string | null; source: string }[];
  byproducts: {
    material_id: string | null;
    name: string;
    note: string;
    source: string;
    disposition: string;
    /** Partners that could take it - the API returns the partner row, not a name. */
    potential_recipients: { company_name: string; sector: string; distance_km?: number | null }[];
    own_product_note: string;
  }[];
  demand_signals: DemandSignal[];
  chain: { step: string; label: string; items: string[]; origin: string; detail: Record<string, unknown>[] }[];
  explanation: string;
  demo_data: boolean;
}

/** One sector template from `GET /api/profiles`. */
export interface SectorProfile {
  sector: string;
  label: string;
  partners: number;
  partner_ids: string[];
  products: string[];
  materials_required: string[];
  byproducts: string[];
  listed_material_ids: string[];
  byproduct_material_ids: string[];
  certifications: string[];
  capability_summary: string;
  intake_note: string;
}

export interface SimilarMaterial {
  material_id: string;
  name: string;
  category: string;
  /** 0-100, deterministic: shared properties, reuse routes and sectors. */
  similarity: number;
  shared: { properties?: string[]; reuse_categories?: string[]; compatible_sectors?: string[] };
  shared_aspect_count: number;
  same_category: boolean;
  safety_level: SafetyLevel;
  requires_processing: boolean;
  /** The safety sentence when the neighbour is the stricter material, else null. */
  safety_delta: string | null;
  differences: string[];
  typical_price_inr_per_tonne: number;
  price_delta_inr_per_tonne: number;
  acceptance_note: string;
}

export interface SimilarityResponse {
  material: MaterialRecord;
  results: SimilarMaterial[];
  least_similar: SimilarMaterial[];
  knowledge_base_size: number;
  score_note: string;
  demo_data: boolean;
}

export interface FlowStage {
  stage: string;
  tonnes_per_month: number;
  apparent_tonnes_per_month: number;
  capped_by_previous_stage: boolean;
  share_of_generated: number;
  definition: string;
  caveat?: string | null;
}

export interface FlowRoute {
  source: string;
  source_sector: string;
  material: string;
  processor: string;
  recipient: string;
  recipient_id: string;
  sector: string;
  product: string;
  tonnes_per_month: number;
  matched_tonnes_per_month: number;
  value_inr_per_month: number;
  co2e_t_per_month: number;
  /** 'unavailable' when the stream's location has no coordinates to price a haul from. */
  transport_status: string;
  transport_cost_inr_per_month: number | null;
  net_economic_potential_inr_per_month: number | null;
  distance_km: number;
  analysis_id: string;
  match_id: string;
}

export interface MaterialFlowResponse {
  stages: FlowStage[];
  drops?: { from: string; to: string; lost_tonnes_per_month: number }[];
  biggest_loss?: { from: string; to: string; lost_tonnes_per_month: number } | null;
  recovery_percent?: number;
  reused_percent?: number;
  reused_equals_processed?: boolean;
  reused_note?: string;
  routes: FlowRoute[];
  route_count?: number;
  partner_count?: number;
  material_count?: number;
  analyses?: number;
  blocked_streams?: { analysis_id: string; material: string; tonnes_per_month: number; reason: string }[];
  partner_appetite_t_per_month?: number;
  partner_appetite_note?: string;
  generated_note?: string;
  caveats?: string[];
  impact_dashboard?: Record<string, unknown>;
  note?: string;
  demo_data: boolean;
}

export interface DemandArea {
  area: string;
  latitude: number;
  longitude: number;
  demand_potential_index: number;
  band: 'High' | 'Medium' | 'Low';
  components: Record<string, number>;
  component_weights: Record<string, number>;
  partners: {
    id: string;
    company_name: string;
    sector: string;
    window_t_per_month: [number, number];
    allocated_t_per_month: number;
    headroom_t_per_month: number;
    price_inr_per_tonne: number;
  }[];
  partner_count: number;
  sector_count: number;
  intake_headroom_t_per_month: number;
  currently_allocated_t_per_month: number;
  open_demand_listings: number;
  open_demand_tonnes_per_month: number;
  nearby_unplaced_supply_t_per_month: number;
  top_materials: { material_id: string; name: string; headroom_t_per_month: number }[];
  drivers: string[];
}

export interface DemandResponse {
  areas: DemandArea[];
  count: number;
  radius_km: number;
  supply_scan_km?: number;
  method: string;
  caveat: string;
  not_a_forecast: string;
  material_id?: string;
  material_name?: string;
  error?: string;
  demo_data: boolean;
}


/* --------------------------------------------------------------------------
   Accounts, organisations and the tenant's own records.
   -------------------------------------------------------------------------- */

export type OrganizationRole = 'organization_admin' | 'operator' | 'viewer';

export interface SessionUser {
  id: string;
  email: string;
  display_name: string;
}

export interface SessionOrganization {
  id: string;
  name: string;
  sector: string;
  verification_status: string;
  verification_note: string;
}

export interface SessionMembership {
  id: string;
  name: string;
  role: OrganizationRole;
}

/** What `/api/auth/me` answers for a signed-in person. */
export interface Session {
  signed_in: boolean;
  user: SessionUser;
  organization: SessionOrganization;
  role: OrganizationRole;
  role_label: string;
  can_write: boolean;
  can_manage_members: boolean;
  organizations: SessionMembership[];
}

/** What the database behind this deployment actually is, in the API's own words. */
export interface PersistenceState {
  configured: boolean;
  mode: string;
  target: string;
  reachable: boolean;
  migrations_applied: number;
  note: string;
  configuration_note?: string;
}

export interface AuthStatus {
  signed_in: boolean;
  session?: Session;
  persistence: PersistenceState;
  geography?: { geocoding: string; routing: string; label: string };
  note?: string;
}

export interface MaterialLine {
  material_id: string;
  name?: string;
  quantity_t_per_month?: number;
  moisture_percent?: number;
  frequency?: string;
  location?: string;
  note?: string;
}

/** The §4 declaration an organisation makes about itself. */
export interface OrganizationProfile {
  sector: string;
  products_produced: string[];
  materials_required: MaterialLine[];
  waste_streams: MaterialLine[];
  processing_capabilities: string[];
  certifications: string[];
  contact: Record<string, string>;
  updated_at?: string;
}

export interface OrganizationFacility {
  id: string;
  name: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  location_resolved: boolean;
  location_source: string;
  notes: string;
}

export interface OrganizationMember {
  user_id: string;
  email: string;
  display_name?: string;
  role: OrganizationRole;
  role_label: string;
  since?: string;
}

export interface OrganizationBundle {
  organization: {
    id: string;
    name: string;
    sector: string;
    description: string;
    website: string;
    contact: { name: string; email: string; phone: string };
    verification: { status: string; note: string; meaning: string };
    created_at: string;
  };
  profile: OrganizationProfile;
  facilities: OrganizationFacility[];
  members: OrganizationMember[];
  counts: { listings: number; analyses: number; facilities: number };
  you: { role: OrganizationRole; role_label: string; can_write: boolean };
  persistence: PersistenceState;
  saved?: boolean;
}

/** One row of Analysis History (§6). Opening it shows the stored run, not a fresh one. */
export interface HistoryRow {
  id: string;
  reference: string;
  material: string;
  quantity_t_per_month: number;
  quantity_unit: string;
  location: string;
  location_resolved: boolean;
  location_source: string;
  match_count: number;
  best_match: string;
  best_match_score: number | null;
  created_at: string;
  created_on: string;
}

export interface HistoryResponse {
  analyses: HistoryRow[];
  count: number;
  persistence: PersistenceState;
  note?: string | null;
}

/** The external route, kept beside the engine's straight line rather than inside it. */
export interface RouteInfo {
  distance_km: number;
  duration_minutes: number | null;
  straight_line_km: number | null;
  difference_percent: number | null;
  fetched_at: string | null;
  source: string;
  note: string;
}

export interface MyListingsResponse {
  listings: Listing[];
  count: number;
  statuses: string[];
  persistence: PersistenceState;
}

/** What the marketplace's edit form may change about a listing it owns. */
export interface ListingPatch {
  quantity_t_per_month?: number;
  price_inr_per_tonne?: number;
  max_distance_km?: number;
  location?: string;
  frequency?: string;
  application_use?: string;
  notes?: string;
  material_ids?: string[];
}

/** `GET /api/status` - what this deployment has wired up, in its own words. */
export interface ServiceStatus {
  service: string;
  version: string;
  storage: {
    configured: boolean;
    mode: string;
    target: string;
    reachable: boolean;
    migrations_applied: number;
    note?: string;
  };
  authentication: { mode: string; note: string };
  geography: {
    geocoding: { provider: string; label: string; state: string };
    routing: { provider: string; label: string; state: string };
    cache_hours: number;
    note: string;
  };
  data: {
    seeded: { materials: number; recipients: number; sources: number; listings: number };
    persistent: { listings: number; analyses?: number; members?: number; organizations?: number };
    session: { analyses: number; listings: number };
  };
  limits: { upload_bytes: number; upload_kinds: string[]; rate_limiting: boolean };
}

/** `GET /api/status` also answers for the health chip; this is the subset it reads. */
export interface StatusLine {
  label: string;
  value: string;
  tone: 'good' | 'warn' | 'off';
  hint: string;
}
