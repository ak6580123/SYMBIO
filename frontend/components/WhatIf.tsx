'use client';

/**
 * What-If simulator (Feature 6).
 *
 * Deliberately thin: the form only posts to `/api/scenario`, which re-runs the
 * same matching engine and the same safety layer on a temporary source record.
 * There is no second scorer here, the stored analysis is never written to, and
 * "reset" is simply dropping the scenario response - which is why nothing has to
 * be undone.
 */

import { useEffect, useState } from 'react';

import { Notice, Panel, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import {
  inr,
  REUSE_TYPE_LABEL,
  reuseTypeTone,
  distanceShort,
 } from '@/lib/format';
import type { Analysis, Frequency, MatchSort, ScenarioResponse } from '@/lib/types';

const UNITS = ['tonnes', 'kg', 'litres', 'units'];
const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: 'one_time', label: 'One-time' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'continuous', label: 'Continuous' },
];

export default function WhatIf({
  analysis,
  sort = 'score',
}: {
  analysis: Analysis;
  /** The mode the matches list is using, so both views answer the same question. */
  sort?: MatchSort;
}) {
  const [form, setForm] = useState(() => defaults(analysis));
  const [data, setData] = useState<ScenarioResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A different analysis means different defaults; a stale scenario would be
  // worse than no scenario at all.
  useEffect(() => {
    setForm(defaults(analysis));
    setData(null);
    setError(null);
    // Keyed on the id on purpose: a fresh analysis object with the same id must
    // not throw away a scenario the user is still reading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis.id]);

  const dirty =
    !data &&
    (form.quantity !== defaults(analysis).quantity ||
      form.location !== defaults(analysis).location ||
      form.frequency !== defaults(analysis).frequency ||
      form.unit !== defaults(analysis).unit);

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    const quantity = Number(form.quantity);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setError('Enter a quantity greater than zero.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const body = await api.scenario(
        {
          analysis_id: analysis.id,
          quantity,
          unit: form.unit,
          frequency: form.frequency,
          location: form.location.trim() || null,
        },
        { sort },
      );
      setData(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The scenario could not be run');
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setData(null);
    setError(null);
    setForm(defaults(analysis));
  };

  const changed = data ? Object.entries(data.scenario.changed) : [];

  return (
    <Panel
      title="What-if simulator"
      action={
        data ? (
          <button onClick={reset} className="text-[11px] link">
            Reset to original
          </button>
        ) : (
          <span className="caption">temporary · nothing is saved</span>
        )
      }
    >
      <form onSubmit={run} className="space-y-3">
        <p className="caption leading-relaxed">
          Change one thing about this stream and re-run the real engine on it. Cadence and amount are normalised to
          tonnes/month first, exactly as they were in the analysis, so the two results stay comparable.
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="label mb-1.5 block">Quantity</span>
            <input
              type="number"
              min={0.1}
              step="0.1"
              className="input"
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </label>
          <label className="block">
            <span className="label mb-1.5 block">Unit</span>
            <select
              className="input"
              value={form.unit}
              onChange={(event) => setForm({ ...form, unit: event.target.value })}
            >
              {UNITS.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label mb-1.5 block">Frequency</span>
            <select
              className="input"
              value={form.frequency}
              onChange={(event) => setForm({ ...form, frequency: event.target.value as Frequency })}
            >
              {FREQUENCIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label mb-1.5 block">Location</span>
            <input
              className="input"
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
              placeholder="area, city"
            />
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button type="submit" className="btn-primary text-xs" disabled={loading}>
            {loading ? 'Re-running…' : 'Run scenario'}
          </button>
          {dirty && <span className="caption">not run yet</span>}
        </div>
      </form>

      {error && (
        <div className="mt-3">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}

      {loading && (
        <div className="mt-3">
          <Spinner label="Re-scoring every recipient…" />
        </div>
      )}

      {data && !loading && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap gap-1.5">
            {changed.length === 0 ? (
              <span className="chip border-ink-600 text-slate-400">Nothing changed from the stored analysis</span>
            ) : (
              changed.map(([field, delta]) => (
                <span key={field} className="chip border-sky-500/30 bg-sky-500/10 text-sky-200">
                  {field}: {delta.from} → {delta.to}
                </span>
              ))
            )}
          </div>

          {data.scenario.warnings.map((warning) => (
            <Notice key={warning} tone="warn">
              {warning}
            </Notice>
          ))}

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {DELTA_ROWS.map((row) => {
              const delta = data.totals_change[row.key] ?? 0;
              return (
                <div key={row.key} className="rounded-md border border-ink-700 bg-ink-900 p-3">
                  <p className="label">{row.label}</p>
                  <p className="mt-1 text-sm tabular-nums text-slate-100">{row.format(row.get(data.totals))}</p>
                  <p
                    className={`mt-0.5 text-[11px] tabular-nums ${
                      delta > 0 ? 'text-emerald-400' : delta < 0 ? 'text-rose-400' : 'text-slate-600'
                    }`}
                  >
                    {delta === 0 ? 'no change' : `${delta > 0 ? '+' : ''}${row.format(delta)} vs original`}
                  </p>
                </div>
              );
            })}
          </div>

          <div>
            <p className="label mb-1.5">
              Ranking under this scenario · {data.count} of {data.scored_partners} partners
            </p>
            <ol className="space-y-1.5">
              {data.matches.slice(0, 8).map((card) => (
                <li
                  key={card.id}
                  className="flex flex-wrap items-center gap-3 rounded-md border border-ink-700 bg-ink-900 px-3 py-2 text-[11px]"
                >
                  <span className="w-14 shrink-0 tabular-nums text-slate-500">
                    {card.scenario_rank}
                    {card.rank_change !== null && card.rank_change !== 0 && (
                      <span className={card.rank_change > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {' '}
                        {card.rank_change > 0 ? '▲' : '▼'}
                        {Math.abs(card.rank_change)}
                      </span>
                    )}
                    {card.is_new && <span className="text-sky-300"> new</span>}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-slate-200">{card.company_name}</span>
                  <span className={`chip ${reuseTypeTone(card.reuse_type)}`}>{REUSE_TYPE_LABEL[card.reuse_type]}</span>
                  <span className="w-20 text-right tabular-nums text-slate-300">{card.score.toFixed(1)}%</span>
                  <span className="w-20 text-right text-[11px] tabular-nums text-text-faint">
                    {distanceShort(card.distance_km)}
                  </span>
                  <span className="w-24 text-right tabular-nums text-slate-400">
                    {inr(card.estimated_value_inr_per_month)}
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-600">
              {data.note} Value and CO₂e are the same estimates the analysis produces, recomputed at the scenario
              quantity — they are not quotes or measured emissions.
            </p>
          </div>
        </div>
      )}
    </Panel>
  );
}

const DELTA_ROWS = [
  {
    label: 'Diverted per month',
    key: 'allocated_t_per_month',
    get: (t: ScenarioResponse['totals']) => t.allocated_t_per_month,
    format: (value: number) => `${Math.abs(value).toFixed(2).replace(/\.00$/, '')} t/mo`,
  },
  {
    label: 'Est. value per month',
    key: 'estimated_value_inr_per_month',
    get: (t: ScenarioResponse['totals']) => t.estimated_value_inr_per_month,
    format: (value: number) => inr(Math.abs(value)),
  },
  {
    label: 'Est. CO₂e avoided',
    key: 'estimated_co2e_avoided_t_per_month',
    get: (t: ScenarioResponse['totals']) => t.estimated_co2e_avoided_t_per_month,
    format: (value: number) => `${Math.abs(value).toFixed(2)} t`,
  },
  {
    label: 'Viable partners',
    key: 'viable_matches',
    get: (t: ScenarioResponse['totals']) => t.viable_matches,
    format: (value: number) => `${Math.abs(value)}`,
  },
];

function defaults(analysis: Analysis) {
  return {
    // The stored record is normalised to t/month, so the starting point of the
    // form is that number in tonnes: opening the panel and pressing run changes
    // nothing, which is the honest default.
    quantity: String(analysis.source.quantity_t_per_month),
    unit: 'tonnes',
    frequency: analysis.source.frequency as Frequency,
    location: analysis.source.location,
  };
}
