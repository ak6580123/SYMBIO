import Link from 'next/link';

import { SymbioButton, Section } from '@/components/ui';
import { api } from '@/lib/api';
import { inr, pct, distanceShort } from '@/lib/format';

export const dynamic = 'force-dynamic';

/**
 * The homepage has one job: say what Symbio does in one line, show that it is
 * working on real material, and hand the reader to the analyzer. The pipeline and
 * the scoring model are here too, because a reader deciding whether to trust a
 * match should be able to see how it was made without opening four pages - but
 * they are set as prose and a table, not as a wall of feature cards.
 */
export default async function Home() {
  let streams: Awaited<ReturnType<typeof api.dashboard>>['recent_analyses'] = [];
  let impact: Awaited<ReturnType<typeof api.dashboard>>['impact'] | null = null;
  let materials = 0;
  let partners = 0;
  let offline = false;

  try {
    const [dashboard, health] = await Promise.all([api.dashboard(), api.health()]);
    streams = dashboard.recent_analyses;
    impact = dashboard.impact;
    materials = health.materials;
    partners = health.recipients;
  } catch {
    // The homepage must still render and still offer the way in, so the failure is
    // reported once, plainly, and the analysis service is not described to the user.
    offline = true;
  }

  return (
    <div className="space-y-section">
      <Hero streams={streams} offline={offline} />

      <Facts materials={materials} partners={partners} impact={impact} offline={offline} />

      <Section title="How a match is made" subtitle="Four steps, and only one of them is a model.">
        <ol className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Describe the stream', 'What it is, how much, how often, where. Plain language or an upload.'],
            ['Identify the material', 'A local model names it against the knowledge base, and you can correct it.'],
            ['Match it to the network', 'A deterministic engine scores compatibility, quantity, distance, value and impact.'],
            ['Read the reason', 'Every match shows the arithmetic, the freight burden and what the safety layer allowed.'],
          ].map(([title, body], index) => (
            <li key={title} className="border-t border-line pt-2.5">
              <p className="tag-label">Step {index + 1}</p>
              <p className="mt-1 text-[14px] font-semibold leading-snug text-text-strong">{title}</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-text-muted">{body}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Scoring />

      {offline && (
        <p className="text-[12.5px] leading-relaxed text-text-faint">
          The figures above need the analysis service, which is not answering right now. Everything else on this page
          still describes how the product works.
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function Hero({
  streams,
  offline,
}: {
  streams: Awaited<ReturnType<typeof api.dashboard>>['recent_analyses'];
  offline: boolean;
}) {
  const shown = streams.slice(0, 3);
  return (
    <section className="grid items-center gap-10 py-4 lg:grid-cols-[1.05fr_1fr] lg:py-8">
      <div>
        <p className="text-[13px] font-semibold uppercase tracking-[0.42em] text-brand-strong">Symbio</p>
        <h1 className="mt-4 max-w-[18ch] text-[38px] font-semibold leading-[1.04] tracking-[-0.02em] text-text-strong sm:text-[52px]">
          Find the next best use for your material.
        </h1>
        <p className="page-subtitle mt-5 text-[15px]">
          Describe a waste stream once. Symbio identifies the material, ranks who can actually take it, and shows the
          distance, the freight burden and the reasoning behind every line.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <SymbioButton variant="hero" href="/analyze">
            Analyze a material
          </SymbioButton>
          <Link href="/map" className="btn-ghost btn-lg">
            Explore the network
          </Link>
        </div>
      </div>

      {/* The product, drawn once: a stream on the left, what Symbio did to it in the
          middle, the next use on the right. The rows are live records - if nothing
          has been analysed, the visual says so rather than showing a stock example. */}
      <div className="rounded-card border border-line bg-surface px-5 py-5">
        <div className="flex items-baseline justify-between gap-3">
          <p className="tag-label">Waste</p>
          <p className="tag-label text-center">Symbio</p>
          <p className="tag-label text-right">Next use</p>
        </div>

        {shown.length === 0 ? (
          <p className="py-8 text-center text-[12.5px] leading-relaxed text-text-faint">
            {offline
              ? 'The analysis service is not answering, so there is nothing to show yet.'
              : 'No material stream has been analysed yet. The first one appears here.'}
          </p>
        ) : (
          <ul className="mt-3 space-y-2.5">
            {shown.map((stream) => (
              <li key={stream.id} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-t border-line pt-2.5">
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-text-strong">{stream.material}</span>
                  <span className="block text-[11px] tabular-nums text-text-faint">
                    {stream.quantity_t_per_month} t/mo · {stream.location}
                  </span>
                </span>
                <span aria-hidden className="px-1 text-[13px] text-brand-strong">
                  →
                </span>
                <span className="min-w-0 text-right">
                  {stream.top_match ? (
                    <>
                      <Link
                        href={`/matches/${stream.top_match.match_id}`}
                        className="block truncate text-[13px] font-medium text-text-strong hover:underline"
                      >
                        {stream.top_match.company_name}
                      </Link>
                      <span className="block text-[11px] tabular-nums text-text-faint">
                        {stream.top_match.score.toFixed(0)} match · {distanceShort(stream.top_match.distance_km)}
                      </span>
                    </>
                  ) : (
                    <span className="text-[11px] leading-snug text-text-faint">
                      No partner can take this stream as it stands.
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}

        <p className="mt-4 border-t border-line pt-3 text-[11px] leading-relaxed text-text-faint">
          {shown.length > 0 && (
            <>
              {streams.length} stream{streams.length === 1 ? '' : 's'} in the network right now.{' '}
            </>
          )}
          Scores are computed by the matching engine; the model identifies the material and never ranks a partner.
        </p>
      </div>
    </section>
  );
}

/** One row of the numbers that describe the network. Not cards - a row. */
function Facts({
  materials,
  partners,
  impact,
  offline,
}: {
  materials: number;
  partners: number;
  impact: Awaited<ReturnType<typeof api.dashboard>>['impact'] | null;
  offline: boolean;
}) {
  const items: [string, string][] = [
    ['Materials known', offline ? '—' : String(materials)],
    ['Partners who can take something', offline ? '—' : String(partners)],
    ['Stream analysed', impact ? `${impact.tonnes_analysed} t/mo` : '—'],
    ['Diverted through a match', impact ? `${impact.tonnes_diverted} t/mo` : '—'],
    ['Estimated value', impact ? `${inr(impact.estimated_value_inr_per_month)}/mo` : '—'],
    ['Estimated CO₂e avoided', impact ? `${impact.estimated_co2e_t_per_month} t/mo` : '—'],
    ['Diversion rate', impact ? pct(impact.diversion_rate) : '—'],
  ];
  return (
    <dl className="grid gap-x-8 gap-y-4 border-y border-line py-5 sm:grid-cols-2 lg:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="label">{label}</dt>
          <dd className="stat mt-1.5">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The scoring model, stated as a table rather than as six tiles: what each
 * component is worth, and the two sentences about the model that a reader
 * actually needs before trusting a number.
 */
function Scoring() {
  const weights: [string, number][] = [
    ['Material compatibility', 30],
    ['Quantity fit', 20],
    ['Distance', 15],
    ['Sector fit', 15],
    ['Economic value', 10],
    ['Environmental benefit', 10],
  ];
  return (
    <Section
      title="Why a score means something"
      subtitle="A match score is a weighted sum of six components, computed from the knowledge base and the stated quantity, location and sector. The same input always gives the same score."
    >
      <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr]">
        <ul className="space-y-2">
          {weights.map(([label, weight]) => (
            <li key={label} className="grid grid-cols-[minmax(0,1fr)_120px_3ch] items-center gap-3 text-[12.5px]">
              <span className="text-text">{label}</span>
              <span className="h-1.5 overflow-hidden rounded-full bg-surface-muted">
                <span className="block h-full rounded-full bg-brand" style={{ width: `${(weight / 30) * 100}%` }} />
              </span>
              <span className="text-right tabular-nums text-text-faint">{weight}</span>
            </li>
          ))}
        </ul>
        <div className="space-y-4">
          <div>
            <p className="text-[13px] font-semibold text-text-strong">What the model does</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-text-muted">
              Reads the description, names the material, reports a confidence and proposes candidate reuse routes. Its
              output is checked against the knowledge base, so it can only narrow what exists.
            </p>
          </div>
          <div>
            <p className="text-[13px] font-semibold text-text-strong">What it cannot do</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-text-muted">
              Invent a partner, a price, an emission figure or a safety verdict. Hazardous and unidentified streams are
              held back from household, farm and artisan routes by a rule-based safety layer that outranks similarity.
            </p>
          </div>
          <div>
            <p className="text-[13px] font-semibold text-text-strong">What an estimate is</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-text-muted">
              Value and CO₂e are computed from recorded prices and avoidance factors. They are estimates for comparing
              options, not quotations, invoices or certified figures.
            </p>
          </div>
        </div>
      </div>
    </Section>
  );
}
