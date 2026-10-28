/**
 * §10 - regional demand potential.
 *
 * Answers one question: where is demand strongest? A ranked list of areas carrying the
 * four components that produced the index, and a plot of where those areas sit. The
 * index is a share of the strongest area in the network, which is said next to it,
 * because "68" alone reads like a probability and is not one.
 */

import { Notice, StatusBadge, type Tone } from '@/components/ui';
import { inr } from '@/lib/format';
import { AMBER_STRONG, BRAND, SLATE_DEEP, TEAL_STRONG } from '@/lib/palette';
import type { DemandArea, DemandResponse } from '@/lib/types';

const BAND_TONE: Record<string, Tone> = { High: 'teal', Medium: 'amber', Low: 'muted' };
const BAND_COLOR: Record<string, string> = { High: TEAL_STRONG, Medium: AMBER_STRONG, Low: BRAND.slate };

const COMPONENT_LABEL: Record<string, string> = {
  intake_headroom: 'unfilled intake capacity',
  partner_breadth: 'partners and sectors present',
  open_listings: 'open demand listings',
  unserved_supply: 'nearby supply with nowhere to go',
};

export default function DemandHeatmap({ data }: { data: DemandResponse }) {
  const areas = data.areas;
  if (!areas.length) {
    return (
      <Notice tone="info">
        {data.error ?? 'No area in this selection has recorded intake capacity for this material.'}
      </Notice>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1.5">
        <p className="text-[12.5px] text-text-muted">
          Areas within {data.radius_km} km of their own partners. The index is each area&#39;s share of the strongest
          area in the network.
        </p>
        <StatusBadge tone="muted">Demand potential · not a forecast</StatusBadge>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <ol className="divide-y divide-line">
          {areas.map((area, index) => (
            <AreaRow key={area.area} area={area} index={index} />
          ))}
        </ol>
        <div className="space-y-4">
          <AreaPlot areas={areas} />
          <p className="caption">{data.method}</p>
        </div>
      </div>

      <p className="max-w-[92ch] text-[11.5px] leading-relaxed text-text-faint">
        {data.caveat} {data.not_a_forecast}
      </p>
    </div>
  );
}

function AreaRow({ area, index }: { area: DemandArea; index: number }) {
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[13.5px] font-semibold text-text-strong">
          <span className="mr-1.5 tabular-nums text-text-faint">{index + 1}</span>
          {area.area}
        </p>
        <div className="flex items-center gap-2 text-[11px]">
          <StatusBadge tone={BAND_TONE[area.band]}>{area.band} potential</StatusBadge>
          <span className="tabular-nums text-text-muted">
            {area.demand_potential_index.toFixed(1)} / 100
          </span>
        </div>
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
        <div
          className="h-full rounded-full"
          style={{ width: `${area.demand_potential_index}%`, background: BAND_COLOR[area.band] }}
        />
      </div>

      <div className="mt-1.5 grid gap-x-3 gap-y-0.5 text-[11px] text-text-faint sm:grid-cols-2">
        {Object.entries(area.components).map(([key, value]) => (
          <p key={key} className="flex items-baseline justify-between gap-2">
            <span>{COMPONENT_LABEL[key] ?? key.replace(/_/g, ' ')}</span>
            <span className="tabular-nums text-text-muted">{(value * 100).toFixed(0)}%</span>
          </p>
        ))}
      </div>

      <p className="mt-1.5 text-[11px] tabular-nums leading-snug text-text-muted">
        {area.intake_headroom_t_per_month.toLocaleString('en-IN', { maximumFractionDigits: 0 })} t/mo of unfilled
        intake across {area.partner_count} partner{area.partner_count === 1 ? '' : 's'} in {area.sector_count} sector
        {area.sector_count === 1 ? '' : 's'} · {area.open_demand_listings} open listing
        {area.open_demand_listings === 1 ? '' : 's'} ({area.open_demand_tonnes_per_month} t/mo) ·{' '}
        {area.nearby_unplaced_supply_t_per_month} t/mo of supply nearby with no route
      </p>

      <ul className="mt-1.5 space-y-1">
        {area.drivers.map((driver) => (
          <li key={driver} className="text-[11px] leading-snug text-text-faint">
            · {driver}
          </li>
        ))}
      </ul>

      <ul className="mt-1.5 flex flex-wrap gap-1.5">
        {area.top_materials.map((material) => (
          <li key={material.material_id} className="chip chip-teal" title={`${material.headroom_t_per_month} t/mo of headroom here`}>
            {material.name}
          </li>
        ))}
      </ul>

      <details className="mt-1.5">
        <summary className="cursor-pointer text-[11px] text-text-faint hover:text-text-muted">
          Partners in this area ({area.partners.length})
        </summary>
        <ul className="mt-1 space-y-1">
          {area.partners.map((partner) => (
            <li key={partner.id} className="flex flex-wrap items-baseline justify-between gap-2 text-[11px]">
              <span className="text-text-muted">{partner.company_name}</span>
              <span className="tabular-nums text-text-faint">
                can still take {partner.headroom_t_per_month.toLocaleString('en-IN', { maximumFractionDigits: 0 })} t/mo
                · {inr(partner.price_inr_per_tonne)}/t
              </span>
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}

/**
 * The same areas placed by their own coordinates. No map tiles, no invented
 * boundaries: a circle per area, sized by index, coloured by band.
 */
function AreaPlot({ areas }: { areas: DemandArea[] }) {
  const lats = areas.map((area) => area.latitude);
  const lons = areas.map((area) => area.longitude);
  const [minLat, maxLat] = [Math.min(...lats), Math.max(...lats)];
  const [minLon, maxLon] = [Math.min(...lons), Math.max(...lons)];
  const spanLat = Math.max(0.01, maxLat - minLat);
  const spanLon = Math.max(0.01, maxLon - minLon);
  const pad = 12;
  const width = 240;
  const height = 200;

  const project = (area: DemandArea) => ({
    x: pad + ((area.longitude - minLon) / spanLon) * (width - pad * 2),
    y: height - pad - ((area.latitude - minLat) / spanLat) * (height - pad * 2),
  });

  return (
    <figure className="rounded-card border border-line bg-surface-inset p-3">
      <figcaption className="label mb-1.5">Where these areas sit</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Areas by coordinates">
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke={SLATE_DEEP} strokeWidth="0.6" />
        <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke={SLATE_DEEP} strokeWidth="0.6" />
        {areas.map((area) => {
          const { x, y } = project(area);
          const radius = 4 + (area.demand_potential_index / 100) * 9;
          return (
            <g key={area.area}>
              <circle
                cx={x}
                cy={y}
                r={radius}
                fill={BAND_COLOR[area.band]}
                fillOpacity={0.28}
                stroke={BAND_COLOR[area.band]}
                strokeWidth="1"
              >
                <title>{`${area.area} · index ${area.demand_potential_index.toFixed(1)} · ${area.intake_headroom_t_per_month} t/mo headroom`}</title>
              </circle>
              <text x={x} y={y - radius - 2} textAnchor="middle" fontSize="7" fill={SLATE_DEEP}>
                {area.area}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-1.5 text-[11px] leading-snug text-text-faint">
        Circle size is the index, colour is the band. Positions are each area&apos;s own partner centroid; nothing here
        is a boundary, a heat surface or a per-square-kilometre rate.
      </p>
    </figure>
  );
}
