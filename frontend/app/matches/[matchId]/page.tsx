import Link from 'next/link';
import { notFound } from 'next/navigation';

import Assistant from '@/components/Assistant';
import IndustryProfile from '@/components/IndustryProfile';
import TransportPanel from '@/components/TransportPanel';
import { Bar, ConfidenceBar, Metric, Notice, OriginChip, Panel, ScoreRing } from '@/components/ui';
import { api } from '@/lib/api';
import { weightBarColor } from '@/lib/palette';
import {
  FLOW_STAGES,
  inr,
  REUSE_TYPE_LABEL,
  STAGE_LABEL,
  reuseTypeTone,
  SAFETY_LABEL,
  safetyTone,
  SOURCE_SECTOR_LABEL,
  titleCase,
  distanceShort,
  distanceFrom,
 } from '@/lib/format';
import type { Match } from '@/lib/types';

export const dynamic = 'force-dynamic';

/**
 * Labels for the engine's factor keys. Only the labels live here: the weights
 * themselves come from `weights_used` on the response, so this page can never
 * show a weighting the engine has changed.
 */
const WEIGHT_LABELS = {
  compatibility: 'Material compatibility',
  quantity: 'Quantity fit',
  location: 'Distance',
  sector: 'Sector fit',
  value: 'Economic value',
  environmental: 'Environmental benefit',
};

/**
 * §15 - one plain sentence saying what the safety layer allows on this route. The
 * words are chosen from the two fields the gate actually returns (`safety_level`
 * and `reuse_type`), never from a guess about the material.
 */
function safetyVerdict(match: Match): string {
  if (match.safety_level === 'hazardous') return 'Hazardous stream - licensed handler and manifest only';
  if (match.safety_level === 'high') return 'High-handling stream - controlled transport and documented disposal';
  if (match.reuse_type === 'REQUIRES_PROCESSING') {
    return 'Processing required before this material can be used - the route below assumes it has been processed';
  }
  if (match.reuse_type === 'INDUSTRIAL_ONLY') return 'Industrial offtake only - not suitable for small-scale or informal reuse';
  if (match.reuse_type === 'RESTRICTED') return 'Permitted routes only - approval needed before anything moves';
  return 'Usable as it stands, subject to the partner\'s intake conditions';
}

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

  const {
    match,
    analysis,
    weights_used: weightsUsed,
    provenance,
    transport,
    industry_profile: note,
  } = data as Awaited<ReturnType<typeof api.matchDetail>>;

  // §5/§7 - the full profile comes from its own route, the one the marketplace uses
  // too, so a recipient has exactly one profile in this app. The detail response
  // carries only the short explanation note above; it is deliberately not a second,
  // thinner copy of the same thing rendered differently.
  // `/api/profiles/{id}` answers for a recipient *or* a sector, so the shape is
  // narrowed here rather than assumed: `recipient_id` only exists on a partner's
  // profile. A sector id (or an unknown one) renders no panel instead of a wrong one.
  const profile = await api
    .profile(recipientId)
    .then((payload) => ('recipient_id' in payload ? payload : null))
    .catch(() => null);
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
      <section className="panel px-5 py-4.5 sm:px-6 sm:py-5">
        <p className="tag-label text-brand-strong">Recommended route</p>
        <div className="mt-2.5 flex flex-wrap items-start gap-5">
          <ScoreRing score={match.overall_score} size={92} />
          <div className="min-w-0 flex-1">
            <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.01em] text-text-strong">
              {analysis.material.name}
              <span aria-hidden className="mx-2 text-text-faint">→</span>
              <span className="text-text-strong">{match.recipient.company_name}</span>
            </h1>
            <p className="mt-1 text-[12.5px] text-text-muted">
              {titleCase(match.recipient.sector)} · {match.recipient.location} ·{' '}
              {distanceFrom(match.distance_km, analysis.source.location)}
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <span className={`chip ${reuseTypeTone(match.reuse_type)}`}>{REUSE_TYPE_LABEL[match.reuse_type]}</span>
            </div>
            {/* The one-sentence reason, worded from the same numbers as the
                breakdown below - generated in matching/engine.py, not here. */}
            <p className="mt-3.5 max-w-[72ch] border-t border-line pt-2.5 text-[12.5px] leading-relaxed text-text-muted">
              <span className="tag-label mr-2">Why this match</span>
              {match.summary}
            </p>
            {match.recipient.notes && (
              <p className="mt-3 text-xs leading-relaxed text-slate-500">{match.recipient.notes}</p>
            )}
          </div>
        </div>
      </section>

      {/* Impact */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3.5 border-y border-line py-4 sm:grid-cols-3 lg:grid-cols-6">
        <Metric
          label="Compatibility"
          value={`${match.overall_score.toFixed(1)}%`}
          hint="deterministic weighted sum"
          accent
        />
        <Metric
          label="Quantity"
          value={`${match.matched_quantity_t_per_month} t/mo`}
          hint={`of ${match.available_quantity_t_per_month} t/mo available`}
        />
        <Metric
          label="Distance"
          value={distanceShort(match.distance_km)}
          hint={`accepted range ${match.required_quantity_range_t_per_month[0]}–${match.required_quantity_range_t_per_month[1]} t/mo`}
        />
        <Metric label="Sector fit" value={titleCase(match.recipient.sector)} hint="of the source stream" />
        <Metric
          label="Est. value"
          value={`${inr(match.estimated_value_inr_per_month)}/mo`}
          hint="from recorded prices"
        />
        <Metric
          label="Est. CO₂e avoided"
          value={`${match.estimated_co2e_t_per_month} t/mo`}
          hint={`${(match.estimated_co2e_t_per_month * 12).toFixed(1)} t/year`}
          accent
        />
      </div>

      {/* §15 - what the safety layer allows on this route, and why, before the
          freight arithmetic or the reasoning. Cherry is used here and nowhere else on
          the page, so the gate reads as the gate. */}
      <section className="flex flex-wrap items-start gap-x-8 gap-y-3 rounded-card border border-line bg-surface px-5 py-4">
        <div className="min-w-0 flex-1">
          <p className="tag-label">Safety status</p>
          <p className="mt-1 text-[15px] font-semibold text-text-strong">
            {safetyVerdict(match)}
          </p>
          <p className="mt-1 max-w-[70ch] text-[12.5px] leading-relaxed text-text-muted">
            {SAFETY_LABEL[match.safety_level]} classification on the material record, applied by the rule-based layer
            before this route was ranked.
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2">
          <span className={`chip ${safetyTone(match.safety_level)} !px-2.5 !py-1 text-[12px]`}>
            {SAFETY_LABEL[match.safety_level]}
          </span>
          {match.cautions.slice(0, 2).map((caution) => (
            <p key={caution} className="max-w-[40ch] text-[11px] leading-snug text-text-faint">
              {caution}
            </p>
          ))}
        </div>
      </section>

      {note && !note.recorded_acceptance && (
        <Notice tone="warn">The partner has not recorded intake terms for this material, so its conditions must be agreed before a load moves.</Notice>
      )}

      {/* §8 - the freight picture for this load, before the reasons. */}
      {transport ? (
        <TransportPanel estimate={transport} />
      ) : (
        /* No coordinates on this stream, so there is no haul to price: the panel is
           replaced by the one sentence that is true, rather than a zero. */
        <p className="rounded-card border border-line bg-surface-inset px-4 py-3 text-[12.5px] leading-relaxed text-text-muted">
          Haulage is not estimated for this route, because the location it starts from has no coordinates. The
          distance and freight figures are left uncalculated rather than measured from another city.
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="space-y-5">
          {/* The reasons, in the engine's own words, with what it flagged. */}
          <Panel title="Why this match was recommended">
            <ul className="space-y-2">
              {match.reasons.map((reason, index) => (
                <li key={index} className="flex gap-2.5 text-[12.5px] leading-relaxed text-text-muted">
                  <span aria-hidden className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                  {reason}
                </li>
              ))}
            </ul>
            {match.cautions.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-line pt-3">
                {match.cautions.map((caution, index) => (
                  <p key={index} className="flex gap-2.5 text-[12.5px] leading-relaxed text-warning">
                    <span aria-hidden className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-fill" />
                    {caution}
                  </p>
                ))}
              </div>
            )}
          </Panel>

          {/* The same reasons, each tagged with where its number came from, so an
              estimate is never read as a measurement. */}
          <Panel
            title="Where each value comes from"
            action={<span className="caption">{provenance.length} values on this recommendation</span>}
          >
            <ul className="space-y-2">
              {provenance.map((row) => (
                <li key={row.field} className="rounded-md border border-ink-700 bg-ink-900 p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-medium text-slate-300">{row.field}</span>
                    <OriginChip origin={row.origin} label={row.origin_label} title={row.origin_note} />
                  </div>
                  <p className="mt-1 break-words text-xs tabular-nums text-slate-100">{row.value}</p>
                  <p className="caption mt-1">{row.detail}</p>
                </li>
              ))}
            </ul>
            <p className="caption mt-3">
              Calculated values come from the coordinates and quantities on this analysis. Estimates are computed from
              recorded prices and emission factors - they are not quotations, invoices or laboratory results, and
              knowledge-base records are not verified against a standard or regulation.
            </p>
          </Panel>

          {/* Score breakdown */}
          <Panel
            title="Score breakdown"
            action={<span className="caption">deterministic weighted sum</span>}
          >
            <div className="space-y-3">
              {Object.entries(weightsUsed).map(([key, weight]) => {
                const value = breakdown[key as keyof typeof WEIGHT_LABELS] ?? 0;
                const points = value * weight * 100;
                return (
                  <div key={key}>
                    <div className="mb-1 flex items-baseline justify-between gap-2">
                      <span className="text-xs text-slate-400">
                        {WEIGHT_LABELS[key as keyof typeof WEIGHT_LABELS] ?? titleCase(key)}
                        <span className="ml-1.5 text-slate-600">× {(weight * 100).toFixed(0)}%</span>
                      </span>
                      <span className="font-mono text-[11px] tabular-nums text-slate-300">
                        {value.toFixed(2)} → {points.toFixed(1)} pts
                      </span>
                    </div>
                    <Bar value={value} color={weightBarColor(points / (weight * 100))} />
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

          {/* Pathway: the five stages the engine recorded for this route */}
          <Panel
            title="Pathway"
            subtitle={`The ${match.reuse_pathway.steps.length} stages this route passes through, as the engine recorded them.`}
          >
            <ol className="space-y-0">
              {pathway.map((step, index) => (
                <li key={`${step}-${index}`} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span
                      className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                        index === 1 ? 'bg-accent' : 'bg-ink-600'
                      }`}
                    />
                    {index < pathway.length - 1 && <span className="w-px flex-1 bg-ink-700" />}
                  </div>
                  <div className="pb-3">
                    <p className="text-[10px] uppercase tracking-wider text-slate-600">
                      {STAGE_LABEL[FLOW_STAGES[index]] ?? `Step ${index + 1}`}
                    </p>
                    <p className={`text-xs ${index === 1 ? 'text-accent' : 'text-slate-300'}`}>{step}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="caption mt-1">
              The same rows the material flow on the overview page is built from. This route carries {match.matched_quantity_t_per_month} t/month on its own, of
              which {match.allocated_t_per_month} t/month is allocated once higher-ranked routes are filled from the
              same {match.available_quantity_t_per_month} t/month.
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
                note="recorded"
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

          {/* §5 / §7 - the receiver's own profile: what it makes, needs, can do and
              discards. Read from the recipient record and its sector template. */}
          {profile && <IndustryProfile profile={profile} />}

          <Assistant analysisId={analysis.id} matchId={match.id} />
        </div>
      </div>

      <Notice tone="info">
        Estimated impact. Value uses the higher of the recipient&#39;s recorded price and the material&#39;s reference
        price; CO₂e uses the knowledge-base avoidance factor of {analysis.totals.co2e_factor_used_t_per_tonne} t per
        tonne - figures for comparing options, not certified values.
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
