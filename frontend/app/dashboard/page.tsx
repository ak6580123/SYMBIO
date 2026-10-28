import Link from 'next/link';
import { CategoryBarChart } from '@/components/Charts';
import DemandHeatmap from '@/components/DemandHeatmap';
import FlowDiagram from '@/components/FlowDiagram';
import MaterialFlow from '@/components/MaterialFlow';
import RoleWorkflows from '@/components/Roles';
import { Empty, ErrorState, MetricStrip, PageHeader, Panel, ScoreRing, Section, SymbioButton } from '@/components/ui';
import { api } from '@/lib/api';
import {
  inr,
  relativeTime,
  SOURCE_SECTOR_LABEL,
  distanceShort,
 } from '@/lib/format';
import type { DashboardData, DemandResponse, ListingStats, MaterialFlowResponse } from '@/lib/types';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  let data: DashboardData | null = null;
  let error: string | null = null;
  try {
    data = await api.dashboard();
  } catch (err) {
    error = err instanceof Error ? err.message : 'Backend unreachable';
  }

  // §4 / §9 / §10 ride along on the same page. Each is fetched independently and
  // rendered only if it answered: a missing funnel should not blank the dashboard.
  let listings: ListingStats | null = null;
  let demand: DemandResponse | null = null;
  let flow: MaterialFlowResponse | null = null;
  try {
    [listings, demand, flow] = await Promise.all([
      api.listings({}).then((payload) => payload.stats),
      api.demand({ limit: 6 }),
      api.materialFlow(),
    ]);
  } catch {
    /* the sections below check for null */
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Overview" title="Network overview" />
        <ErrorState
          title="Something went wrong while loading the overview."
          hint={error ?? 'The figures on this page are read from the analysis service, which is not answering.'}
          retryHref="/dashboard"
        />
      </div>
    );
  }

  const impact = data.impact;

  const categoryData = data.waste_categories.map((category) => ({
    name: category.label.length > 22 ? `${category.label.slice(0, 20)}…` : category.label,
    tonnes: category.tonnes,
    value: category.value,
  }));

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Overview"
        title="Network overview"
        subtitle="What has been put into Symbio, what the network could take, and what actually found a route."
        actions={<SymbioButton href="/analyze">Analyze a material</SymbioButton>}
      />

      <MetricStrip
        items={[
          { label: 'Stream analysed', value: `${impact.tonnes_analysed} t/mo`, hint: `${impact.analyses} analyses` },
          {
            label: 'Diverted through a match',
            value: `${impact.tonnes_diverted} t/mo`,
            hint: `${(impact.diversion_rate * 100).toFixed(0)}% of analysed volume`,
            tone: 'success',
          },
          {
            label: 'Matches',
            value: String(impact.potential_matches),
            hint: `${impact.viable_matches} with allocated volume`,
          },
          {
            label: 'Est. economic value',
            value: `${inr(impact.estimated_value_inr_per_month)}/mo`,
            hint: 'from recorded prices',
          },
          {
            label: 'Est. CO₂e avoided',
            value: `${impact.estimated_co2e_t_per_month} t/mo`,
            hint: `${(impact.estimated_co2e_t_per_month * 12).toFixed(1)} t/year`,
            tone: 'accent',
          },
        ]}
      />

      {listings && demand && flow && (
        <RoleWorkflows impact={data.impact} stats={listings} demand={demand} flow={flow} />
      )}

      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        {/* Recent analyses */}
        <Section
          title="Analysed streams"
          subtitle={`${data.recent_analyses.length} most recent`}
          action={
            <Link href="/analyze" className="text-[11px] link">
              Analyze a material
            </Link>
          }
          divided
        >
          {data.recent_analyses.length === 0 ? (
            <Empty title="No material has been analysed yet" hint="Describe one stream and Symbio will rank who can take it." />
          ) : (
            <div className="-mx-4 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-xs">
                <thead>
                  <tr className="border-b border-ink-700 text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-4 py-2 font-medium">Material</th>
                    <th className="px-2 py-2 font-medium">Source</th>
                    <th className="px-2 py-2 text-right font-medium">Qty</th>
                    <th className="px-2 py-2 text-right font-medium">Diverted</th>
                    <th className="px-2 py-2 text-right font-medium">Est. value</th>
                    <th className="px-2 py-2 text-right font-medium">Matches</th>
                    <th className="px-4 py-2 text-right font-medium">Top match</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_analyses.map((row) => (
                    <tr key={row.id} className="border-b border-ink-800 last:border-0 hover:bg-ink-800/40">
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-200">{row.material}</span>

                        </div>
                        <span className="text-[10px] text-slate-600">
                          {(row.confidence * 100).toFixed(0)}% confidence · {relativeTime(row.created_at)}
                        </span>
                      </td>
                      <td className="px-2 py-2.5">
                        <span className="text-slate-400">{SOURCE_SECTOR_LABEL[row.source_type]}</span>
                        <span className="block text-[10px] text-slate-600">{row.location}</span>
                      </td>
                      <td className="px-2 py-2.5 text-right tabular-nums text-slate-300">
                        {row.quantity_t_per_month} t
                      </td>
                      <td className="px-2 py-2.5 text-right tabular-nums text-accent">
                        {row.allocated_t_per_month} t
                      </td>
                      <td className="px-2 py-2.5 text-right tabular-nums text-slate-300">
                        {inr(row.estimated_value_inr_per_month)}
                      </td>
                      <td className="px-2 py-2.5 text-right tabular-nums text-slate-400">{row.potential_matches}</td>
                      <td className="px-4 py-2.5 text-right">
                        {row.top_match ? (
                          <Link
                            href={`/matches/${row.top_match.match_id}`}
                            className="text-slate-300 hover:text-brand-strong"
                            title={row.top_match.company_name}
                          >
                            {row.top_match.score.toFixed(0)}% · {row.top_match.sector_label}
                          </Link>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* Circular flow */}
        <Panel title="Where the tonnage goes" subtitle="Each route, from the source that made it to the product it became.">
          <FlowDiagram rows={data.flow_rows} />
          <Link href="/map" className="btn-ghost mt-4 w-full text-xs">
            Open network map
          </Link>
        </Panel>
      </div>

      {flow && (
        <Section
          title="Material flow"
          subtitle="Every tonnage that entered Symbio, stage by stage to the one a partner took in."
          action={
            <span className="text-[11px] text-text-faint">
              {data.flow_rows.length} of {data.flow_routes_potential} routes carry tonnage
            </span>
          }
          divided
        >
          <MaterialFlow flow={flow} />
        </Section>
      )}

      {demand && (
        <Section
          title="Where demand is strongest"
          subtitle="Regional demand potential by area: the capacity that exists nearby, not a prediction about any one company."
          divided
        >
          <DemandHeatmap data={demand} />
        </Section>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        {/* Top matches */}
        <Section
          title="Strongest matches"
          action={
            <Link href="/matches" className="text-[11px] link">
              All matches
            </Link>
          }
          divided
        >
          {data.top_matches.length === 0 ? (
            <Empty title="No compatible demand found yet" hint="A match appears as soon as a stream and a partner line up." />
          ) : (
            <ul className="divide-y divide-line">
              {data.top_matches.map((match) => (
                <li key={match.id}>
                  <Link href={`/matches/${match.id}`} className="-mx-2 flex items-center gap-3 rounded-card px-2 py-2 hover:bg-surface-inset">
                    <ScoreRing score={match.score} size={48} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-slate-200">{match.company_name}</p>
                      <p className="truncate text-[10px] text-slate-500">
                        {match.material} → {match.sector_label} · {distanceShort(match.distance_km)}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[11px] tabular-nums text-text-strong">{inr(match.estimated_value_inr_per_month)}</p>
                      <p className="text-[10px] tabular-nums text-text-faint">
                        {match.estimated_co2e_t_per_month} t CO₂e
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* Categories */}
        <Section title="Material categories" subtitle="Tonnes per month, grouped by the category the knowledge base filed them in." divided>
          {categoryData.length === 0 ? (
            <Empty title="No categories yet" hint="Categories appear once a stream has been identified." />
          ) : (
            <CategoryBarChart data={categoryData} />
          )}
        </Section>
      </div>

      {/* Impact summary */}
      <Section
        title="What it added up to"
        subtitle={impact.label}
        divided
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <ImpactRow
            label="Volume diverted"
            value={`${impact.tonnes_diverted} t/mo`}
            ratio={impact.diversion_rate}
            caption={`${(impact.diversion_rate * 100).toFixed(0)}% of analyzed waste has at least one viable route`}
          />
          <ImpactRow
            label="Economic value"
            value={inr(impact.estimated_value_inr_per_month)}
            ratio={Math.min(1, impact.estimated_value_inr_per_month / 50000)}
            caption={`${inr(impact.estimated_value_inr_per_month * 12)} per year if every route ran`}
          />
          <ImpactRow
            label="CO₂e avoided"
            value={`${impact.estimated_co2e_t_per_month} t/mo`}
            ratio={Math.min(1, impact.estimated_co2e_t_per_month / 5)}
            caption={`${(impact.estimated_co2e_t_per_month * 12).toFixed(1)} t per year`}
          />
          <ImpactRow
            label="Route coverage"
            value={`${impact.viable_matches}/${impact.potential_matches}`}
            ratio={impact.potential_matches ? impact.viable_matches / impact.potential_matches : 0}
            caption="matches with allocated volume vs total opportunities"
          />
        </div>
        <p className="caption mt-1">
          Every figure above is computed from the recorded price and emission factor it names - an estimate for
          comparing options, not a certified value.{' '}
          <Link href="/impact" className="link">
            See the formulas
          </Link>
          .
        </p>
      </Section>

      {/* Quick action */}
      <section className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
        <div>
          <p className="text-[15px] font-semibold text-text-strong">Another stream to look at?</p>
          <p className="mt-0.5 text-[12.5px] text-text-muted">
            Industrial, household, SME or agricultural residue - the same pipeline, the same rules.
          </p>
        </div>
        <div className="flex gap-2">
          <SymbioButton href="/analyze">Analyze a material</SymbioButton>
          <SymbioButton href="/knowledge-base" variant="ghost">
            Browse materials
          </SymbioButton>
        </div>
      </section>
    </div>
  );
}

function ImpactRow({
  label,
  value,
  ratio,
  caption,
}: {
  label: string;
  value: string;
  ratio: number;
  caption: string;
}) {
  return (
    <div className="rounded-md border border-ink-700 bg-ink-900 p-3">
      <p className="label">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-100">{value}</p>
      <div className="mt-2">
        <div className="h-1 w-full overflow-hidden rounded-full bg-ink-700">
          <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, ratio * 100)}%` }} />
        </div>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-600">{caption}</p>
    </div>
  );
}
