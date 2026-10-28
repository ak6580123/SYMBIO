// Thin client for the Symbio API.
//
// Requests go to /api/* on the Next server, which rewrites them to FastAPI
// (see next.config.mjs). Nothing here ever holds a secret or a backend host.

import { readerCopy, titleCase } from './format';

import type {
  Analysis,
  AnalyzeResponse,
  AuthStatus,
  ChatResponse,
  CompletenessCard,
  DashboardData,
  DemandResponse,
  ExtractionPayload,
  HealthData,
  HistoryResponse,
  ImpactData,
  IndustryProfile,
  IntelligenceCard,
  Listing,
  ListingMatchResponse,
  ListingPatch,
  ListingQuery,
  ListingStats,
  LogisticsResponse,
  MapPayload,
  Match,
  MatchCard,
  MatchIndustryNote,
  MatchSort,
  MaterialFlowResponse,
  MaterialRecord,
  MyListingsResponse,
  OrganizationBundle,
  OrganizationProfile,
  OrganizationRole,
  PathwayResponse,
  PersistenceState,
  ProvenanceRow,
  Recipient,
  RouteInfo,
  ScenarioCompareResponse,
  ScenarioConfig,
  ScenarioInput,
  ScenarioResponse,
  SectorProfile,
  ServiceStatus,
  SimilarityResponse,
  TransportEstimate,
  UploadResponse,
} from './types';

export class ApiError extends Error {
  status: number;
  /** Field-level messages for a form, keyed by field name. */
  fieldErrors?: Record<string, string>;
  constructor(status: number, message: string, fieldErrors?: Record<string, string>) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

/**
 * A failure the reader can act on. Status codes, endpoints, response bodies and
 * stack traces stay in the console, where a developer looks; a screen gets one
 * sentence about what did not work and, usually, a retry.
 */
function readableFailure(status: number, raw: string): { message: string; fields?: Record<string, string> } {
  if (status === 0) {
    return { message: 'Symbio cannot reach its analysis service right now. Nothing was lost - try again.' };
  }
  if (status === 404) {
    return { message: 'That record is not available any more. It may belong to an analysis that has since been cleared.' };
  }
  if (status === 422) {
    // FastAPI answers a rejected body with a list of machine locations. Turn each
    // into `Field: what to do`, and never show the raw array.
    const fields: Record<string, string> = {};
    try {
      const parsed = JSON.parse(raw);
      const items = Array.isArray(parsed?.detail) ? parsed.detail : [];
      for (const item of items) {
        const loc = Array.isArray(item?.loc) ? item.loc.filter((part: unknown) => part !== 'body') : [];
        const field = String(loc[loc.length - 1] ?? 'value');
        const message = typeof item?.msg === 'string' ? item.msg.replace(/^Value verified/, 'This value').replace(/^[\w.]+:\s*/, '') : 'check this value';
        fields[field] = `${titleCase(field.replace(/_/g, ' '))}: ${message}`;
      }
    } catch {
      /* the body was not the validation document we expect; the generic line stands */
    }
    const keys = Object.keys(fields);
    return {
      message: keys.length
        ? `This was not accepted. ${keys.length === 1 ? fields[keys[0]] : 'Check the highlighted fields.'}`
        : 'This was not accepted. Check the values and send it again.',
      fields: keys.length ? fields : undefined,
    };
  }
  if (status >= 500) {
    return { message: 'The analysis service stopped before it finished. Long analyses can take a minute on CPU - try again.' };
  }
  return { message: 'Something went wrong while loading this. Try again.' };
}

// In the browser we call the same origin and let Next rewrite /api/* to FastAPI
// (no CORS, no host baked into client code). In a server component there is no
// origin, so fetch needs an absolute URL - built from BACKEND_URL.
function url(path: string): string {
  if (typeof window !== 'undefined') return path;
  const base = (process.env.BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');
  return `${base}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url(path), { ...init, cache: 'no-store' });
  } catch {
    console.warn('[symbio] request failed', path);
    throw new ApiError(0, 'Symbio cannot reach its analysis service right now. Nothing was lost - try again.');
  }

  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    // The status and the upstream message go to the console; the reader gets the
    // sentence in `readableFailure`.
    console.warn(`[symbio] ${res.status} ${path}`, detail);
    const { message, fields } = readableFailure(res.status, detail);
    throw new ApiError(res.status, message, fields);
  }
  return normaliseText((await res.json()) as unknown) as T;
}

/**
 * Product copy at the boundary.
 *
 * The backend and its tests keep speaking in machine provenance - `verification:
 * "demo"`, notes that name the file a value came from - which is right for an API
 * and wrong for a screen. Rewriting once, on the way in, means no component has to
 * remember to; every sentence a screen prints has already been put in product
 * language. Caveats survive: what is removed is the vocabulary, not the honesty.
 */
function normaliseText(value: unknown): unknown {
  if (typeof value === 'string') return readerCopy(value);
  if (Array.isArray(value)) return value.map(normaliseText);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) out[key] = normaliseText(item);
    return out;
  }
  return value;
}

function query(params: Record<string, unknown>): string {
  // Widened to `unknown` on purpose: a typed filter object (ListingQuery, MatchQuery)
  // has no index signature, and re-declaring one per call site is how a UI ends up
  // sending a parameter the backend never reads.
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export interface AnalyzeInput {
  source_type: string;
  material_description: string;
  quantity: number;
  unit: string;
  location: string;
  frequency: string;
  composition?: string | null;
  /** Stated condition of the stream, when the generator knows it. Scored by §3. */
  physical_state?: string | null;
  /** Moisture percentage, when it has been measured. Scored by §3. */
  moisture_percent?: number | null;
  /** Known contaminants, as stated by the generator. Scored by §3. */
  contaminants?: string[];
  /** What the generator hopes the material will be used for. Scored by §3. */
  intended_use?: string | null;
  attached_text?: string | null;
  attached_filename?: string | null;
  /**
   * A knowledge-base material id chosen by the user, which overrides what the
   * model read for this analysis only. Set it by re-running the analysis with the
   * same input plus this field - nothing else in the system changes.
   */
  material_override_id?: string | null;
}

/**
 * Filters and sort shared by the matches list and the map.
 *
 * One type on purpose: `/api/map` accepts exactly these parameters, so a
 * filtered map and a filtered list cannot quietly mean different things.
 */
export type MatchQuery = {
  analysis_id?: string;
  sector?: string;
  max_distance_km?: number;
  min_match_score?: number;
  min_quantity?: number;
  reuse_type?: string;
  processing?: string;
  min_estimated_value?: number;
  safety_level?: string;
  partner_type?: string;
  sort?: MatchSort;
}

export const api = {
  health: () => request<HealthData>('/api/health'),

  /** §13 - what is real here: storage, authentication, geography, data counts. */
  status: () => request<ServiceStatus>('/api/status'),

  analyze: (input: AnalyzeInput) =>
    request<AnalyzeResponse>('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),

  analysis: (id: string) => request<Analysis>(`/api/analyses/${id}`),

  analyses: () => request<{ analyses: { id: string; material: string; matches: number }[] }>('/api/analyses'),

  matches: (filters: MatchQuery) =>
    request<{
      matches: MatchCard[];
      count: number;
      filtered_from: number;
      sort: MatchSort;
      sort_label: string;
      /** Present when the mode cannot change the order, and says why. */
      sort_note: string | null;
    }>(`/api/matches${query(filters)}`, { method: 'POST' }),

  /**
   * Pathways for one analysis: the ranked matches collapsed into the distinct
   * routes they represent. Same filters and same sort mode as `matches`, so the
   * primary pathway is the one the chosen optimisation actually prefers.
   */
  pathways: (filters: MatchQuery) => request<PathwayResponse>(`/api/pathways${query(filters)}`),

  /** What the knowledge base actually holds about the identified material. */
  intelligence: (analysisId: string) =>
    request<IntelligenceCard>(`/api/intelligence${query({ analysis_id: analysisId })}`),

  /**
   * A temporary re-run with different quantity, cadence or place. Nothing is
   * stored on the server, so "reset" means dropping this response.
   */
  scenario: (input: ScenarioInput, filters: Omit<MatchQuery, 'analysis_id'> = {}) =>
    request<ScenarioResponse>(`/api/scenario${query(filters)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),

  /**
   * Read candidate fields out of free text without running an analysis. The
   * caller shows these for editing first - they are never fed into the pipeline
   * behind the user's back.
   */
  extract: (text: string) =>
    request<ExtractionPayload>('/api/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),

  matchDetail: (analysisId: string, recipientId: string) =>
    request<{
      match: Match;
      analysis: Pick<Analysis, 'id' | 'source' | 'material' | 'identification' | 'totals'>;
      weights_used: Record<string, number>;
      provenance: ProvenanceRow[];
      /** §8 - attached to the card, never folded into the score. */
      transport: TransportEstimate | null;
      /** The external route for this pair, or null when nothing could be routed. */
      route?: RouteInfo | null;
      /** §5 / §7 - null when the recipient has no record to build a profile from. */
      industry_profile: MatchIndustryNote | null;
      demo_data: boolean;
    }>(`/api/matches/${analysisId}/${recipientId}`),

  materials: () =>
    request<{
      materials: MaterialRecord[];
      count: number;
      note?: string;
      verification_note?: string;
      demo_data?: boolean;
    }>('/api/materials'),

  recipients: (sector?: string) =>
    request<{ recipients: Recipient[]; count: number; sectors: { sector: string; label: string }[] }>(
      `/api/recipients${query({ sector })}`,
    ),

  dashboard: () => request<DashboardData>('/api/dashboard'),

  impact: () => request<ImpactData>('/api/impact'),

  /**
   * Map data. Takes the same filters as `matches` because it is a view of that
   * same result set - the backend shares one filter/sort path for both.
   */
  map: (analysisId?: string, filters: Omit<MatchQuery, 'analysis_id'> = {}) =>
    request<MapPayload>(`/api/map${query({ ...filters, analysis_id: analysisId })}`),

  chat: (analysisId: string, question: string, matchId?: string) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: analysisId, question, match_id: matchId }),
    }),

  /* --- Sprint 3 -------------------------------------------------------------
   * Each of these reads a response the backend already builds. No method here
   * assembles a number, so the UI can never show a figure the engine did not
   * compute - including the marketplace, which is a view over the same matches.
   * -------------------------------------------------------------------------- */

  /** §3 - how complete one analysis's input is, with advice per missing field. */
  completeness: (analysisId: string) =>
    request<CompletenessCard>(`/api/analyses/${analysisId}/completeness`),

  /** §12 - materials the knowledge base says are similar, never a safety verdict. */
  similarMaterials: (materialId: string, limit?: number) =>
    request<SimilarityResponse>(`/api/materials/${materialId}/similar${query({ limit })}`),

  /** §5 - a partner's structured profile, or the §16 sector template. */
  profile: (id: string) => request<IndustryProfile | SectorProfile>(`/api/profiles/${id}`),

  sectorProfiles: () =>
    request<import('../components/SectorProfiles').SectorProfilePayload>('/api/profiles'),

  /** The seeded source records a supply listing is allowed to name. */
  sources: () =>
    request<{
      sources: { id: string; name: string; sector: string; location: string; material_hint: string }[];
      count: number;
      note: string;
      demo_data: boolean;
    }>('/api/sources'),

  /** §8 - the freight constants and a one-off calculation. */
  logistics: (params: { distance_km?: number; quantity_t_per_month?: number; value_inr_per_tonne?: number }) =>
    request<LogisticsResponse & { estimate?: TransportEstimate }>(`/api/logistics${query(params)}`),

  /** §6 - the marketplace. Read filters, then a validated publish, then a match. */
  listings: (filters: ListingQuery = {}) =>
    request<{
      listings: Listing[];
      count: number;
      stats: ListingStats;
      note: string;
      persistence_note: string;
      demo_data: boolean;
    }>(`/api/listings${query(filters)}`),

  listing: (id: string) => request<{ listing: Listing; as_row: Record<string, unknown> }>(`/api/listings/${id}`),

  publishListing: (body: Record<string, unknown>) =>
    request<{ listing: Listing; persisted: boolean; origin: string }>('/api/listings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  matchListing: (body: Record<string, unknown>) =>
    request<ListingMatchResponse>('/api/listings/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /** §9 - the material flow funnel over the stored analyses. */
  materialFlow: (analysisId?: string) => request<MaterialFlowResponse>(`/api/material-flow${query({ analysis_id: analysisId })}`),

  /** §10 - regional demand potential. Capacity, not prediction. */
  demand: (params: { material_id?: string; limit?: number } = {}) =>
    request<DemandResponse>(`/api/demand${query(params)}`),

  /** §11 - two to four configurations of one analysis, side by side. */
  compareScenarios: (analysisId: string, configs: ScenarioConfig[]) =>
    request<ScenarioCompareResponse>('/api/scenarios/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: analysisId, configs }),
    }),

  upload: async (file: File): Promise<UploadResponse> => {
    const form = new FormData();
    form.append('file', file);
    return request<UploadResponse>('/api/upload', { method: 'POST', body: form });
  },

  /* ---------------------------------------------------------------- accounts
     The session is a cookie the browser holds; nothing here stores a token. */

  /** What the app asks on load. A signed-out answer is a 200, not an error. */
  session: () => request<AuthStatus>('/api/auth/me'),

  signUp: (body: {
    email: string;
    password: string;
    display_name?: string;
    organization_name: string;
    sector?: string;
    location?: string;
  }) => request<{ session: AuthStatus['session']; persistence: PersistenceState; note: string }>('/api/auth/signup', post(body)),

  signIn: (email: string, password: string) =>
    request<{ session: AuthStatus['session']; persistence: PersistenceState }>('/api/auth/login', post({ email, password })),

  signOut: () => request<{ signed_in: boolean; note: string }>('/api/auth/logout', post({})),

  organizations: () =>
    request<{ organizations: { id: string; name: string; role: OrganizationRole; sector: string }[]; active: string }>(
      '/api/auth/organizations'
    ),

  selectOrganization: (organizationId: string) =>
    request<{ session: AuthStatus['session']; changed: boolean; note?: string }>(
      '/api/auth/organizations/select',
      post({ organization_id: organizationId })
    ),

  /* -------------------------------------------------------- the organisation */

  organization: () => request<OrganizationBundle>('/api/org'),

  updateOrganization: (body: Record<string, string>) => request<OrganizationBundle>('/api/org', patch(body)),

  saveProfile: (body: Partial<OrganizationProfile>) =>
    request<{ profile: OrganizationProfile; saved: boolean; template_available: boolean; note: string }>(
      '/api/org/profile',
      put(body)
    ),

  addFacility: (body: { name: string; location?: string; notes?: string }) =>
    request<{ facility: OrganizationBundle['facilities'][number]; saved: boolean }>('/api/org/facilities', post(body)),

  removeFacility: (id: string) => request<{ removed: boolean }>(`/api/org/facilities/${id}`, { method: 'DELETE' }),

  addMember: (email: string, role: OrganizationRole) =>
    request<{ member: { user_id: string; email: string; role: OrganizationRole }; note: string }>(
      '/api/org/members',
      post({ email, role })
    ),

  removeMember: (userId: string) => request<{ removed: boolean; note: string }>(`/api/org/members/${userId}`, { method: 'DELETE' }),

  history: (limit = 25) => request<HistoryResponse>(`/api/org/history${query({ limit })}`),

  myListings: (filters: { status?: string; kind?: string } = {}) =>
    request<MyListingsResponse>(`/api/org/listings/mine${query(filters)}`),

  editListing: (id: string, body: ListingPatch) =>
    request<{ listing: Listing; saved: boolean; changed: string[] }>(`/api/org/listings/${id}`, patch(body)),

  setListingStatus: (id: string, status: 'active' | 'paused' | 'closed') =>
    request<{ listing: Listing; status: string; saved: boolean; note: string }>(
      `/api/org/listings/${id}/status`,
      post({ status })
    ),
};

/** The three body shapes the mutating routes use, in one place. */
function post(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function put(body: unknown): RequestInit {
  return { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function patch(body: unknown): RequestInit {
  return { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}
