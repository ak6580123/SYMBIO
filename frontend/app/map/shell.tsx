'use client';

import dynamic from 'next/dynamic';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { DemoTag, Notice, Panel, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import type { Analysis, MapPayload } from '@/lib/types';

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

  const [data, setData] = useState<MapPayload | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The selector needs the stored analyses; the demo seeds three on startup.
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

  useEffect(() => {
    setLoading(true);
    api
      .map(analysisId || undefined)
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load the map'))
      .finally(() => setLoading(false));
  }, [analysisId]);

  const select = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set('analysis', value);
    else next.delete('analysis');
    router.replace(`/map${next.toString() ? `?${next.toString()}` : ''}`);
  };

  const active = analyses.find((row) => row.id === analysisId);

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center gap-3 p-3">
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <span className="label">View</span>
          <select className="input w-auto min-w-[260px]" value={analysisId} onChange={(e) => select(e.target.value)}>
            <option value="">Whole network (all sources and compatible recipients)</option>
            {analyses.map((row) => (
              <option key={row.id} value={row.id}>
                {row.material.name} · {row.source.location} · {row.source.quantity_t_per_month} t/mo
              </option>
            ))}
          </select>
        </label>
        <DemoTag />
        <span className="ml-auto text-[11px] text-slate-600">OpenStreetMap · demo coordinates</span>
      </div>

      {error && <Notice tone="danger">{error}</Notice>}

      {loading ? (
        <div className="panel panel-pad">
          <Spinner label="Loading map…" />
        </div>
      ) : data ? (
        <MapView data={data} />
      ) : null}

      {active && (
        <Panel title="About this view">
          <dl className="grid gap-3 text-[11px] sm:grid-cols-4">
            <div>
              <dt className="label">Material</dt>
              <dd className="mt-0.5 text-slate-300">{active.material.name}</dd>
            </div>
            <div>
              <dt className="label">Source</dt>
              <dd className="mt-0.5 text-slate-300">{active.source.location}</dd>
            </div>
            <div>
              <dt className="label">Quantity</dt>
              <dd className="mt-0.5 text-slate-300">{active.source.quantity_t_per_month} t/month</dd>
            </div>
            <div>
              <dt className="label">Connections shown</dt>
              <dd className="mt-0.5 text-slate-300">Top {Math.min(15, active.matches.length)} ranked matches</dd>
            </div>
          </dl>
        </Panel>
      )}
    </div>
  );
}
