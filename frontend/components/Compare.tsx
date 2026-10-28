'use client';

/**
 * Side-by-side comparison (Feature 4).
 *
 * One table component, two column sets: the matches list compares partners and
 * the pathway panel compares routes. Both need the same thing - "which one wins
 * on this row" - so the winner is computed here from the same numbers the list
 * shows, never from a second opinion. Rows that cannot be compared (a sector
 * name) carry no `value` and get no highlight.
 */

import {
  inr,
  PROCESSING_BURDEN,
  REUSE_TYPE_LABEL,
  SAFETY_LABEL,
  reuseTypeTone,
  distanceShort,
 } from '@/lib/format';
import type { MatchCard, PathwayRow, ReuseType, SafetyLevel } from '@/lib/types';

export interface CompareColumn<T> {
  label: string;
  display: (row: T) => string;
  /** The number that decides the winner. Omit it for rows nothing ranks on. */
  value?: (row: T) => number;
  better?: 'high' | 'low';
  hint?: string;
}

/** Lowest first: 'low' risk beats 'hazardous'. Ordering, not a judgement. */
const SAFETY_ORDER: Record<SafetyLevel, number> = {
  low: 0,
  moderate: 1,
  high: 2,
  hazardous: 3,
  unknown: 4,
};

const reuseValue = (type: ReuseType) => PROCESSING_BURDEN[type] ?? 9;

export const MATCH_COLUMNS: CompareColumn<MatchCard>[] = [
  {
    label: 'Overall fit',
    display: (m) => `${m.score.toFixed(1)}%`,
    value: (m) => m.score,
    better: 'high',
    hint: 'weighted engine score',
  },
  {
    label: 'Quantity it takes',
    display: (m) => `${m.matched_quantity_t_per_month} t/mo`,
    value: (m) => m.matched_quantity_t_per_month,
    better: 'high',
    hint: 'what fits this route out of what you have',
  },
  {
    label: 'Quantity it needs',
    display: (m) => `${m.required_quantity_range_t_per_month[0]}–${m.required_quantity_range_t_per_month[1]} t/mo`,
    hint: 'the recipient’s own stated range',
  },
  {
    label: 'Distance',
    display: (m) => distanceShort(m.distance_km),
    // an unmeasured route sorts last, never first as if it were 0 km away
    value: (m) => m.distance_km ?? Number.MAX_SAFE_INTEGER,
    better: 'low',
  },
  {
    label: 'Processing',
    display: (m) => REUSE_TYPE_LABEL[m.reuse_type],
    value: (m) => reuseValue(m.reuse_type),
    better: 'low',
  },
  {
    label: 'Est. value',
    display: (m) => `${inr(m.estimated_value_inr_per_month)}/mo`,
    value: (m) => m.estimated_value_inr_per_month,
    better: 'high',
    hint: 'estimated: matched tonnes × recorded price',
  },
  {
    label: 'Est. CO₂e avoided',
    display: (m) => `${m.estimated_co2e_t_per_month} t/mo`,
    value: (m) => m.estimated_co2e_t_per_month,
    better: 'high',
    hint: 'estimated: matched tonnes × knowledge-base factor',
  },
  {
    label: 'Safety class',
    display: (m) => SAFETY_LABEL[m.safety_level],
    value: (m) => SAFETY_ORDER[m.safety_level],
    better: 'low',
  },
  { label: 'Partner type', display: (m) => m.partner_type_label },
  { label: 'Reuse sector', display: (m) => m.sector_label },
];

export const PATHWAY_COLUMNS: CompareColumn<PathwayRow>[] = [
  {
    label: 'Overall fit',
    display: (p) => `${p.score.toFixed(1)}%`,
    value: (p) => p.score,
    better: 'high',
  },
  {
    label: 'Processing',
    display: (p) => p.processing,
    value: (p) => reuseValue(p.reuse_type),
    better: 'low',
  },
  {
    label: 'Distance',
    display: (p) => distanceShort(p.distance_km),
    value: (p) => p.distance_km ?? Number.MAX_SAFE_INTEGER,
    better: 'low',
  },
  {
    label: 'Quantity routed',
    display: (p) => `${p.matched_quantity_t_per_month} t/mo`,
    value: (p) => p.matched_quantity_t_per_month,
    better: 'high',
  },
  {
    label: 'Est. value',
    display: (p) => `${inr(p.estimated_value_inr_per_month)}/mo`,
    value: (p) => p.estimated_value_inr_per_month,
    better: 'high',
    hint: 'estimated',
  },
  {
    label: 'Est. CO₂e avoided',
    display: (p) => `${p.estimated_co2e_t_per_month} t/mo`,
    value: (p) => p.estimated_co2e_t_per_month,
    better: 'high',
    hint: 'estimated',
  },
  {
    label: 'Safety class',
    display: (p) => SAFETY_LABEL[p.safety_level],
    value: (p) => SAFETY_ORDER[p.safety_level],
    better: 'low',
  },
  { label: 'Product', display: (p) => p.product },
  { label: 'Partner type', display: (p) => p.partner_type_label },
];

export function CompareTable<T>({
  rows,
  columns,
  titleOf,
  subOf,
  onRemove,
}: {
  rows: T[];
  columns: CompareColumn<T>[];
  titleOf: (row: T) => string;
  subOf: (row: T) => string;
  onRemove?: (index: number) => void;
}) {
  if (rows.length < 2) {
    return (
      <p className="text-xs leading-relaxed text-slate-500">
        Pick two or three {rows.length === 1 ? 'more ' : ''}items to compare them row by row. The strongest cell in
        each row is highlighted, using the same numbers the list already shows.
      </p>
    );
  }

  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-xs">
        <thead>
          <tr>
            <th className="w-36 px-1 pb-2 text-left align-bottom text-[10px] font-normal uppercase tracking-wider text-slate-600">
              {rows.length} selected
            </th>
            {rows.map((row, index) => (
              <th key={index} className="px-2 pb-2 text-left align-bottom">
                <span className="block font-semibold text-slate-100">{titleOf(row)}</span>
                <span className="mt-0.5 block font-normal text-[10px] text-slate-500">{subOf(row)}</span>
                {onRemove && (
                  <button
                    onClick={() => onRemove(index)}
                    className="mt-1 text-[10px] text-slate-600 underline hover:text-slate-300"
                  >
                    remove
                  </button>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {columns.map((column) => {
            const values = rows.map((row) => (column.value ? column.value(row) : null));
            const comparable = column.value && column.better ? values : [];
            let best: number | null = null;
            if (comparable.length) {
              const numbers = values.filter((v): v is number => v !== null);
              best = column.better === 'high' ? Math.max(...numbers) : Math.min(...numbers);
            }
            return (
              <tr key={column.label} className="border-t border-ink-700">
                <th scope="row" className="px-1 py-1.5 text-left align-top font-normal text-slate-500">
                  {column.label}
                  {column.hint && <span className="block text-[10px] text-slate-700">{column.hint}</span>}
                </th>
                {rows.map((row, index) => {
                  const win = best !== null && values[index] === best && new Set(values).size > 1;
                  return (
                    <td
                      key={index}
                      className={`px-2 py-1.5 align-top tabular-nums ${
                        win ? 'font-semibold text-accent' : 'text-slate-300'
                      }`}
                    >
                      {column.display(row)}
                      {win && <span className="ml-1 text-[9px] uppercase tracking-wider text-accent/70">best</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-600">
        Reuse type and safety class come from the same knowledge-base records the engine used; value and CO₂e are
        estimates. A route the safety layer refused never reaches this table at all.
      </p>
    </div>
  );
}

/** The chip set a compared item carries, shared by the two panels. */
export function ItemChips({ reuseType, safetyLevel }: { reuseType: ReuseType; safetyLevel: SafetyLevel }) {
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      <span className={`chip ${reuseTypeTone(reuseType)}`}>{REUSE_TYPE_LABEL[reuseType]}</span>
      <span className="chip border-ink-600 text-slate-400">{SAFETY_LABEL[safetyLevel]}</span>
    </span>
  );
}
