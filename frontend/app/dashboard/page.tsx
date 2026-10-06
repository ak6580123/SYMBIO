import Link from 'next/link';
import { CategoryBarChart } from '@/components/Charts';
import FlowDiagram, { type FlowLink } from '@/components/FlowDiagram';
import { DemoTag, Empty, Metric, Notice, Panel, ScoreRing } from '@/components/ui';
import { api } from '@/lib/api';
import { inr, relativeTime, SOURCE_SECTOR_LABEL } from '@/lib/format';
import type { DashboardData } from '@/lib/types';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  let data: DashboardData | null = null;
  let error: string | null = null;
  try {
    data = await api.dashboard();
  } catch (err) {
    error = err instanceof Error ? err.message : 'Backend unreachable';
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold tracking-tight text-slate-100">Dashboard</h1>
        <Notice tone="danger">
          {error}
          <br />
          <span className="text-slate-400">Start the FastAPI backend on port 8000, then reload.</span>
        </Notice>
      </div>
    );
  }

  const impact = data.impact;

  // Build the flow ribbons from the per-analysis allocated routes.
  const flowLinks: FlowLink[] = [];
  for (const analysis of data.recent_analyses) {
    if (!analysis.top_match || analysis.allocated_t_per_month <= 0) continue;
    flowLinks.push({
      material: analysis.material,
      sector: analysis.top_match.sector,
      tonnes: analysis.allocated_t_per_month,
    });
  }

  const categoryData = data.waste_categories.map((category) => ({
    name: category.label.length > 22 ? `${category.label.slice(0, 20)}…` : category.label,
    tonnes: category.tonnes,
    value: category.value,
  }));

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-100">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Everything Symbio has analyzed in this session, and what it found.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DemoTag />
          <Link href="/analyze" className="btn-primary">
            Analyze New Waste
          </Link>
        </div>
      </header>

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="Total waste analyzed" value={`${impact.tonnes_analysed} t/mo`} hint={`${impact.analyses} analyses`} />
        <Metric
          label="Potential waste diverted"
          value={`${impact.tonnes_diverted} t/mo`}
          hint={`${(impact.diversion_rate * 100).toFixed(0)}% of analyzed volume`}
          accent
        />
        <Metric label="Potential matches" value={String(impact.potential_matches)} hint={`${impact.viable_matches} with allocated volume`} />
        <Metric label="Est. economic value" value={inr(impact.estimated_value_inr_per_month)} hint="per month · demo" />
        <Metric
          label="Est. CO₂e reduction"
          value={`${impact.estimated_co2e_t_per_month} t/mo`}
          hint={`${(impact.estimated_co2e_t_per_month * 12).toFixed(1)} t/year · demo`}
          accent
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        {/* Recent analyses */}
        <Panel
          title="Recent waste analyses"
          action={
            <span className="text-[11px] text-slate-500">{data.recent_analyses.length} most recent</span>
          }
        >
          {data.recent_analyses.length === 0 ? (
            <Empty title="No analyses yet" hint="Run your first analysis to populate the dashboard." />
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
                          {row.seeded && (
                            <span className="chip border-ink-600 bg-ink-800 text-[9px] text-slate-500">seeded</span>
                          )}
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
                            className="text-slate-300 hover:text-accent"
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
        </Panel>

        {/* Circular flow */}
        <Panel title="Circular flow" action={<span className="text-[11px] text-slate-500">allocated tonnes</span>}>
          <FlowDiagram links={flowLinks} />
          <Link href="/map" className="btn-ghost mt-4 w-full text-xs">
            Open network map
          </Link>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        {/* Top matches */}
        <Panel
          title="Top matches"
          action={
            <Link href="/matches" className="text-[11px] text-accent hover:underline">
              all matches
            </Link>
          }
        >
          {data.top_matches.length === 0 ? (
            <Empty title="No matches yet" />
          ) : (
            <ul className="space-y-2">
              {data.top_matches.map((match) => (
                <li key={match.id}>
                  <Link
                    href={`/matches/${match.id}`}
                    className="flex items-center gap-3 rounded-md border border-ink-700 bg-ink-900 p-2.5 transition-colors hover:border-ink-600"
                  >
                    <ScoreRing score={match.score} size={48} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-slate-200">{match.company_name}</p>
                      <p className="truncate text-[10px] text-slate-500">
                        {match.material} → {match.sector_label} · {match.distance_km} km
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[11px] tabular-nums text-accent">
                        {inr(match.estimated_value_inr_per_month)}
                      </p>
                      <p className="text-[10px] tabular-nums text-slate-600">
                        {match.estimated_co2e_t_per_month} t CO₂e
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Categories */}
        <Panel title="Waste categories" action={<span className="text-[11px] text-slate-500">tonnes / month</span>}>
          {categoryData.length === 0 ? (
            <Empty title="No categories yet" />
          ) : (
            <CategoryBarChart data={categoryData} />
          )}
        </Panel>
      </div>

      {/* Impact summary */}
      <Panel title="Impact summary" action={<span className="text-[11px] text-slate-500">{impact.label}</span>}>
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
        <p className="mt-4 border-t border-ink-700 pt-3 text-[11px] leading-relaxed text-slate-600">
          Estimated impact — demo calculation. Figures come from the seeded price and emission factors in the
          knowledge base and are not certified values.{' '}
          <Link href="/impact" className="text-accent hover:underline">
            See the formulas
          </Link>
          .
        </p>
      </Panel>

      {/* Quick action */}
      <section className="panel flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <p className="text-sm font-medium text-slate-200">Have another stream to test?</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Industry, household, SME or agricultural residue — the same pipeline handles all of them.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/analyze" className="btn-primary">
            Analyze New Waste
          </Link>
          <Link href="/knowledge-base" className="btn-ghost">
            Browse materials
          </Link>
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
