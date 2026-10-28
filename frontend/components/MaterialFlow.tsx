/**
 * §9 / §12 - the material flow.
 *
 * This is the page's centrepiece, so it is drawn as one figure rather than six
 * panels: each stage is a bar whose width is the tonnage that survived to that
 * point, the drop between two stages is written where it happens, and the routes
 * that make up the last bar sit underneath as the evidence.
 *
 * Each bar is a subset of the one above it - that is the whole point of the
 * diagram - so a stage that the network could absorb but nobody actually took is
 * shown capped, and the tonnage a partner *could* take is printed separately from
 * the tonnage that was placed.
 */

import Link from 'next/link';

import { Notice, StatusBadge, type Tone } from '@/components/ui';
import { inr } from '@/lib/format';
import { AMBER_STRONG, BRAND, TEAL_STRONG } from '@/lib/palette';
import type { MaterialFlowResponse } from '@/lib/types';

const TRANSPORT_TONE: Record<string, Tone> = {
  viable: 'teal',
  marginal: 'amber',
  impractical: 'cherry',
  unknown: 'muted',
};

const tonnes = (value: number) => value.toLocaleString('en-IN', { maximumFractionDigits: 2 });

export default function MaterialFlow({ flow }: { flow: MaterialFlowResponse }) {
  if (!flow.stages.length || flow.stages[0].tonnes_per_month === 0) {
    return (
      <Notice tone="info">
        {flow.note ?? 'No material has been analysed yet, so there is no flow to draw. The first analysis fills this in.'}
      </Notice>
    );
  }

  const generated = flow.stages[0].tonnes_per_month;
  const widest = Math.max(...flow.stages.map((stage) => stage.apparent_tonnes_per_month), generated);
  /** Tonnage lost between a stage and the next one, keyed by the stage it left. */
  const dropAfter = new Map((flow.drops ?? []).map((drop) => [drop.from, drop]));

  return (
    <div className="space-y-7">
      <ol className="space-y-0">
        {flow.stages.map((stage, index) => {
          const width = widest > 0 ? (stage.apparent_tonnes_per_month / widest) * 100 : 0;
          const share = generated > 0 ? stage.tonnes_per_month / generated : 0;
          const last = index === flow.stages.length - 1;
          const drop = dropAfter.get(stage.stage);
          const lost = drop && drop.lost_tonnes_per_month > 0 ? drop : null;
          return (
            <li key={stage.stage}>
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4">
                <p className="text-[14px] font-semibold leading-snug text-text-strong">
                  <span className="mr-2 text-[11px] font-normal tabular-nums text-text-faint">{index + 1}</span>
                  {stage.stage}
                </p>
                <p className="text-right text-[13px] tabular-nums text-text">
                  {tonnes(stage.tonnes_per_month)} t/mo
                  <span className="ml-2 text-[11px] text-text-faint">{(share * 100).toFixed(0)}%</span>
                </p>
              </div>

              <div className="mt-1.5 flex items-center gap-2">
                <div className="h-6 flex-1 overflow-hidden rounded-sm bg-surface-inset">
                  <div
                    className="h-full rounded-sm"
                    style={{
                      width: `${Math.max(5, width)}%`,
                      background: last ? AMBER_STRONG : index === 0 ? TEAL_STRONG : BRAND.teal,
                    }}
                    title={stage.definition}
                  />
                </div>
                {stage.capped_by_previous_stage && (
                  <span className="shrink-0 text-[11px] leading-tight text-warning" title={stage.definition}>
                    capped at {tonnes(stage.apparent_tonnes_per_month)} t of appetite
                  </span>
                )}
              </div>

              <p className="mt-1 max-w-[86ch] text-[11.5px] leading-relaxed text-text-faint">{stage.definition}</p>
              {stage.caveat && <p className="mt-0.5 text-[11.5px] leading-relaxed text-warning">{stage.caveat}</p>}

              {lost ? (
                <p className="my-2.5 flex items-baseline gap-2 border-l-2 border-accent-fill pl-2.5 text-[11.5px] leading-snug text-text-muted">
                  <span aria-hidden className="text-text-faint">↓</span>
                  <span className="tabular-nums font-medium text-text-strong">−{tonnes(lost.lost_tonnes_per_month)} t/mo</span>
                  <span>lost before {lost.to.toLowerCase()}</span>
                </p>
              ) : (
                index < flow.stages.length - 1 && (
                  <p aria-hidden className="my-2 border-l-2 border-transparent pl-2.5 text-[11.5px] text-text-faint">
                    ↓
                  </p>
                )
              )}
            </li>
          );
        })}
      </ol>

      {/* The four numbers a reader checks the funnel against - inline, on hairlines,
          because they are captions on the figure above, not objects of their own. */}
      <dl className="grid gap-x-8 gap-y-4 border-y border-line py-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="label">Recovery</dt>
          <dd className="stat mt-1">{(flow.recovery_percent ?? 0).toFixed(1)}%</dd>
          <dd className="caption mt-0.5">processed as a share of what was generated</dd>
        </div>
        <div>
          <dt className="label">Into a named product</dt>
          <dd className="stat mt-1">{(flow.reused_percent ?? 0).toFixed(1)}%</dd>
          <dd className="caption mt-0.5">{flow.reused_note ?? 'the last stage counts a named product only'}</dd>
        </div>
        <div>
          <dt className="label">Largest loss</dt>
          <dd className="stat mt-1">
            {flow.biggest_loss ? `${tonnes(flow.biggest_loss.lost_tonnes_per_month)} t` : '0 t'}
          </dd>
          <dd className="caption mt-0.5">
            {flow.biggest_loss
              ? `${flow.biggest_loss.from} → ${flow.biggest_loss.to}`
              : 'no tonnage is lost between the stages in this network'}
          </dd>
        </div>
        <div>
          <dt className="label">Partner appetite</dt>
          <dd className="stat mt-1">{tonnes(flow.partner_appetite_t_per_month ?? 0)} t</dd>
          <dd className="caption mt-0.5">{flow.partner_appetite_note?.split('.')[0] ?? 'what partners said they could take'}</dd>
        </div>
      </dl>

      <div>
        <p className="label mb-2">Routes · source → processor → recipient → product</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-[11.5px]">
            <thead>
              <tr className="border-b border-line-strong text-left text-text-faint">
                <th scope="col" className="py-1.5 pr-2 font-medium">Source</th>
                <th scope="col" className="py-1.5 pr-2 font-medium">Material</th>
                <th scope="col" className="py-1.5 pr-2 font-medium">Processor</th>
                <th scope="col" className="py-1.5 pr-2 font-medium">Recipient</th>
                <th scope="col" className="py-1.5 pr-2 font-medium">Product</th>
                <th scope="col" className="py-1.5 pr-2 text-right font-medium">t/mo</th>
                <th scope="col" className="py-1.5 pr-2 text-right font-medium">Value</th>
                <th scope="col" className="py-1.5 pr-2 text-right font-medium">Freight</th>
                <th scope="col" className="py-1.5 text-right font-medium">Haul</th>
              </tr>
            </thead>
            <tbody>
              {flow.routes.map((route) => (
                <tr key={route.match_id} className="border-b border-line align-top">
                  <td className="py-2 pr-2 text-text-muted">{route.source}</td>
                  <td className="py-2 pr-2 text-text">{route.material}</td>
                  <td className="py-2 pr-2 text-text-muted">{route.processor}</td>
                  <td className="py-2 pr-2">
                    <Link
                      href={`/matches/${encodeURIComponent(`${route.analysis_id}:${route.recipient_id}`)}`}
                      className="link"
                    >
                      {route.recipient}
                    </Link>
                  </td>
                  <td className="py-2 pr-2 text-text-muted">
                    {route.product === 'Assessed Material' ? (
                      <span
                        className="text-text-faint"
                        title="No application is recorded for this sector, so none is claimed here."
                      >
                        Assessed Material
                      </span>
                    ) : (
                      route.product
                    )}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums text-text-strong">{route.tonnes_per_month}</td>
                  <td className="py-2 pr-2 text-right tabular-nums text-text-muted">
                    {inr(route.value_inr_per_month)}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums text-text-muted">
                    {route.transport_cost_inr_per_month === null ? 'not priced' : inr(route.transport_cost_inr_per_month)}
                  </td>
                  <td className="py-2 text-right">
                    <StatusBadge tone={TRANSPORT_TONE[route.transport_status] ?? 'muted'}>
                      {route.transport_status === 'unavailable' ? 'no coordinates' : route.transport_status}
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="caption mt-2">
          {(flow.route_count ?? 0) > flow.routes.length && (
            <>
              Showing the {flow.routes.length} largest of {flow.route_count} routes.{' '}
            </>
          )}
          {flow.impact_dashboard
            ? `These stages reconcile with the impact dashboard: ${String(flow.impact_dashboard.note)}`
            : 'Value and freight are computed from the recorded factors on each route.'}{' '}
          <Link href="/impact" className="link">
            See the formulas
          </Link>
          .
        </p>
      </div>

      {flow.blocked_streams && flow.blocked_streams.length > 0 && (
        <Notice tone="warn">
          <span className="font-medium">Streams with no route: </span>
          {flow.blocked_streams
            .map((row) => `${row.material} (${row.tonnes_per_month} t/mo) — ${row.reason}`)
            .join('; ')}
        </Notice>
      )}

      {flow.generated_note && <p className="caption">{flow.generated_note}</p>}
    </div>
  );
}
