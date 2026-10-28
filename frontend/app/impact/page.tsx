import { SectorBarChart, SourceStackedChart } from '@/components/Charts';
import { Empty, MetricStrip, Notice, PageHeader, Panel, Section, SymbioButton } from '@/components/ui';
import { api } from '@/lib/api';
import { inr } from '@/lib/format';
import type { ImpactData } from '@/lib/types';

export const dynamic = 'force-dynamic';

export default async function ImpactPage() {
  let data: ImpactData | null = null;
  let error: string | null = null;
  try {
    data = await api.impact();
  } catch (err) {
    error = err instanceof Error ? err.message : 'Backend unreachable';
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold tracking-tight text-slate-100">Impact</h1>
        <Notice tone="danger">{error}</Notice>
      </div>
    );
  }

  const { totals, circularity, processing_pathways: pathways } = data;
  const components: [string, string, number][] = [
    ['diversion_rate', 'Diverted', circularity.components.diversion_rate],
    ['direct_reuse_share', 'Direct reuse', circularity.components.direct_reuse_share],
    ['confidence', 'Confidence', circularity.components.mean_identification_confidence],
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Impact"
        title="What the routes add up to"
        subtitle="What the ranked matches would divert, earn and avoid, with the formula behind every figure stated underneath it."
      />

      <Notice tone="warn">{data.disclaimer}</Notice>

      <MetricStrip
        items={[
          {
            label: 'Waste diverted',
            value: `${totals.tonnes_diverted} t/mo`,
            hint: `${(totals.diversion_rate * 100).toFixed(0)}% of ${totals.tonnes_analysed} t analysed`,
            tone: 'success',
          },
          {
            label: 'Est. economic value',
            value: `${inr(totals.estimated_value_inr_per_month)}/mo`,
            hint: `${inr(totals.estimated_value_inr_per_year)} per year`,
          },
          {
            label: 'Est. CO₂e avoided',
            value: `${totals.estimated_co2e_t_per_month} t/mo`,
            hint: `${totals.estimated_co2e_t_per_year} t per year`,
            tone: 'accent',
          },
          { label: 'Analyses', value: String(totals.analyses), hint: 'streams processed in this session' },
        ]}
      />

      <dl className="-mt-1 flex flex-wrap items-baseline gap-x-7 gap-y-1.5 text-[11.5px] text-text-faint">
        <span>
          Partners taking something{' '}
          <span className="tabular-nums text-text-muted">
            {totals.reuse_partners} across {totals.routes} scored routes
          </span>
        </span>
        <span>
          Reuse volume, all routes{' '}
          <span className="tabular-nums text-text-muted">
            {totals.potential_reuse_t_per_month} t/mo
            <span title="Partner appetite in total. It is not added to the diverted figure above, because one stream cannot be taken twice.">†</span>
          </span>
        </span>
        <span>
          Usable without processing <span className="tabular-nums text-text-muted">{(totals.direct_reuse_share * 100).toFixed(0)}%</span>
        </span>
        <span>
          Identification confidence{' '}
          <span className="tabular-nums text-text-muted">{(totals.mean_identification_confidence * 100).toFixed(0)}%</span>
        </span>
      </dl>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Diversion by receiving sector" subtitle="Tonnes per month, by the sector that takes the material.">
          {data.by_sector.length === 0 ? (
            <Empty title="No allocated routes yet" hint="An allocation appears once a stream has been matched to a partner and accepted." />
          ) : (
            <SectorBarChart
              data={data.by_sector.map((row) => ({ label: row.label, value: row.tonnes }))}
              dataKey="tonnes"
              unit="t/mo"
            />
          )}
        </Section>

        <Section title="Analysed vs diverted by source type" subtitle="Not every analysis finds a route; this is where the volume stops.">
          {data.by_source_type.length === 0 ? (
            <Empty title="No analyses yet" hint="Describe a stream and this page fills in." action={<SymbioButton href="/analyze" variant="primary" size="sm">Analyze a material</SymbioButton>} />
          ) : (
            <SourceStackedChart data={data.by_source_type} />
          )}
        </Section>
      </div>

      <Panel title="Where the value goes" action={<span className="caption">estimated</span>}>
        {data.by_sector.length === 0 ? (
          <Empty title="No allocated routes yet" hint="An allocation appears once a stream has been matched to a partner and accepted." />
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead>
                <tr className="border-b border-ink-700 text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-2 font-medium">Sector</th>
                  <th className="px-2 py-2 text-right font-medium">Routes</th>
                  <th className="px-2 py-2 text-right font-medium">Tonnes/mo</th>
                  <th className="px-2 py-2 text-right font-medium">Est. value/mo</th>
                  <th className="px-4 py-2 text-right font-medium">Est. CO₂e/mo</th>
                </tr>
              </thead>
              <tbody>
                {data.by_sector.map((row) => (
                  <tr key={row.sector} className="border-b border-ink-800 last:border-0">
                    <td className="px-4 py-2 text-slate-300">{row.label}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-slate-500">{row.routes}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-slate-300">{row.tonnes}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-accent">{inr(row.value)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-300">{row.co2e} t</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        {/* Optional gamification: one composite number, shown with its formula. */}
        <Panel
          title="Circularity score"
          action={<span className="caption">optional · composite of the figures above</span>}
        >
          <div className="flex flex-wrap items-center gap-5">
            <div className="text-4xl font-semibold tabular-nums text-accent">{circularity.score.toFixed(1)}</div>
            <div className="min-w-[180px] flex-1 space-y-1">
              {components.map(([key, text, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-[104px] shrink-0 text-[10px] uppercase tracking-wider text-slate-600">{text}</span>
                  <span className="h-1.5 flex-1 rounded-full bg-ink-700">
                    <span className="block h-1.5 rounded-full bg-accent/70" style={{ width: `${value * 100}%` }} />
                  </span>
                  <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-slate-400">
                    {(value * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>

          <p className="mt-3 font-mono text-[10px] leading-relaxed text-slate-600">{circularity.formula}</p>

          <ul className="mt-3 space-y-1.5">
            {circularity.bands.map((band) => {
              const earned = circularity.score >= band.min;
              return (
                <li
                  key={band.label}
                  className={`flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-[11px] ${
                    earned ? 'border-accent/30 bg-accent/5 text-slate-300' : 'border-ink-700 text-slate-600'
                  }`}
                >
                  <span className={earned ? 'text-accent' : 'text-slate-700'}>{earned ? '✓' : '○'}</span>
                  <span>
                    <span className="font-medium">{band.label}</span>
                    <span className="text-slate-500"> · from {band.min.toFixed(0)}</span>
                    <span className="block text-[10px] leading-relaxed text-slate-600">{band.rule}</span>
                  </span>
                </li>
              );
            })}
          </ul>

          <p className="mt-3 border-t border-ink-700 pt-2 text-[11px] leading-relaxed text-slate-500">
            {circularity.current ? (
              <>
                Current band: <span className="text-slate-300">{circularity.current.label}</span>.{' '}
              </>
            ) : null}
            {circularity.next ? (
              <>
                Next is <span className="text-slate-300">{circularity.next.label}</span> — {circularity.next.rule}.
              </>
            ) : (
              'Every band here is already earned by the measured data.'
            )}
          </p>
          <p className="mt-2 text-[10px] leading-relaxed text-slate-600">{circularity.note}</p>
          <p className="mt-1 text-[10px] leading-relaxed text-slate-600">{circularity.weight_of_demo_estimate}</p>
        </Panel>

        <Panel title="Processing pathways" action={<span className="caption">routes per capability</span>}>
          {pathways.length === 0 ? (
            <Empty title="No allocated routes yet" hint="An allocation appears once a stream has been matched to a partner and accepted." />
          ) : (
            <ul className="space-y-1.5">
              {pathways.map((row) => (
                <li key={row.capability} className="flex items-center gap-3 text-[11px]">
                  <span className="w-28 shrink-0 truncate text-slate-400">{row.capability}</span>
                  <span className="h-2 flex-1 rounded-full bg-ink-700">
                    <span
                      className="block h-2 rounded-full bg-sky-400/70"
                      style={{ width: `${(row.routes / pathways[0].routes) * 100}%` }}
                    />
                  </span>
                  <span className="w-6 shrink-0 text-right tabular-nums text-slate-300">{row.routes}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
            Counted from the recipients the matches actually point at, so this is the equipment a matched network
            already has — what a route needs beyond it is stated per match under “Processing required”.
          </p>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Formulas" subtitle="Stated exactly as the engine applies them, so any figure on this page can be reproduced by hand.">
          <dl className="space-y-3">
            {Object.entries(data.formulae).map(([key, value]) => (
              <div key={key}>
                <dt className="font-mono text-[11px] text-accent">{key}</dt>
                <dd className="mt-0.5 text-[11px] leading-relaxed text-text-muted">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="caption mt-4 border-t border-line pt-3">
            Every figure comes from the reference values in the knowledge base below. Replacing them with validated
            life-cycle factors changes the numbers on this page and nothing else about how they are combined.
          </p>
        </Panel>

        <Panel title="Factors used" subtitle="Recorded reference values in the knowledge base - replace them with validated factors before any real use.">
          <div className="max-h-72 overflow-y-auto pr-1">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-ink-850">
                <tr className="border-b border-ink-700 text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="py-1.5 font-medium">Material</th>
                  <th className="py-1.5 text-right font-medium">t CO₂e/t</th>
                  <th className="py-1.5 text-right font-medium">₹/tonne</th>
                </tr>
              </thead>
              <tbody>
                {data.factors_used.map((factor) => (
                  <tr key={factor.material} className="border-b border-ink-800 last:border-0">
                    <td className="py-1.5 text-slate-400">{factor.material}</td>
                    <td className="py-1.5 text-right tabular-nums text-slate-300">
                      {factor.co2e_avoided_t_per_tonne.toFixed(2)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums text-slate-500">
                      {inr(factor.typical_price_inr_per_tonne)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
