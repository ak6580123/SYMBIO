import { SectorBarChart, SourceStackedChart } from '@/components/Charts';
import { DemoTag, Empty, Metric, Notice, Panel } from '@/components/ui';
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

  const { totals } = data;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-100">Impact</h1>
          <p className="mt-1 text-sm text-slate-500">
            What the ranked routes would divert, earn and avoid — with the formulas in plain sight.
          </p>
        </div>
        <DemoTag label="Demo calculation" />
      </header>

      <Notice tone="warn">{data.disclaimer}</Notice>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Waste diverted"
          value={`${totals.tonnes_diverted} t/mo`}
          hint={`${(totals.diversion_rate * 100).toFixed(0)}% of ${totals.tonnes_analysed} t analyzed`}
          accent
        />
        <Metric
          label="Est. economic value"
          value={inr(totals.estimated_value_inr_per_month)}
          hint={`${inr(totals.estimated_value_inr_per_year)} per year`}
        />
        <Metric
          label="Est. CO₂e reduction"
          value={`${totals.estimated_co2e_t_per_month} t/mo`}
          hint={`${totals.estimated_co2e_t_per_year} t per year`}
          accent
        />
        <Metric label="Analyses" value={String(totals.analyses)} hint="streams processed this session" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Diversion by receiving sector" action={<span className="text-[11px] text-slate-500">t/month</span>}>
          {data.by_sector.length === 0 ? (
            <Empty title="No allocated routes yet" />
          ) : (
            <SectorBarChart
              data={data.by_sector.map((row) => ({ label: row.label, value: row.tonnes }))}
              dataKey="tonnes"
              unit="t/mo"
            />
          )}
        </Panel>

        <Panel title="Analysed vs diverted by source type">
          {data.by_source_type.length === 0 ? (
            <Empty title="No analyses yet" />
          ) : (
            <SourceStackedChart data={data.by_source_type} />
          )}
        </Panel>
      </div>

      <Panel title="Where the value goes" action={<span className="text-[11px] text-slate-500">estimated</span>}>
        {data.by_sector.length === 0 ? (
          <Empty title="No allocated routes yet" />
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

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Formulas" action={<span className="text-[11px] text-slate-500">in backend/matching/engine.py</span>}>
          <dl className="space-y-3">
            {Object.entries(data.formulae).map(([key, value]) => (
              <div key={key}>
                <dt className="font-mono text-[11px] text-accent">{key}</dt>
                <dd className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 border-t border-ink-700 pt-3 text-[11px] leading-relaxed text-slate-600">
            Swap the price and emission factors in{' '}
            <code className="font-mono text-slate-500">backend/knowledge_base/materials.py</code> for validated LCA
            values and every figure on this page updates — no other code changes.
          </p>
        </Panel>

        <Panel title="Factors used" action={<span className="text-[11px] text-slate-500">demo values</span>}>
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
