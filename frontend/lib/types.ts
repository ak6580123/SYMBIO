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
  distance_km: number;
  matched_quantity_t_per_month: number;
  allocated_t_per_month: number;
  required_quantity_range_t_per_month: [number, number];
  available_quantity_t_per_month: number;
  estimated_value_inr_per_month: number;
  estimated_co2e_t_per_month: number;
  reuse_pathway: { steps: string[] };
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
    latitude: number;
    longitude: number;
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
}

export interface AnalyzeResponse {
  analysis: Analysis;
  matches: Match[];
  totals: Totals;
  warnings: string[];
  demo_data: boolean;
}

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
  distance_km: number;
  reuse_type: ReuseType;
  safety_level: SafetyLevel;
  matched_quantity_t_per_month: number;
  allocated_t_per_month: number;
  required_quantity_range_t_per_month: [number, number];
  available_quantity_t_per_month: number;
  estimated_value_inr_per_month: number;
  estimated_co2e_t_per_month: number;
  breakdown: Breakdown;
  reasons: string[];
  cautions: string[];
  reuse_pathway: string[];
  source_location: string;
  source_latitude: number;
  source_longitude: number;
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
      distance_km: number;
      match_id: string;
    } | null;
    seeded: boolean;
  }[];
  top_matches: MatchCard[];
  waste_categories: { category: string; label: string; analyses: number; tonnes: number; value: number; co2e: number }[];
  sector_flow: { sector: string; label: string; tonnes: number }[];
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

export interface MapPayload {
  analysis_id: string | null;
  nodes: {
    id: string;
    name: string;
    kind: 'source' | 'recipient';
    sector: string;
    latitude: number;
    longitude: number;
    location: string;
    extra: Record<string, unknown>;
  }[];
  links: {
    id: string;
    source: string;
    target: string;
    material: string;
    match_score: number;
    distance_km: number;
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
  ollama: { available: boolean; url: string; model: string; model_present: boolean; error?: string };
}

export interface ChatResponse {
  answer: string;
  grounded_in: string[];
  engine: string;
  confident: boolean;
}

export interface UploadResponse {
  filename: string;
  extracted_text: string;
  char_count: number;
  ok: boolean;
  message: string;
  engine?: string | null;
}
