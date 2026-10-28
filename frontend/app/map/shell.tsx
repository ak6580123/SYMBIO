'use client';

import dynamic from 'next/dynamic';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import NetworkView from '@/components/NetworkView';
import { Notice, Panel, Spinner } from '@/components/ui';
import { api, type MatchQuery } from '@/lib/api';
import { OPTIMIZATION_MODES, REUSE_TYPE_LABEL, SAFETY_LABEL } from '@/lib/format';
import type { Analysis, MapPayload, MatchSort, SafetyLevel } from '@/lib/types';

// Leaflet reads `window` the moment it is imported, so it cannot be evaluated
// during SSR at all - 'use client' alone is not enough. Load it only in the
// browser.
const MapView = dynamic(() => import('@/components/MapView'), {
  ssr: false,
  loading: () => (
    <div className="panel panel-pad">
      <Spinner label="Loading map…" />
    </div>
  ),
});

export default function MapShell() {
  const params = useSearchParams();
  const router = useRouter();
  const analysisId = params.get('analysis') || '';
  // Filters live in the URL so a filtered map is a link you can hand someone,
  // and so the map and the Matches page can be compared side by side.
  const filters: Omit<MatchQuery, 'analysis_id'> = {
    partner_type: params.get('partner_type') || undefined,
    safety_level: params.get('safety_level') || undefined,
    reuse_type: params.get('reuse_type') || undefined,
    max_distance_km: params.get('max_distance_km') ? Number(params.get('max_distance_km')) : undefined,
    min_match_score: params.get('min_match_score') ? Number(params.get('min_match_score')) : undefined,
  };
  const filterKeys = Object.entries(filters).filter(([, value]) => value !== undefined).length;
  // The optimisation mode is part of the map query too: the lines and the popups
  // are drawn from the same ordered result the Matches list shows.
  const sort = (params.get('sort') || 'score') as MatchSort;

  const [data, setData] = useState<MapPayload | null>(null);
  /** 'map' answers where, 'network' answers who is connected to whom. Same payload. */
  const [view, setView] = useState<'map' | 'network'>('map');
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The selector reads the stored analyses, which are seeded by the service on startup.
  useEffect(() => {
    api
      .analyses()
      .then(async (list) => {
        const rows = await Promise.all(
          list.analyses.map(async (row) => {
            try {
              return await api.analysis(row.id);
            } catch {
              return null;
            }
          }),
        );
        setAnalyses(rows.filter((row): row is Analysis => row !== null));
      })
      .catch(() => setAnalyses([]));
  }, []);

  const filterKey = JSON.stringify({ ...filters, sort });

  useEffect(() => {
    setLoading(true);
    api
      .map(analysisId || undefined, { ...filters, sort })
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load the map'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId, filterKey]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`/map${next.toString() ? `?${next.toString()}` : ''}`);
  };

  const chosen = analyses.find((row) => row.id === analysisId);

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center gap-3 p-3">
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <span className="label">View</span>
          <select
            className="input w-auto min-w-[260px]"
            value={analysisId}
            onChange={(e) => setParam('analysis', e.target.value)}
          >
            <option value="">Whole network (all sources and compatible recipients)</option>
            {analyses.map((row) => (
              <option key={row.id} value={row.id}>
                {row.material.name} · {row.source.location} · {row.source.quantity_t_per_month} t/mo
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <span className="label">Best by</span>
          <select
            className="input w-auto min-w-[150px] py-1.5 text-xs"
            value={sort}
            onChange={(e) => setParam('sort', e.target.value === 'score' ? '' : e.target.value)}
          >
            {OPTIMIZATION_MODES.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1" role="group" aria-label="Map or network view">
          {(['map', 'network'] as const).map((option) => (
            <button
              key={option}
              onClick={() => setView(option)}
              aria-pressed={view === option}
              title={
                option === 'map'
                  ? 'Geographic view: where the sources and recipients are'
                  : 'Network view: which source reaches which recipient, through which material'
              }
              className={`rounded-md border px-2.5 py-1 text-[11px] uppercase tracking-wider transition-colors ${
                view === option
                  ? 'border-accent/50 bg-accent/10 text-accent'
                  : 'border-ink-700 text-slate-500 hover:text-slate-300'
              }`}
            >
              {option}
            </button>
          ))}
        </div>
        <span className="ml-auto text-[11px] text-slate-600">
          {view === 'map'
            ? 'Street layer from OpenStreetMap · positions from each record'
            : 'The same routes and scores, drawn as a network'}
        </span>

        <div className="flex flex-wrap items-end gap-2 border-l border-ink-700 pl-3">
          <Pick
            label="Partner type"
            value={filters.partner_type ?? ''}
            onChange={(v) => setParam('partner_type', v)}
            options={[
              ['industry', 'Industry'],
              ['sme', 'SME / artisan'],
              ['recycler', 'Recycler'],
              ['processing', 'Processing / recovery'],
              ['agriculture', 'Agriculture'],
              ['community', 'Community'],
            ]}
          />
          <Pick
            label="Safety"
            value={filters.safety_level ?? ''}
            onChange={(v) => setParam('safety_level', v)}
            options={(['low', 'moderate', 'high', 'hazardous', 'unknown'] as SafetyLevel[]).map((level) => [
              level,
              SAFETY_LABEL[level],
            ])}
          />
          <Pick
            label="Use category"
            value={filters.reuse_type ?? ''}
            onChange={(v) => setParam('reuse_type', v)}
            options={['DIRECT_REUSE', 'REQUIRES_PROCESSING', 'INDUSTRIAL_ONLY', 'RESTRICTED'].map((type) => [
              type,
              REUSE_TYPE_LABEL[type as keyof typeof REUSE_TYPE_LABEL],
            ])}
          />
          <Pick
            label="Within km"
            value={filters.max_distance_km?.toString() ?? ''}
            onChange={(v) => setParam('max_distance_km', v)}
            options={[
              ['15', '15 km'],
              ['30', '30 km'],
              ['60', '60 km'],
              ['120', '120 km'],
            ]}
          />
          <Pick
            label="Min score"
            value={filters.min_match_score?.toString() ?? ''}
            onChange={(v) => setParam('min_match_score', v)}
            options={[
              ['50', '50%'],
              ['60', '60%'],
              ['70', '70%'],
              ['80', '80%'],
            ]}
          />
          {filterKeys > 0 && (
            <button
              onClick={() => {
                ['partner_type', 'safety_level', 'reuse_type', 'max_distance_km', 'min_match_score'].forEach((key) =>
                  setParam(key, ''),
                );
              }}
              className="pb-1 text-[11px] text-slate-500 underline hover:text-slate-300"
            >
              clear {filterKeys}
            </button>
          )}
        </div>
      </div>

      <p className="caption leading-relaxed">
        These are the same filters the Matches page applies — the map draws the current result of that query, not a
        separate set of places. Lines from a source are its scored matches, ordered as the list orders them.
      </p>

      {error && <Notice tone="danger">{error}</Notice>}

      {loading ? (
        <div className="panel panel-pad">
          <Spinner label="Loading map…" />
        </div>
      ) : data ? (
        view === 'map' ? (
          <MapView data={data} />
        ) : (
          <Panel
            title="Network view"
            action={
              <span className="caption">
                {data.links.length} routes · {data.nodes.length} places
              </span>
            }
          >
            <NetworkView payload={data} />
          </Panel>
        )
      ) : null}

      {chosen && (
        <Panel title="About this view">
          <dl className="grid gap-3 text-[11px] sm:grid-cols-4">
            <div>
              <dt className="label">Material</dt>
              <dd className="mt-0.5 text-slate-300">{chosen.material.name}</dd>
            </div>
            <div>
              <dt className="label">Source</dt>
              <dd className="mt-0.5 text-slate-300">{chosen.source.location}</dd>
            </div>
            <div>
              <dt className="label">Quantity</dt>
              <dd className="mt-0.5 text-slate-300">{chosen.source.quantity_t_per_month} t/month</dd>
            </div>
            <div>
              <dt className="label">Connections shown</dt>
              <dd className="mt-0.5 text-slate-300">Top {chosen.matches.length} ranked matches</dd>
            </div>
          </dl>
        </Panel>
      )}
    </div>
  );
}

/** One compact filter select. Empty value means "no filter", same as the API. */
function Pick({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="label mb-1 block">{label}</span>
      <select className="input w-auto min-w-[120px] py-1.5 text-xs" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Any</option>
        {options.map(([key, text]) => (
          <option key={key} value={key}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}
