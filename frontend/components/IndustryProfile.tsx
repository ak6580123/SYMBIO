/**
 * §5 and §7 - what a receiver actually is.
 *
 * Set out the way an organisation profile is set out in any industrial directory:
 * who they are at the top, then what they make, need, take and discard, in one
 * definition grid. The four §5 steps (Supply → Material demand → Production
 * capability → Potential reuse product) stay visible as the spine of the card,
 * because they are what makes this a symbiosis profile rather than a company
 * blurb - but they are a row, not four nested cards.
 *
 * Every line carries the origin the backend gave it, so a sector template reads as
 * a template and not as a statement about this particular plant.
 */

import { OriginChip, StatusBadge, type Tone } from '@/components/ui';
import {
  inr,
  REUSE_TYPE_LABEL,
  reuseTypeTone,
  SAFETY_LABEL,
  safetyTone,
  sourceLabel,
  titleCase,
 } from '@/lib/format';
import type { IndustryProfile as Profile } from '@/lib/types';

const ORIGIN = {
  'recipient record': 'recipient' as const,
  'knowledge base': 'knowledge_base' as const,
};

function originFor(origin: string): 'recipient' | 'knowledge_base' | 'calculated' | 'user' {
  for (const [needle, key] of Object.entries(ORIGIN)) {
    if (origin.toLowerCase().includes(needle)) return key;
  }
  return origin.toLowerCase().includes('template') ? 'knowledge_base' : 'calculated';
}

/** `detail` is a list of small objects from the backend; show their text values. */
function detailText(detail?: Record<string, unknown>[]): string | undefined {
  if (!detail || detail.length === 0) return undefined;
  const lines = detail
    .map((row) => Object.values(row).filter((value) => typeof value === 'string').join(' - '))
    .filter((line) => line.length > 0);
  return lines.length > 0 ? lines.join('\n') : undefined;
}

export default function IndustryProfile({ profile }: { profile: Profile }) {
  const capability = profile.capability;
  return (
    <article className="overflow-hidden rounded-card border border-line bg-surface">
      <header className="border-b border-line px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            <p className="tag-label">Industry profile</p>
            <h2 className="mt-1 text-[18px] font-semibold leading-snug text-text-strong">{profile.company_name}</h2>
            <p className="mt-0.5 text-[12.5px] text-text-muted">
              {profile.sector_label} · {profile.location}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge tone={reuseTypeTone(capability.reuse_type) as Tone}>{REUSE_TYPE_LABEL[capability.reuse_type]}</StatusBadge>
            <StatusBadge tone={safetyTone(capability.safety_level) as Tone}>{SAFETY_LABEL[capability.safety_level]}</StatusBadge>
            <span className="text-[11px] text-text-faint">{sourceLabel(profile.profile_source)}</span>
          </div>
        </div>
      </header>

      {/* The symbiosis spine, as one strip. Each step says whether the line came from
          the partner's own record or from a sector template. */}
      <ol className="grid divide-y divide-line border-b border-line sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
        {profile.chain.map((step, index) => (
          <li key={step.step} className="px-4 py-3">
            <p className="tag-label">
              {index + 1} · {step.step}
            </p>
            <p className="mt-1 text-[12px] leading-snug text-text">{step.label}</p>
            <ul className="mt-1.5 space-y-0.5">
              {step.items.length > 0 ? (
                step.items.map((item) => (
                  <li key={item} className="text-[11.5px] leading-snug text-text-muted">
                    {item}
                  </li>
                ))
              ) : (
                <li className="text-[11.5px] text-text-faint">Nothing recorded</li>
              )}
            </ul>
            <span className="mt-2 block">
              <OriginChip origin={originFor(step.origin)} label={titleCase(step.origin)} title={detailText(step.detail)} />
            </span>
          </li>
        ))}
      </ol>

      <div className="space-y-6 px-5 py-4">
        <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          <Field label="Products" items={profile.products} />
          <Field label="Materials required" items={profile.materials_required.map((material) => material.name)} />
          <div>
            <dt className="label mb-1.5">Waste streams it generates</dt>
            <dd className="space-y-2">
              {profile.byproducts.map((byproduct) => (
                <div key={byproduct.name}>
                  <p className="text-[12.5px] font-medium text-text-strong">{byproduct.name}</p>
                  <p className="text-[11.5px] leading-snug text-text-muted">{byproduct.disposition}</p>
                  {byproduct.potential_recipients.length > 0 && (
                    <p className="text-[11px] leading-snug text-text-faint">
                      could go to {byproduct.potential_recipients.slice(0, 3).map((receiver) => receiver.company_name).join(', ')}
                      {byproduct.potential_recipients.length > 3
                        ? ` +${byproduct.potential_recipients.length - 3} more`
                        : ''}
                    </p>
                  )}
                  {byproduct.own_product_note && (
                    <p className="text-[11px] leading-snug text-text-faint">{byproduct.own_product_note}</p>
                  )}
                </div>
              ))}
              {profile.byproducts.length === 0 && <p className="text-[11.5px] text-text-faint">No outbound stream recorded.</p>}
            </dd>
          </div>
          <div>
            <dt className="label mb-1.5">Processing capability</dt>
            <dd>
              <p className="text-[12.5px] leading-relaxed text-text-muted">{capability.summary}</p>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {capability.processing.map((step) => (
                  <li key={step} className="chip chip-teal">
                    {titleCase(step)}
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-[11.5px] tabular-nums text-text-faint">
                Intake {capability.quantity_window_t_per_month[0]}–{capability.quantity_window_t_per_month[1]} t/month ·{' '}
                {inr(capability.price_inr_per_tonne)}/tonne
              </p>
            </dd>
          </div>
          <div>
            <dt className="label mb-1.5">What it must be told at the gate</dt>
            <dd className="text-[12.5px] leading-relaxed text-text-muted">{profile.intake_note}</dd>
          </div>
          {profile.certifications.length > 0 && <Field label="Certifications it works to" items={profile.certifications} />}
        </dl>

        <div>
          <p className="label mb-2">Material demand across its sector</p>
          {profile.demand_signals.length === 0 ? (
            <p className="text-[11.5px] text-text-faint">No material demand recorded for this sector.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[460px] border-collapse text-[11.5px]">
                <thead>
                  <tr className="border-b border-line-strong text-left text-text-faint">
                    <th scope="col" className="py-1.5 pr-3 font-medium">Material</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Safety</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">Partners seeking</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">Price</th>
                    <th scope="col" className="py-1.5 text-right font-medium">Window</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.demand_signals.map((signal) => (
                    <tr key={`${signal.material_id ?? signal.name}`} className="border-b border-line last:border-0">
                      <td className="py-1.5 pr-3 text-text">
                        {signal.name}
                        {signal.note && <span className="block text-[11px] leading-snug text-text-faint">{signal.note}</span>}
                      </td>
                      <td className="py-1.5 pr-3">
                        {signal.safety_level ? (
                          <span className={`chip ${safetyTone(signal.safety_level)}`}>{SAFETY_LABEL[signal.safety_level]}</span>
                        ) : (
                          <span className="text-text-faint">not stated</span>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-text-muted">{signal.partners_seeking}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-text-muted">
                        {signal.price_range_inr_per_tonne
                          ? `${inr(signal.price_range_inr_per_tonne[0])}–${inr(signal.price_range_inr_per_tonne[1])}/t`
                          : '—'}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-text-muted">
                        {signal.quantity_window_t_per_month
                          ? `${signal.quantity_window_t_per_month[0]}–${signal.quantity_window_t_per_month[1]} t/mo`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <p className="caption border-t border-line pt-3">{profile.explanation}</p>
      </div>
    </article>
  );
}

function Field({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <dt className="label mb-1.5">{label}</dt>
      <dd>
        {items.length === 0 ? (
          <p className="text-[11.5px] text-text-faint">Nothing recorded.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {items.map((item) => (
              <li key={item} className="chip chip-slate">
                {item}
              </li>
            ))}
          </ul>
        )}
      </dd>
    </div>
  );
}
