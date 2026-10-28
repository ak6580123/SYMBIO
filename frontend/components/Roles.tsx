/**
 * §4 - three roles, one platform.
 *
 * Not three apps and not three marketing columns: every number in here is read from the
 * same responses the rest of the site uses, and each "what you do here" line is a route
 * that exists in this build. The roles differ in what they are shown first, which is the
 * only honest difference a session without accounts can offer.
 */

import Link from 'next/link';

import { Panel, StatusBadge } from '@/components/ui';
import { inr } from '@/lib/format';
import type { DashboardData, DemandResponse, ListingStats, MaterialFlowResponse } from '@/lib/types';

interface RoleProps {
  impact: DashboardData['impact'];
  stats: ListingStats;
  demand: DemandResponse;
  flow: MaterialFlowResponse;
}

export default function RoleWorkflows(props: RoleProps) {
  const { impact, stats, demand, flow } = props;
  const topArea = demand.areas[0];
  const blocked = flow.blocked_streams?.length ?? 0;
  const unplaced = (flow.stages[0]?.tonnes_per_month ?? 0) - (flow.stages[4]?.tonnes_per_month ?? 0);

  const roles = [
    {
      id: 'source',
      name: 'Source generator',
      line: 'A plant, yard or site that has something to get rid of',
      numbers: [
        { label: 'Stated here', value: `${impact.tonnes_analysed} t/mo`, hint: `${impact.analyses} analyses in this session` },
        { label: 'Supply listings', value: String(stats.supply), hint: `${stats.session_published} published this session` },
      ],
      does: [
        { href: '/analyze', label: 'Describe a stream', note: 'material, quantity, place, condition' },
        { href: '/marketplace', label: 'Publish a supply listing', note: 'validated against the knowledge base' },
        { href: '/matches', label: 'Read the match reasons', note: 'score, provenance, transport' },
      ],
      sees: 'Completeness of their own input first, then the routes that take it.',
    },
    {
      id: 'receiver',
      name: 'Industry receiver',
      line: 'A processor, plant or handler that can take material in',
      numbers: [
        { label: 'Demand listings', value: String(stats.demand), hint: 'what partners stated they can take' },
        topArea
          ? {
              label: `Strongest area · ${topArea.area}`,
              value: `${topArea.intake_headroom_t_per_month.toLocaleString('en-IN', { maximumFractionDigits: 0 })} t/mo`,
              hint: `index ${topArea.demand_potential_index.toFixed(1)} of 100`,
            }
          : { label: 'Strongest area', value: '—', hint: 'no recorded capacity for this selection' },
      ],
      does: [
        { href: '/marketplace', label: 'Publish a demand listing', note: 'quantity, window, offer price' },
        { href: '/knowledge-base', label: 'Check a material', note: 'properties, handling, safety' },
        { href: '/dashboard', label: 'Regional demand potential', note: 'capacity by area, not prediction' },
      ],
      sees: 'Their intake window and headroom, then which open streams fit inside it.',
    },
    {
      id: 'coordinator',
      name: 'Network coordinator',
      line: 'An agency or cluster operator looking across the whole network',
      numbers: [
        { label: 'Routes in flow', value: String(flow.route_count ?? 0), hint: `${flow.partner_count ?? 0} partners involved` },
        {
          label: 'Diversion',
          value: `${(impact.diversion_rate * 100).toFixed(0)}%`,
          hint: unplaced > 0 ? `${Math.round(unplaced * 10) / 10} t/mo with no route` : 'every stated tonnage has a route',
        },
      ],
      does: [
        { href: '/map', label: 'Geography and gaps', note: 'same filters as the matches list' },
        { href: '/impact', label: 'Portfolio and pathways', note: 'per-material roll-ups' },
        { href: '/knowledge-base', label: 'Sector profiles', note: 'what each industry discards and needs' },
      ],
      sees: 'Where the network loses tonnage, and which refusal or distance caused it.',
    },
  ];

  return (
    <section className="space-y-3">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="eyebrow">One platform, three jobs</p>
          <h2 className="mt-1 text-lg font-semibold text-text-strong">What each role opens on</h2>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-text-faint">
          <StatusBadge tone="muted">shared data, no separate apps</StatusBadge>
          {blocked > 0 && <StatusBadge tone="cherry">{blocked} stream{blocked === 1 ? '' : 's'} with no route</StatusBadge>}
        </div>
      </header>

      <div className="grid gap-3 lg:grid-cols-3">
        {roles.map((role) => (
          <Panel key={role.id} title={role.name} subtitle={role.line}>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                {role.numbers.map((number) => (
                  <div key={number.label} className="rounded-card border border-line bg-surface-inset px-2.5 py-2">
                    <p className="label">{number.label}</p>
                    <p className="mt-0.5 text-sm tabular-nums text-text-strong">{number.value}</p>
                    <p className="mt-0.5 text-[11px] leading-snug text-text-faint">{number.hint}</p>
                  </div>
                ))}
              </div>

              <div>
                <p className="label mb-1.5">What you do here</p>
                <ul className="space-y-1">
                  {role.does.map((entry) => (
                    <li key={entry.href + entry.label} className="flex items-baseline justify-between gap-2 text-xs">
                      <Link href={entry.href} className="link">
                        {entry.label}
                      </Link>
                      <span className="text-right text-[11px] text-text-faint">{entry.note}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-[11px] leading-relaxed text-text-muted">{role.sees}</p>
            </div>
          </Panel>
        ))}
      </div>

      <p className="text-[11px] leading-relaxed text-text-faint">
        Value figures across all three views are the same estimates the analysis produces ({inr(
          impact.estimated_value_inr_per_month
        )} per month in total) — they are not quotes, contracts or measured flows.
      </p>
    </section>
  );
}
