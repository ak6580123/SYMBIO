import Link from 'next/link';
import { notFound } from 'next/navigation';

import Assistant from '@/components/Assistant';
import { Bar, ConfidenceBar, DemoTag, Metric, Notice, Panel, ScoreRing } from '@/components/ui';
import { api } from '@/lib/api';
import {
  inr,
  REUSE_TYPE_LABEL,
  reuseTypeTone,
  SAFETY_LABEL,
  safetyTone,
  SOURCE_SECTOR_LABEL,
  titleCase,
} from '@/lib/format';

export const dynamic = 'force-dynamic';

const COMPONENTS: { key: keyof typeof WEIGHT_LABELS; weight: number }[] = [
  { key: 'compatibility', weight: 30 },
  { key: 'quantity', weight: 20 },
  { key: 'location', weight: 15 },
  { key: 'sector', weight: 15 },
  { key: 'value', weight: 10 },
  { key: 'environmental', weight: 10 },
];

const WEIGHT_LABELS = {
  compatibility: 'Material compatibility',
  quantity: 'Quantity fit',
  location: 'Distance',
  sector: 'Sector fit',
  value: 'Economic value',
  environmental: 'Environmental benefit',
};

export default async function MatchDetailPage({ params }: { params: { matchId: string } }) {
  // Match ids are "analysisId:recipientId" — see backend/matching/engine.py.
  // Next.js hands over the raw segment, so ":" arrives percent-encoded as %3A.
  // Decode before splitting, or the separator is never found.
  let matchId = params.matchId;
  try {
    matchId = decodeURIComponent(matchId);
  } catch {
    /* leave as-is if it is not valid percent-encoding */
  }

  const separator = matchId.indexOf(':');
  if (separator < 0) notFound();
  const analysisId = matchId.slice(0, separator);
  const recipientId = matchId.slice(separator + 1);
  if (!analysisId || !recipientId) notFound();

  let data;
  try {
    data = await api.matchDetail(analysisId, recipientId);
  } catch {
    notFound();
  }

  const { match, analysis } = data as Awaited<ReturnType<typeof api.matchDetail>>;
  const breakdown = match.breakdown;
  const pathway = match.reuse_pathway.steps;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-[11px] text-slate-600">
        <Link href="/matches" className="hover:text-slate-400">
          ← Matches
        </Link>
        <span>/</span>
        <span className="font-mono">{match.id}</span>
      </div>

      {/* Header */}
      <section className="panel p-5">
        <div className="flex flex-wrap items-start gap-5">
          <ScoreRing score={match.overall_score} size={84} />
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold tracking-tight text-slate-100">{match.recipient.company_name}</h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {titleCase(match.recipient.sector)} · {match.recipient.location} · {match.distance_km} km from source
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className={`chip ${reuseTypeTone(match.reuse_type)}`}>{REUSE_TYPE_LABEL[match.reuse_type]}</span>
              <span className={`chip ${safetyTone(match.safety_level)}`}>{SAFETY_LABEL[match.safety_level]}</span>
              <DemoTag />
            </div>
            {match.recipient.notes && (
              <p className="mt-3 text-xs leading-relaxed text-slate-500">{match.recipient.notes}</p>
            )}
          </div>
        </div>
      </section>

      {/* Impact */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Matched quantity"
          value={`${match.matched_quantity_t_per_month} t/mo`}
          hint={`of ${match.available_quantity_t_per_month} t/mo available`}
          accent
        />
        <Metric
          label="Recipient range"
          value={`${match.required_quantity_range_t_per_month[0]}–${match.required_quantity_range_t_per_month[1]} t/mo`}
          hint="minimum – maximum accepted"
        />
        <Metric
          label="Est. economic value"
          value={inr(match.estimated_value_inr_per_month)}
          hint="per month · demo calculation"
        />
        <Metric
          label="Est. CO₂e avoided"
          value={`${match.estimated_co2e_t_per_month} t/mo`}
          hint={`${(match.estimated_co2e_t_per_month * 12).toFixed(1)} t/year · demo`}
          accent
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="space-y-5">
          {/* Why */}
          <Panel title="Why this match was recommended">
            <ul className="space-y-2">
              {match.reasons.map((reason, index) => (
                <li key={index} className="flex gap-2.5 text-xs leading-relaxed text-slate-300">
                  <span className="mt-0.5 shrink-0 text-accent">✓</span>
                  {reason}
                </li>
              ))}
            </ul>
            {match.cautions.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-ink-700 pt-3">
                {match.cautions.map((caution, index) => (
                  <p key={index} className="flex gap-2.5 text-xs leading-relaxed text-amber-200/90">
                    <span className="mt-0.5 shrink-0">!</span>
                    {caution}
                  </p>
                ))}
              </div>
            )}
          </Panel>

          {/* Score breakdown */}
          <Panel
            title="Score breakdown"
            action={<span className="text-[11px] text-slate-500">deterministic weighted sum</span>}
          >
            <div className="space-y-3">
              {COMPONENTS.map(({ key, weight }) => {
                const value = breakdown[key];
                const points = value * weight;
                return (
                  <div key={key}>
                    <div className="mb-1 flex items-baseline justify-between gap-2">
                      <span className="text-xs text-slate-400">
                        {WEIGHT_LABELS[key]}
                        <span className="ml-1.5 text-slate-600">× {weight}%</span>
                      </span>
                      <span className="font-mono text-[11px] tabular-nums text-slate-300">
                        {value.toFixed(2)} → {points.toFixed(1)} pts
                      </span>
                    </div>
                    <Bar value={value} color={points >= weight * 0.75 ? '#34D399' : points >= weight * 0.5 ? '#A3E635' : '#FCD34D'} />
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-ink-700 pt-3">
              <span className="text-xs text-slate-400">
                Overall ({(breakdown.weighted_total * 100).toFixed(2)}% before rounding)
              </span>
              <span className="text-lg font-semibold tabular-nums text-accent">
                {match.overall_score.toFixed(1)}%
              </span>
            </div>
          </Panel>

          {/* Pathway */}
          <Panel title="Reuse pathway">
            <ol className="flex flex-wrap items-center gap-2">
              {pathway.map((step, index) => (
                <li key={`${step}-${index}`} className="flex items-center gap-2">
                  <span
                    className={`rounded-md border px-2.5 py-1.5 text-[11px] ${
                      index === 1
                        ? 'border-accent/40 bg-accent/10 text-accent'
                        : 'border-ink-600 bg-ink-900 text-slate-300'
                    }`}
                  >
                    {step}
                  </span>
                  {index < pathway.length - 1 && <span className="text-slate-600">→</span>}
                </li>
              ))}
            </ol>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
              Source sector, identified material, handling requirement, receiving sector and the product it becomes.
            </p>
          </Panel>
        </div>

        <div className="space-y-5">
          {/* Source material */}
          <Panel title="Source material">
            <p className="text-sm font-medium text-slate-200">{analysis.material.name}</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">{analysis.material.description}</p>

            <div className="mt-3 flex items-center gap-2">
              <span className="label">Confidence</span>
              <ConfidenceBar confidence={analysis.identification.confidence} />
              <span className="font-mono text-[10px] text-slate-600">{analysis.identification.engine}</span>
            </div>

            <dl className="mt-3 space-y-1.5 text-[11px]">
              <Row label="Source" value={SOURCE_SECTOR_LABEL[analysis.source.source_type]} />
              <Row label="Location" value={analysis.source.location} />
              <Row label="Quantity" value={`${analysis.source.quantity_t_per_month} t/month`} />
              <Row label="Category" value={titleCase(analysis.material.category)} />
              <Row label="Safety level" value={SAFETY_LABEL[analysis.material.safety_level]} />
            </dl>

            {Object.keys(analysis.identification.composition).length > 0 && (
              <div className="mt-3">
                <p className="label mb-1.5">Composition</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(analysis.identification.composition).map(([key, value]) => (
                    <span key={key} className="chip border-ink-600 bg-ink-800 font-mono text-slate-400">
                      {key.toUpperCase()} {value}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Panel>

          {/* Recipient */}
          <Panel title="Recipient">
            <dl className="space-y-1.5 text-[11px]">
              <Row label="Company" value={match.recipient.company_name} />
              <Row label="Sector" value={titleCase(match.recipient.sector)} />
              <Row label="Location" value={match.recipient.location} />
              <Row
                label="Accepts"
                value={`${match.recipient.min_quantity_t_per_month}–${match.recipient.max_quantity_t_per_month} t/month`}
              />
              <Row
                label="Est. price"
                value={`${inr(match.recipient.estimated_price_inr_per_tonne)}/tonne`}
                note="demo"
              />
            </dl>
            <div className="mt-3">
              <p className="label mb-1.5">Processing capability</p>
              <div className="flex flex-wrap gap-1.5">
                {match.recipient.processing_capability.map((cap) => (
                  <span key={cap} className="chip border-ink-600 bg-ink-800 text-slate-400">
                    {titleCase(cap)}
                  </span>
                ))}
              </div>
            </div>
            <Link
              href={`/map?analysis=${analysis.id}`}
              className="btn-ghost mt-4 w-full text-xs"
            >
              View on map
            </Link>
          </Panel>

          <Assistant analysisId={analysis.id} matchId={match.id} />
        </div>
      </div>

      <Notice tone="info">
        Estimated impact — demo calculation. Value uses max(recipient price, material reference price); CO₂e uses the
        knowledge-base avoidance factor of {analysis.totals.co2e_factor_used_t_per_tonne} t per tonne. These are
        illustrative figures, not certified values.
      </Notice>
    </div>
  );
}

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-slate-600">{label}</dt>
      <dd className="truncate text-right text-slate-300">
        {value}
        {note && <span className="ml-1 text-slate-600">({note})</span>}
      </dd>
    </div>
  );
}
