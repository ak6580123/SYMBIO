import Link from 'next/link';

import { DemoTag, Panel } from '@/components/ui';
import { api } from '@/lib/api';
import { inr, pct } from '@/lib/format';
import type { DashboardData, HealthData } from '@/lib/types';

export const dynamic = 'force-dynamic';

const FLOW = [
  { step: '01', title: 'Waste source', body: 'Industry, household, SME, agriculture — any generator.' },
  { step: '02', title: 'AI identification', body: 'A local model reads the messy description and names the material.' },
  { step: '03', title: 'Material knowledge base', body: 'Properties, reuse routes, compatible sectors, hazards.' },
  { step: '04', title: 'Deterministic matching', body: 'Scores compatibility, quantity, distance, sector, value, impact.' },
  { step: '05', title: 'Ranked opportunities', body: 'Every match explains exactly why it was recommended.' },
  { step: '06', title: 'Circular flow', body: 'Economic value and avoided emissions, mapped end to end.' },
];

export default async function Home() {
  let dashboard: DashboardData | null = null;
  let health: HealthData | null = null;
  let error: string | null = null;

  try {
    [dashboard, health] = await Promise.all([api.dashboard(), api.health()]);
  } catch (err) {
    error = err instanceof Error ? err.message : 'Backend unreachable';
  }

  const impact = dashboard?.impact;
  const seeded = dashboard?.recent_analyses.find((a) => a.material === 'Fly Ash');

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="panel overflow-hidden">
        <div className="grid gap-8 p-8 lg:grid-cols-[1.15fr_1fr] lg:p-10">
          <div>
            <div className="mb-4 flex items-center gap-2">
              <DemoTag />
              <span className="chip border-ink-600 bg-ink-800 text-slate-400">Circular economy matchmaking</span>
            </div>
            <h1 className="text-3xl font-semibold leading-tight tracking-tight text-slate-50 sm:text-4xl">
              Your waste is somebody else&apos;s raw material.
              <span className="block text-slate-400">Symbio finds out who.</span>
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-relaxed text-slate-400">
              Describe a waste stream in plain language. Symbio identifies the material, looks it up in a knowledge
              base of reuse routes, and ranks the companies, recyclers, farms and community programmes that could
              actually use it — with an explainable score for every match.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link href="/analyze" className="btn-primary">
                Analyze Waste
              </Link>
              {seeded && (
                <Link href={`/matches/${seeded.top_match?.match_id ?? ''}`} className="btn-ghost">
                  See the fly ash demo
                </Link>
              )}
            </div>
            <p className="mt-4 text-[11px] text-slate-600">
              No account, no API keys. Runs entirely on local demo data.
            </p>
          </div>

          <div className="rounded-lg border border-ink-700 bg-ink-900 p-5">
            <p className="label mb-3">Live from the demo dataset</p>
            {error ? (
              <p className="text-xs leading-relaxed text-rose-300">
                {error}
                <br />
                <span className="text-slate-500">Start the FastAPI backend on port 8000 (see README).</span>
              </p>
            ) : (
              <dl className="grid grid-cols-2 gap-4">
                <Stat label="Materials known" value={String(health?.materials ?? '—')} />
                <Stat label="Potential recipients" value={String(health?.recipients ?? '—')} />
                <Stat label="Waste analyzed" value={`${impact?.tonnes_analysed ?? 0} t/mo`} />
                <Stat label="Potential diversion" value={`${impact?.tonnes_diverted ?? 0} t/mo`} accent />
                <Stat label="Potential matches" value={String(impact?.potential_matches ?? 0)} />
                <Stat label="Est. value" value={inr(impact?.estimated_value_inr_per_month ?? 0)} />
                <Stat label="Est. CO₂e avoided" value={`${impact?.estimated_co2e_t_per_month ?? 0} t/mo`} accent />
                <Stat label="Est. diversion rate" value={pct(impact?.diversion_rate ?? 0)} />
              </dl>
            )}
            <p className="mt-4 border-t border-ink-700 pt-3 text-[11px] leading-relaxed text-slate-600">
              Values are demo calculations from seeded factors, not certified figures.
            </p>
          </div>
        </div>
      </section>

      {/* Flow */}
      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-slate-200">How a match is made</h2>
          <span className="text-[11px] text-slate-600">The language model never sets a score</span>
        </div>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FLOW.map((item) => (
            <li key={item.step} className="panel panel-pad">
              <span className="font-mono text-[11px] text-accent">{item.step}</span>
              <p className="mt-1 text-sm font-medium text-slate-200">{item.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Scoring transparency */}
      <Panel
        title="The score, in full"
        action={<span className="text-[11px] text-slate-500">deterministic · auditable</span>}
      >
        <p className="mb-4 text-xs leading-relaxed text-slate-500">
          Every match score is a weighted sum of six components computed from the knowledge base and the source&apos;s
          quantity, location and sector. The same input always produces the same score.
        </p>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[
            ['Material compatibility', 30],
            ['Quantity fit', 20],
            ['Distance', 15],
            ['Sector fit', 15],
            ['Economic value', 10],
            ['Environmental benefit', 10],
          ].map(([label, weight]) => (
            <div key={String(label)} className="rounded-md border border-ink-700 bg-ink-900 p-3">
              <p className="text-lg font-semibold tabular-nums text-accent">{weight}%</p>
              <p className="mt-0.5 text-[11px] leading-tight text-slate-500">{label}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-ink-700 bg-ink-900 p-3">
            <p className="text-xs font-medium text-slate-300">What the model does</p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
              Reads your description, names the material, gives a confidence, suggests candidate reuse categories. Its
              output is validated against the knowledge base and can only narrow the options.
            </p>
          </div>
          <div className="rounded-md border border-ink-700 bg-ink-900 p-3">
            <p className="text-xs font-medium text-slate-300">What the model cannot do</p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
              Invent companies, prices, emission figures or safety verdicts. Hazardous and unidentified streams are
              blocked from household, farm and artisan routes by a rule-based safety layer.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function Stat({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className={`mt-0.5 text-lg font-semibold tabular-nums ${accent ? 'text-accent' : 'text-slate-100'}`}>
        {value}
      </dd>
    </div>
  );
}
