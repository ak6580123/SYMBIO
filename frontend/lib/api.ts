// Thin client for the Symbio API.
//
// Requests go to /api/* on the Next server, which rewrites them to FastAPI
// (see next.config.mjs). Nothing here ever holds a secret or a backend host.

import type {
  AnalyzeResponse,
  Analysis,
  ChatResponse,
  DashboardData,
  HealthData,
  ImpactData,
  MapPayload,
  MatchCard,
  MaterialRecord,
  Match,
  Recipient,
  UploadResponse,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
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
    throw new ApiError(0, 'Cannot reach the Symbio API. Is the backend running on port 8000?');
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }

    // A bare 500 with no JSON body means the Next dev proxy gave up on the
    // upstream request (it logs "socket hang up / ECONNRESET"). Say so, and say
    // what to change - an opaque 500 here is what made this hard to diagnose.
    if (res.status >= 500 && detail === `Request failed (${res.status})`) {
      detail =
        'The request to the backend was cut off. Analysis waits on local Ollama, which can take ' +
        'over a minute on CPU. Check the backend terminal is still running, and make sure ' +
        'PROXY_TIMEOUT_MS in next.config.mjs is above OLLAMA_TIMEOUT_SECONDS.';
    }

    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function query(params: Record<string, string | number | undefined | null>): string {
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
  attached_text?: string | null;
  attached_filename?: string | null;
}

export const api = {
  health: () => request<HealthData>('/api/health'),

  analyze: (input: AnalyzeInput) =>
    request<AnalyzeResponse>('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),

  analysis: (id: string) => request<Analysis>(`/api/analyses/${id}`),

  analyses: () => request<{ analyses: { id: string; material: string; matches: number }[] }>('/api/analyses'),

  matches: (filters: {
    analysis_id?: string;
    sector?: string;
    max_distance_km?: number;
    min_match_score?: number;
    min_quantity?: number;
    reuse_type?: string;
    processing?: string;
    min_estimated_value?: number;
  }) =>
    request<{ matches: MatchCard[]; count: number; filtered_from: number }>(
      `/api/matches${query(filters)}`,
      { method: 'POST' },
    ),

  matchDetail: (analysisId: string, recipientId: string) =>
    request<{
      match: Match;
      analysis: Pick<Analysis, 'id' | 'source' | 'material' | 'identification' | 'totals'>;
      weights_used: Record<string, number>;
      demo_data: boolean;
    }>(`/api/matches/${analysisId}/${recipientId}`),

  materials: () => request<{ materials: MaterialRecord[]; count: number }>('/api/materials'),

  recipients: (sector?: string) =>
    request<{ recipients: Recipient[]; count: number; sectors: { sector: string; label: string }[] }>(
      `/api/recipients${query({ sector })}`,
    ),

  dashboard: () => request<DashboardData>('/api/dashboard'),

  impact: () => request<ImpactData>('/api/impact'),

  map: (analysisId?: string) => request<MapPayload>(`/api/map${query({ analysis_id: analysisId })}`),

  chat: (analysisId: string, question: string, matchId?: string) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: analysisId, question, match_id: matchId }),
    }),

  upload: async (file: File): Promise<UploadResponse> => {
    const form = new FormData();
    form.append('file', file);
    return request<UploadResponse>('/api/upload', { method: 'POST', body: form });
  },
};
