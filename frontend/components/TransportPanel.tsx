/**
 * §8 - what it costs to move the load.
 *
 * Two shapes of the same object: `TransportChip` is the one-line summary that sits on a
 * match card, `TransportPanel` is the working on the detail page. Both read the
 * `transport` block the backend attaches to the card - neither of them does arithmetic
 * on the score, and neither calls it a quote.
 */

import { EstimatedTag, MetricCard, Notice, StatusBadge, type Tone } from '@/components/ui';
import { inr, titleCase } from '@/lib/format';
import type { TransportEstimate } from '@/lib/types';

const STATUS_TONE: Record<string, Tone> = {
  viable: 'teal',
  marginal: 'amber',
  impractical: 'cherry',
  unknown: 'muted',
};

const STATUS_TITLE: Record<string, string> = {
  viable: 'Haulage stays well under the value of what it moves',
  marginal: 'Haulage eats a large share of the material value',
  impractical: 'Haulage costs more than the material is worth at this distance',
  unknown: 'Nothing to move, or no value recorded to compare against',
};

/** One line, for a list of matches. */
export function TransportChip({ estimate }: { estimate?: TransportEstimate | null }) {
  if (!estimate) return null;
  const tone = STATUS_TONE[estimate.status] ?? 'muted';
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-[11px] text-text-faint">
      <StatusBadge tone={tone} title={STATUS_TITLE[estimate.status]}>
        {estimate.status_label}
      </StatusBadge>
      <span className="tabular-nums">
        freight {inr(estimate.transport_cost_inr_per_month)}/mo · {inr(estimate.transport_cost_inr_per_tonne)}/t
      </span>
      <EstimatedTag />
    </span>
  );
}

/**
 * The road, as somebody else measured it.
 *
 * A routing provider's figure sits here and nowhere else: the freight cost above is
 * calculated on the straight line the engine scored, so a provider that disagrees moves
 * this sentence and not the recommendation. Where nothing could be routed, the line says
 * that instead of showing a number borrowed from another place.
 */
function RouteLine({ estimate }: { estimate: TransportEstimate }) {
  const route = estimate.route ?? null;
  if (!route) {
    return (
      <p className="text-xs leading-relaxed text-text-faint">
        <span className="font-medium text-text-muted">Distance unavailable.</span> The exact route could not be
        calculated from the provided location, so the distance above stays a straight line.
      </p>
    );
  }
  const difference = route.difference_percent;
  return (
    <div className="space-y-1">
      <p className="text-[12.5px] leading-relaxed text-text-muted">
        <span className="tabular-nums font-medium text-text">
          {route.distance_km.toLocaleString('en-IN', { maximumFractionDigits: 1 })} km
        </span>
        {route.duration_minutes !== null && route.duration_minutes !== undefined ? (
          <span className="tabular-nums"> · ~{Math.round(route.duration_minutes)} min</span>
        ) : null}
        <span className="text-text-faint"> · Route source: {titleCase(route.source)}</span>
        {difference !== null && difference !== undefined ? (
          <span className="tabular-nums text-text-faint">
            {' '}
            · {difference >= 0 ? '+' : ''}
            {difference.toFixed(0)}% against the straight line
          </span>
        ) : null}
      </p>
      <p className="text-[11px] leading-relaxed text-text-faint">
        {route.note}
        {route.fetched_at ? ` Fetched ${route.fetched_at.replace('T', ' ').slice(0, 16)}.` : ''}
      </p>
    </div>
  );
}

export default function TransportPanel({ estimate }: { estimate: TransportEstimate }) {
  const net = estimate.net_economic_potential_inr_per_month;
  return (
    <section className="panel panel-pad space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Transport</p>
          <h2 className="mt-1 text-sm font-semibold text-text-strong">Minimum viable shipment and freight burden</h2>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge tone={STATUS_TONE[estimate.status] ?? 'muted'} title={STATUS_TITLE[estimate.status]}>
            {estimate.status_label}
          </StatusBadge>
          <EstimatedTag />
        </div>
      </header>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Distance"
          value={`${estimate.distance_km.toLocaleString('en-IN', { maximumFractionDigits: 1 })} km`}
          hint={`${estimate.trips_per_month} trip${estimate.trips_per_month === 1 ? '' : 's'} per month`}
        />
        <MetricCard
          label="Moved per month"
          value={`${estimate.quantity_t_per_month.toLocaleString('en-IN', { maximumFractionDigits: 1 })} t`}
          hint={`${estimate.load_per_trip_t} t per load · ${estimate.truck_capacity_t} t truck`}
        />
        <MetricCard
          label="Freight cost"
          value={inr(estimate.transport_cost_inr_per_month)}
          hint={`${inr(estimate.transport_cost_inr_per_tonne)} per tonne`}
        />
        <MetricCard
          label="Net economic potential"
          value={inr(net)}
          tone={net > 0 ? 'success' : net < 0 ? 'danger' : 'default'}
          hint="material value minus the burden of moving it"
        />
      </div>

      <RouteLine estimate={estimate} />

      <div className="rounded-card border border-line bg-surface-inset px-3 py-2.5 text-xs leading-relaxed text-text-muted">
        <span className="font-medium text-text">When does this become worth shipping? </span>
        {estimate.minimum_viable_explanation}
      </div>

      <div>
        <p className="label mb-1.5">Burden against value</p>
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
          <span className="tabular-nums text-text-strong">
            {estimate.burden_to_value_ratio.toLocaleString('en-IN', { maximumFractionDigits: 2 })}×
          </span>
          <span className="text-text-faint">{estimate.ratio_basis}</span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
          <div
            className={`h-full rounded-full ${
              estimate.status === 'viable' ? 'bg-brand' : estimate.status === 'marginal' ? 'bg-accent-fill' : 'bg-cherry'
            }`}
            style={{ width: `${Math.min(100, estimate.burden_to_value_ratio * 100)}%` }}
          />
        </div>
        <p className="mt-1.5 text-[11px] leading-snug text-text-faint">
          The bar is freight cost as a share of material value. Under 35% is treated as viable, up to 100% as
          marginal, above it the haul costs more than the load.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="label mb-1.5">Cost per trip</p>
          <ul className="space-y-1 text-xs">
            {Object.entries(estimate.cost_breakdown).map(([key, value]) => (
              <li key={key} className="flex items-baseline justify-between gap-3 border-b border-line pb-1">
                <span className="text-text-muted">{humanise(key)}</span>
                <span className="tabular-nums text-text-strong">
                  {typeof value === 'number' ? (key.includes('hours') ? `${value} h` : inr(value)) : String(value)}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="label mb-1.5">Assumptions behind these numbers</p>
          <ul className="space-y-1 text-xs">
            {estimate.assumptions.map((row) => (
              <li key={row.key} className="border-b border-line pb-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 text-text-muted">{humanise(row.key)}</span>
                  <span className="shrink-0 tabular-nums text-text-strong">
                    {row.value.toLocaleString('en-IN')} {row.unit}
                  </span>
                </div>
                <p className="mt-0.5 text-[10px] leading-snug text-text-faint">{row.why}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <Notice tone="warn">{estimate.disclaimer}</Notice>
    </section>
  );
}

function humanise(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/^./, (c) => c.toUpperCase())
    .replace('Inr', '₹')
    .replace('Km', 'km')
    .replace('T', 't');
}
