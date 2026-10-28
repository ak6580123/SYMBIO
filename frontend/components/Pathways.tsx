'use client';

/**
 * Multiple reuse pathways (Feature 1).
 *
 * These are not invented options: the backend groups this analysis's own ranked
 * matches into the distinct routes they represent, so a material with two
 * compatible partners shows two pathways and nothing more. The selected
 * optimisation mode decides which pathway is primary, because the mode decides
 * which partner leads - the pathway rows are the same rows the list shows.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { CompareTable, PATHWAY_COLUMNS } from '@/components/Compare';
import { Empty, Notice, Panel, ScoreRing, Spinner } from '@/components/ui';
import { api, type MatchQuery } from '@/lib/api';
import {
  inr,
  MODE_LABEL,
  OPTIMIZATION_MODES,
  REUSE_TYPE_LABEL,
  reuseTypeTone,
  SAFETY_LABEL,
  distanceShort,
 } from '@/lib/format';
import type { MatchSort, PathwayResponse, PathwayRow } from '@/lib/types';

export default function Pathways({
  analysisId,
  sort = 'score',
  onSortChange,
  filters = {},
}: {
  analysisId: string;
  sort?: MatchSort;
  /** Pass this to let the panel carry its own optimisation-mode switch. */
  onSortChange?: (sort: MatchSort) => void;
  filters?: Omit<MatchQuery, 'analysis_id'>;
}) {
  const [data, setData] = useState<PathwayResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [compare, setCompare] = useState<PathwayRow[]>([]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .pathways({ analysis_id: analysisId, sort, ...filters })
      .then((body) => {
        if (!alive) return;
        setData(body);
        // Keep the selection meaningful after the mode or filters change.
        const visible = [body.primary, ...body.alternatives].filter(Boolean) as PathwayRow[];
        setCompare((prev) => prev.filter((row) => visible.some((v) => v.match_id === row.match_id)).slice(0, 3));
        setError(null);
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : 'Could not load pathways'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId, sort, JSON.stringify(filters)]);

  const toggle = (row: PathwayRow) =>
    setCompare((prev) =>
      prev.some((item) => item.match_id === row.match_id)
        ? prev.filter((item) => item.match_id !== row.match_id)
        : [...prev, row].slice(-3),
    );

  const rows = data ? ([data.primary, ...data.alternatives].filter(Boolean) as PathwayRow[]) : [];

  return (
    <Panel
      title={`Reuse pathways (${data ? data.pathway_count : '…'})`}
      action={
        <div className="flex items-center gap-3">
          {onSortChange && (
            <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Optimisation mode">
              {OPTIMIZATION_MODES.map((mode) => (
                <button
                  key={mode.value}
                  title={mode.note}
                  onClick={() => onSortChange(mode.value)}
                  className={`rounded border px-2 py-0.5 text-[10px] transition-colors ${
                    sort === mode.value
                      ? 'border-accent/50 bg-accent/10 text-accent'
                      : 'border-ink-700 text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          )}
          {data && (
            <span className="hidden text-[11px] text-slate-500 sm:inline">
              {MODE_LABEL[sort]} · {data.partner_count} partners
              {data.excluded_by_safety > 0 ? ` · ${data.excluded_by_safety} refused by the safety layer` : ''}
            </span>
          )}
        </div>
      }
    >
      {loading ? (
        <Spinner label="Grouping routes…" />
      ) : error ? (
        <Notice tone="danger">{error}</Notice>
      ) : !data || rows.length === 0 ? (
        <Empty
          title="No pathway could be built from these matches"
          hint="Pathways come from ranked matches. If every route was filtered out or refused on safety grounds, there is nothing to group."
        />
      ) : (
        <div className="space-y-4">
          {data.sort_note && (
            <p className="rounded-md border border-ink-700 bg-ink-900 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
              {data.sort_note}
            </p>
          )}

          <p className="caption leading-relaxed">
            One pathway per distinct route in this result set: same processing step, same reuse sector, same product.
            Where several partners perform the same route, the best-ranked one leads the row and the others are named
            inside it.
          </p>

          {/* Primary pathway, shown as the route itself rather than a partner card. */}
          <div className="rounded-md border border-accent/30 bg-accent/5 p-3">
            <div className="flex flex-wrap items-start gap-3">
              <ScoreRing score={rows[0].score} size={58} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip border-accent/40 bg-accent/10 text-accent">Primary route</span>
                  <span className={`chip ${reuseTypeTone(rows[0].reuse_type)}`}>{REUSE_TYPE_LABEL[rows[0].reuse_type]}</span>
                  <span className="chip border-ink-600 text-slate-400">{SAFETY_LABEL[rows[0].safety_level]}</span>
                </div>
                <ol className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-300">
                  {rows[0].pathway.map((step, index) => (
                    <li key={`${step}-${index}`} className="flex items-center gap-1.5">
                      <span className="rounded border border-ink-700 bg-ink-900 px-2 py-0.5">{step}</span>
                      {index < rows[0].pathway.length - 1 && <span className="text-slate-600">→</span>}
                    </li>
                  ))}
                </ol>
                <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{rows[0].summary}</p>
                <PathwayNumbers row={rows[0]} />
                {rows[0].other_partners.length > 0 && (
                  <p className="mt-1.5 text-[11px] text-slate-500">
                    Same route, other partners: {rows[0].other_partners.join(', ')}
                  </p>
                )}
                <Link href={`/matches/${rows[0].match_id}`} className="mt-2 inline-block text-[11px] link">
                  Why this partner scored {rows[0].score.toFixed(1)}% →
                </Link>
              </div>
            </div>
          </div>

          {/* Alternatives */}
          {rows.length > 1 ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="label">{rows.length - 1} alternative{rows.length > 2 ? 's' : ''}</p>
                <label className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  <input
                    type="checkbox"
                    className="accent-emerald-400"
                    checked={compare.length === rows.length}
                    onChange={(event) => setCompare(event.target.checked ? rows.slice(0, 3) : [])}
                  />
                  select all for comparison
                </label>
              </div>
              {rows.slice(1).map((row) => (
                <div
                  key={row.match_id}
                  className="flex flex-wrap items-center gap-3 rounded-md border border-ink-700 bg-ink-900 px-3 py-2"
                >
                  <input
                    type="checkbox"
                    aria-label={`Compare ${row.partner}`}
                    className="accent-emerald-400"
                    checked={compare.some((item) => item.match_id === row.match_id)}
                    onChange={() => toggle(row)}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-slate-200">
                      {row.processing} → {row.sector_label} → {row.product}
                    </p>
                    <p className="truncate text-[11px] text-slate-500">
                      {row.partner} · {row.partner_type_label}
                      {row.other_partners.length > 0 ? ` +${row.other_partners.length} more on this route` : ''}
                    </p>
                  </div>
                  <span className={`chip ${reuseTypeTone(row.reuse_type)}`}>{REUSE_TYPE_LABEL[row.reuse_type]}</span>
                  {['high', 'hazardous', 'unknown'].includes(row.safety_level) && (
                    <span
                      className="chip border-rose-500/40 bg-rose-500/10 text-rose-200"
                      title={`Safety class from the knowledge base: ${SAFETY_LABEL[row.safety_level]}`}
                    >
                      {SAFETY_LABEL[row.safety_level]}
                    </span>
                  )}
                  <span className="w-14 text-right text-xs tabular-nums text-slate-300">{row.score.toFixed(1)}%</span>
                  <span className="w-20 text-right text-xs tabular-nums text-slate-400">{inr(row.estimated_value_inr_per_month)}</span>
                  <span className="w-20 text-right text-xs tabular-nums text-slate-400">{row.estimated_co2e_t_per_month} t CO₂e</span>
                  <Link href={`/matches/${row.match_id}`} className="text-[11px] link">
                    open
                  </Link>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-md border border-ink-700 bg-ink-900 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
              Only one route exists for this material in the current result set. Symbio does not pad the list with
              alternatives the engine did not find — widen the distance filter, change the optimisation mode, or add a
              recipient that works this material.
            </p>
          )}

          {compare.length >= 2 && (
            <div className="rounded-md border border-ink-700 bg-ink-950/60 p-3">
              <p className="label mb-2">Compare routes ({compare.length})</p>
              <CompareTable
                rows={compare}
                columns={PATHWAY_COLUMNS}
                titleOf={(row) => row.partner}
                subOf={(row) => `${row.sector_label} · ${distanceShort(row.distance_km)}`}
                onRemove={(index) => setCompare((prev) => prev.filter((_, i) => i !== index))}
              />
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function PathwayNumbers({ row }: { row: PathwayRow }) {
  const cells = [
    { label: 'Partner', value: row.partner },
    { label: 'Distance', value: distanceShort(row.distance_km) },
    { label: 'Quantity routed', value: `${row.matched_quantity_t_per_month} t/mo` },
    { label: 'Est. value', value: `${inr(row.estimated_value_inr_per_month)}/mo` },
    { label: 'Est. CO₂e', value: `${row.estimated_co2e_t_per_month} t/mo` },
  ];
  return (
    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-5">
      {cells.map((cell) => (
        <div key={cell.label}>
          <dt className="text-[10px] uppercase tracking-wider text-slate-600">{cell.label}</dt>
          <dd className="truncate tabular-nums text-slate-300">{cell.value}</dd>
        </div>
      ))}
    </dl>
  );
}
