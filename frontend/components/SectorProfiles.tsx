/**
 * §5 - the sector templates behind every industry profile.
 *
 * A template is authored for a whole sector, so this page shows it as what it is: a
 * pattern the platform applies when a partner's own record does not cover something.
 * The note under the header is the backend's, including the precedence rule.
 */

import { Notice, Panel, StatusBadge } from '@/components/ui';
import { titleCase } from '@/lib/format';
import type { SectorProfile } from '@/lib/types';

export interface SectorProfilePayload {
  profiles: SectorProfile[];
  count: number;
  note: string;
  source: string;
  coverage: { recipients_total: number; recipients_with_template: number; uncovered_sectors: string[] };
  demo_data: boolean;
}

export default function SectorProfiles({ payload, search }: { payload: SectorProfilePayload; search: string }) {
  const needle = search.trim().toLowerCase();
  const profiles = needle
    ? payload.profiles.filter(
        (profile) =>
          profile.label.toLowerCase().includes(needle) ||
          profile.sector.toLowerCase().includes(needle) ||
          profile.materials_required.join(' ').toLowerCase().includes(needle) ||
          profile.byproducts.join(' ').toLowerCase().includes(needle),
      )
    : payload.profiles;

  return (
    <div className="space-y-3">
      <Notice tone="info">
        {payload.coverage.recipients_with_template} of {payload.coverage.recipients_total} partners have a template
        for their sector ({payload.source}).
        {payload.coverage.uncovered_sectors.length > 0
          ? ` Not yet modelled: ${payload.coverage.uncovered_sectors.join(', ')}.`
          : ' Nothing in the partner pool is left without one.'}
      </Notice>

      {profiles.length === 0 ? (
        <Panel title="No sector matches that search">
          <p className="text-xs text-text-muted">Clear the search box to see all {payload.count} templates.</p>
        </Panel>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {profiles.map((profile) => (
            <li key={profile.sector} className="panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-text-strong">{profile.label}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-text-faint">{profile.sector}</p>
                </div>
                <StatusBadge tone="muted">{profile.partners} partner{profile.partners === 1 ? '' : 's'}</StatusBadge>
              </div>

              <dl className="mt-3 space-y-2 text-[11px] leading-relaxed">
                <Group label="Takes in" items={profile.materials_required} tone="text-text" />
                <Group label="Discards" items={profile.byproducts} tone="text-text-muted" />
                <Group label="Makes" items={profile.products} tone="text-text" />
                <Group label="Works to" items={profile.certifications} tone="text-text-muted" />
              </dl>

              <p className="mt-2.5 text-[11px] leading-relaxed text-text-muted">{profile.capability_summary}</p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-text-faint">
                <span className="font-medium text-text-muted">At the gate: </span>
                {profile.intake_note}
              </p>
            </li>
          ))}
        </ul>
      )}

      <p className="text-[11px] leading-relaxed text-text-faint">{payload.note}</p>
    </div>
  );
}

function Group({ label, items, tone }: { label: string; items: string[]; tone: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className={`mt-0.5 ${tone}`}>{items.map((item) => titleCase(item)).join(' · ')}</dd>
    </div>
  );
}
