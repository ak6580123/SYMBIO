'use client';

/**
 * §11 - several versions of the same decision, side by side.
 *
 * Every column here is one call to `POST /api/scenarios/compare`, which runs the same
 * engine, the same safety layer and the same freight estimate as the single what-if.
 * This component never recomputes a score or a total: the only arithmetic it does is the
 * subtraction the backend already returned in `delta_vs_baseline`.
 */

import { useState } from 'react';

import { Notice, Panel, Spinner, StatusBadge } from '@/components/ui';
import { api } from '@/lib/api';
import { inr } from '@/lib/format';
import type { Analysis, ScenarioColumn, ScenarioCompareResponse, ScenarioConfig } from '@/lib/types';

const RULE_OPTIONS = [
  { key: 'require_viable_transport', label: 'drop hauls that cost more than the load' },
  { key: 'direct_only', label: 'direct reuse only' },
] as const;

export default function ScenarioComparison({ analysis }: { analysis: Analysis }) {
  const [configs, setConfigs] = useState<ScenarioConfig[]>([
    { label: 'As recorded', quantity: analysis.source.quantity_t_per_month },
    { label: 'Four times the volume', quantity: round(analysis.source.quantity_t_per_month * 4) },
  ]);
  const [ceiling, setCeiling] = useState<string[]>(configs.map(() => ''));
  const [flags, setFlags] = useState<string[][]>(configs.map(() => []));
  const [data, setData] = useState<ScenarioCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = (index: number, next: Partial<ScenarioConfig>) =>
    setConfigs((rows) => rows.map((row, position) => (position === index ? { ...row, ...next } : row)));

  const add = () => {
    if (configs.length >= 4) return;
    setConfigs((rows) => [...rows, { label: `Configuration ${rows.length + 1}`, quantity: rows[0].quantity ?? null }]);
    setCeiling((rows) => [...rows, '']);
    setFlags((rows) => [...rows, []]);
  };

  const remove = (index: number) => {
    if (configs.length <= 2) return;
    setConfigs((rows) => rows.filter((_, position) => position !== index));
    setCeiling((rows) => rows.filter((_, position) => position !== index));
    setFlags((rows) => rows.filter((_, position) => position !== index));
    setData(null);
  };

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    const payload = configs.map((config, index) => ({
      ...config,
      max_transport_cost_inr_per_tonne: ceiling[index] ? Number(ceiling[index]) : null,
      require_viable_transport: flags[index].includes('require_viable_transport'),
      max_processing_burden: flags[index].includes('direct_only') ? 0 : null,
    }));
    try {
      setData(await api.compareScenarios(analysis.id, payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not run the comparison');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Panel
      title="Compare scenarios"
      subtitle="Two to four versions of this analysis, each re-run through the same engine - the first column is the baseline"
    >
      <form className="space-y-3" onSubmit={run}>
        <ul className="grid gap-2 lg:grid-cols-2">
          {configs.map((config, index) => (
            <li
              key={`${config.label}-${index}`}
              className="border-b border-line px-1 py-3 last:border-b-0 sm:px-2"
            >
              <div className="flex items-center gap-2">
                <span className="chip chip-slate">{index === 0 ? 'baseline' : `config ${index + 1}`}</span>
                <input
                  className="input min-w-0 flex-1 !py-1 text-xs"
                  value={config.label}
                  onChange={(event) => patch(index, { label: event.target.value })}
                  aria-label="Configuration label"
                />
                {configs.length > 2 && (
                  <button type="button" className="text-[11px] text-text-faint hover:text-danger" onClick={() => remove(index)}>
                    remove
                  </button>
                )}
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                <label className="block">
                  <span className="label mb-1 block">Quantity t/mo</span>
                  <input
                    className="input !py-1 text-xs"
                    inputMode="decimal"
                    value={config.quantity ?? ''}
                    onChange={(event) => patch(index, { quantity: event.target.value ? Number(event.target.value) : null })}
                  />
                </label>
                <label className="block">
                  <span className="label mb-1 block">Location</span>
                  <input
                    className="input !py-1 text-xs"
                    value={config.location ?? analysis.source.location}
                    onChange={(event) => patch(index, { location: event.target.value })}
                  />
                </label>
                <label className="block">
                  <span className="label mb-1 block">Freight ceiling ₹/t</span>
                  <input
                    className="input !py-1 text-xs"
                    inputMode="decimal"
                    value={ceiling[index]}
                    onChange={(event) => setCeiling((rows) => rows.map((row, position) => (position === index ? event.target.value : row)))}
                    placeholder="none"
                  />
                </label>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {RULE_OPTIONS.map((option) => {
                  const on = flags[index].includes(option.key);
                  return (
                    <button
                      type="button"
                      key={option.key}
                      className={`chip ${on ? 'chip-teal' : 'chip-muted'}`}
                      onClick={() =>
                        setFlags((rows) =>
                          rows.map((row, position) =>
                            position === index
                              ? on
                                ? row.filter((key) => key !== option.key)
                                : [...row, option.key]
                              : row,
                          ),
                        )
                      }
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary text-xs" disabled={loading}>
            {loading ? 'Re-running the engine…' : 'Compare scenarios'}
          </button>
          {configs.length < 4 && (
            <button type="button" className="btn-quiet text-xs" onClick={add}>
              Add configuration
            </button>
          )}
          <span className="text-[11px] text-text-faint">
            Nothing is stored: a comparison lives in this response only, and clearing it leaves the analysis untouched.
          </span>
        </div>
      </form>

      {error && (
        <div className="mt-3">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}
      {loading && (
        <div className="mt-3">
          <Spinner label="Running one scenario per configuration…" />
        </div>
      )}

      {data && !loading && (
        <div className="mt-4 space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className="py-1.5 pr-3 text-left font-medium text-text-faint"> </th>
                  {data.configurations.map((column) => (
                    <th key={column.label} className="py-1.5 pr-3 text-left">
                      <span className="font-semibold text-text-strong">{column.label}</span>
                      {column.label !== data.baseline_label && <span className="ml-1.5 font-normal text-text-faint">vs baseline</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <Row
                  label="Best match"
                  cells={data.configurations.map((column) =>
                    column.best_match ? (
                      <span key={column.label}>
                        {column.best_match.company_name}
                        <span className="ml-1.5 tabular-nums text-text-faint">{column.best_match.score.toFixed(1)}</span>
                      </span>
                    ) : (
                      <span key={column.label} className="text-text-faint">
                        none after the rules
                      </span>
                    ),
                  )}
                />
                <Row
                  label="Routes shown"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {column.match_count} of {column.scored_partners}
                      {column.dropped_by_rule.length > 0 && (
                        <span className="ml-1.5 text-text-faint">({column.dropped_by_rule.length} dropped by rule)</span>
                      )}
                    </span>
                  ))}
                />
                <Row
                  label="Diverted"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {column.totals.allocated_t_per_month} t/mo
                      {delta(column, 'allocated_t_per_month', (value) => `${value > 0 ? '+' : ''}${value} t`)}
                    </span>
                  ))}
                />
                <Row
                  label="Est. value"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {inr(column.totals.estimated_value_inr_per_month)}
                      {delta(column, 'estimated_value_inr_per_month', (value) => `${value > 0 ? '+' : '−'}${inr(Math.abs(value))}`)}
                    </span>
                  ))}
                />
                <Row
                  label="Est. CO₂e avoided"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {column.totals.estimated_co2e_avoided_t_per_month} t/mo
                      {delta(column, 'estimated_co2e_avoided_t_per_month', (value) => `${value > 0 ? '+' : ''}${value} t`)}
                    </span>
                  ))}
                />
                <Row
                  label="Freight burden"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {column.transport.transport_cost_inr_per_month === null
                        ? 'not priced'
                        : `${inr(column.transport.transport_cost_inr_per_month)}/mo`}
                      {delta(column, 'transport_cost_inr_per_month', (value) => `${value > 0 ? '+' : '−'}${inr(Math.abs(value))}`)}
                    </span>
                  ))}
                />
                <Row
                  label="Net potential"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {column.transport.net_economic_potential_inr_per_month === null
                        ? 'not priced'
                        : inr(column.transport.net_economic_potential_inr_per_month)}
                      {delta(
                        column,
                        'net_economic_potential_inr_per_month',
                        (value) => `${value > 0 ? '+' : '−'}${inr(Math.abs(value))}`,
                      )}
                    </span>
                  ))}
                />
                <Row
                  label="Viable routes"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge tone="teal">{column.transport.viable_routes} viable</StatusBadge>
                      <StatusBadge tone="amber">{column.transport.marginal_routes} marginal</StatusBadge>
                      <StatusBadge tone="cherry">{column.transport.impractical_routes} impractical</StatusBadge>
                    </span>
                  ))}
                />
                <Row
                  label="Worth shipping from"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="tabular-nums">
                      {column.viable_at_t_per_month
                        ? `${column.viable_at_t_per_month} t per load`
                        : 'no load size makes this pay here'}
                    </span>
                  ))}
                />
                <Row
                  label="Changes applied"
                  cells={data.configurations.map((column) => (
                    <span key={column.label} className="flex flex-wrap gap-1.5 text-[11px]">
                      {Object.entries(column.changed).map(([field, change]) => (
                        <span key={field} className="chip chip-amber">
                          {field}: {change.from} → {change.to}
                        </span>
                      ))}
                      {Object.entries(column.rules).map(([label, value]) => (
                        <span key={label} className="chip chip-slate">
                          {label}
                          {typeof value === 'boolean' ? '' : `: ${value}`}
                        </span>
                      ))}
                      {Object.keys(column.changed).length === 0 && Object.keys(column.rules).length === 0 && (
                        <span className="text-text-faint">none — this is the stored analysis</span>
                      )}
                    </span>
                  ))}
                />
              </tbody>
            </table>
          </div>

          {data.configurations.some((column) => column.warnings.length > 0) && (
            <ul className="space-y-1.5">
              {data.configurations
                .filter((column) => column.warnings.length > 0)
                .map((column) => (
                  <li key={column.label}>
                    {column.warnings.map((warning) => (
                      <Notice key={warning} tone="warn">
                        {column.label}: {warning}
                      </Notice>
                    ))}
                  </li>
                ))}
            </ul>
          )}

          <p className="text-[11px] leading-relaxed text-text-faint">{data.note}</p>
        </div>
      )}
    </Panel>
  );
}

function Row({ label, cells }: { label: string; cells: React.ReactNode[] }) {
  return (
    <tr className="border-t border-line align-top">
      <th scope="row" className="py-1.5 pr-3 text-left font-medium text-text-muted">
        {label}
      </th>
      {cells.map((cell, index) => (
        <td key={index} className="py-1.5 pr-3 text-text">
          {cell}
        </td>
      ))}
    </tr>
  );
}

function delta(column: ScenarioColumn, key: string, format: (value: number) => string) {
  const value = column.delta_vs_baseline?.[key];
  if (typeof value !== 'number' || value === 0) return null;
  return <span className="ml-1.5 text-[11px] tabular-nums text-accent">{format(value)}</span>;
}

function round(value: number) {
  return Math.round(value * 10) / 10;
}
