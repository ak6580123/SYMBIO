'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { DemoTag, Empty, Notice, ScoreRing, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import { inr, REUSE_TYPE_LABEL, reuseTypeTone, titleCase } from '@/lib/format';
import type { MatchCard } from '@/lib/types';

const REUSE_OPTIONS = ['DIRECT_REUSE', 'REQUIRES_PROCESSING', 'INDUSTRIAL_ONLY', 'UNKNOWN'];

export default function MatchesPage() {
  const [filters, setFilters] = useState({
    sector: '',
    max_distance_km: '',
    min_match_score: '0',
    min_quantity: '',
    reuse_type: '',
    processing: '',
    min_estimated_value: '',
  });
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [sectors, setSectors] = useState<{ sector: string; label: string }[]>([]);
  const [meta, setMeta] = useState({ count: 0, filtered_from: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .recipients()
      .then((data) => setSectors(data.sectors))
      .catch(() => setSectors([]));
  }, []);

  // Debounced so dragging the distance slider does not hammer the API.
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true);
      api
        .matches({
          sector: filters.sector || undefined,
          max_distance_km: filters.max_distance_km ? Number(filters.max_distance_km) : undefined,
          min_match_score: Number(filters.min_match_score) || 0,
          min_quantity: filters.min_quantity ? Number(filters.min_quantity) : undefined,
          reuse_type: filters.reuse_type || undefined,
          processing: filters.processing || undefined,
          min_estimated_value: filters.min_estimated_value ? Number(filters.min_estimated_value) : undefined,
        })
        .then((data) => {
          setMatches(data.matches);
          setMeta({ count: data.count, filtered_from: data.filtered_from });
          setError(null);
        })
        .catch((err) => setError(err instanceof Error ? err.message : 'Could not load matches'))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [filters]);

  const set = (key: string, value: string) => setFilters((prev) => ({ ...prev, [key]: value }));
  const reset = () =>
    setFilters({
      sector: '',
      max_distance_km: '',
      min_match_score: '0',
      min_quantity: '',
      reuse_type: '',
      processing: '',
      min_estimated_value: '',
    });

  const distanceMax = useMemo(() => Number(filters.max_distance_km) || 300, [filters.max_distance_km]);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-100">Matches</h1>
          <p className="mt-1 text-sm text-slate-500">
            Ranked reuse opportunities across every analysis. Scores come from the deterministic engine.
          </p>
        </div>
        <DemoTag />
      </header>

      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        {/* Filters */}
        <aside className="panel h-fit p-4 lg:sticky lg:top-20">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">Filters</h2>
            <button onClick={reset} className="text-[11px] text-slate-500 underline hover:text-slate-300">
              reset
            </button>
          </div>

          <div className="space-y-4">
            <FilterField label="Sector">
              <select className="input" value={filters.sector} onChange={(e) => set('sector', e.target.value)}>
                <option value="">All sectors</option>
                {sectors.map((s) => (
                  <option key={s.sector} value={s.sector}>
                    {s.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label={`Maximum distance · ${filters.max_distance_km || 300} km`}>
              <input
                type="range"
                min={5}
                max={300}
                step={5}
                value={distanceMax}
                onChange={(e) => set('max_distance_km', e.target.value)}
                className="w-full accent-emerald-400"
              />
            </FilterField>

            <FilterField label={`Minimum match score · ${filters.min_match_score}%`}>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={Number(filters.min_match_score)}
                onChange={(e) => set('min_match_score', e.target.value)}
                className="w-full accent-emerald-400"
              />
            </FilterField>

            <FilterField label="Minimum quantity (t/month)">
              <input
                type="number"
                min={0}
                step="0.5"
                className="input"
                value={filters.min_quantity}
                onChange={(e) => set('min_quantity', e.target.value)}
                placeholder="any"
              />
            </FilterField>

            <FilterField label="Reuse type">
              <select className="input" value={filters.reuse_type} onChange={(e) => set('reuse_type', e.target.value)}>
                <option value="">Any</option>
                {REUSE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {REUSE_TYPE_LABEL[option as keyof typeof REUSE_TYPE_LABEL]}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Processing">
              <select className="input" value={filters.processing} onChange={(e) => set('processing', e.target.value)}>
                <option value="">Any</option>
                <option value="direct">Direct reuse only</option>
                <option value="processing_required">Processing required</option>
              </select>
            </FilterField>

            <FilterField label="Minimum est. value (₹/month)">
              <input
                type="number"
                min={0}
                step={500}
                className="input"
                value={filters.min_estimated_value}
                onChange={(e) => set('min_estimated_value', e.target.value)}
                placeholder="any"
              />
            </FilterField>
          </div>
        </aside>

        {/* Results */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>
              {loading ? 'Filtering…' : `${meta.count} of ${meta.filtered_from} matches`}
            </span>
            <Link href="/analyze" className="text-accent hover:underline">
              + Analyze new waste
            </Link>
          </div>

          {error && <Notice tone="danger">{error}</Notice>}

          {loading ? (
            <div className="panel panel-pad">
              <Spinner label="Scoring…" />
            </div>
          ) : matches.length === 0 ? (
            <div className="panel">
              <Empty title="No matches for these filters" hint="Loosen the distance or score filter and try again." />
            </div>
          ) : (
            <ul className="space-y-3">
              {matches.map((match) => (
                <li key={match.id} className="panel p-4">
                  <div className="flex flex-wrap items-start gap-4">
                    <ScoreRing score={match.score} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-slate-100">{match.company_name}</h3>
                        <span className={`chip ${reuseTypeTone(match.reuse_type)}`}>
                          {REUSE_TYPE_LABEL[match.reuse_type]}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {match.sector_label} · {match.location}
                      </p>

                      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] sm:grid-cols-4">
                        <Cell label="Distance" value={`${match.distance_km} km`} />
                        <Cell
                          label="Required"
                          value={`${match.required_quantity_range_t_per_month[0]}–${match.required_quantity_range_t_per_month[1]} t/mo`}
                        />
                        <Cell label="Available" value={`${match.available_quantity_t_per_month} t/mo`} />
                        <Cell label="Material" value={match.material} />
                        <Cell label="Est. value" value={inr(match.estimated_value_inr_per_month)} accent />
                        <Cell label="Est. CO₂e" value={`${match.estimated_co2e_t_per_month} t/mo`} accent />
                        <Cell label="From" value={match.source_location} />
                        <Cell label="Route" value={titleCase(match.reuse_type.toLowerCase())} />
                      </dl>

                      <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">
                        <span className="text-accent">✓</span> {match.reasons[0]}
                      </p>
                    </div>
                    <Link href={`/matches/${match.id}`} className="btn-ghost shrink-0 text-xs">
                      View Match
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

function Cell({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-slate-600">{label}</dt>
      <dd className={`truncate tabular-nums ${accent ? 'text-accent' : 'text-slate-300'}`}>{value}</dd>
    </div>
  );
}
