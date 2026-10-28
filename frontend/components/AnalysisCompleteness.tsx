/**
 * §3 - how much of the picture the engine was actually given.
 *
 * This panel can only describe the input. It never dims a match, never blocks the
 * analysis, and says so in the backend's own words: `blocks_analysis` is false by
 * construction, and the line under the bar is the response's `note`, not a sentence
 * written here.
 */

import { Bar, Notice, Panel, StatusBadge, type Tone } from '@/components/ui';
import { scoreColor } from '@/lib/palette';
import type { CompletenessCard, CompletenessField, CompletenessGap } from '@/lib/types';

const LEVEL_TONE: Record<string, Tone> = {
  complete: 'teal',
  solid: 'teal',
  workable: 'amber',
  thin: 'clay',
};

const GROUP_LABEL: Record<string, string> = {
  identification: 'Read the material',
  scoring: 'Score the fit',
  handling: 'Screen the handling',
  safety: 'Screen the safety',
};

/** The same figure as a chip, for a page that has no room for the panel. */
export function CompletenessChip({ completeness }: { completeness?: CompletenessCard | null }) {
  if (!completeness) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-text-faint">
      <span className="tabular-nums">{completeness.percent}% complete</span>
      <StatusBadge tone={LEVEL_TONE[completeness.level] ?? 'muted'} title={completeness.note}>
        {completeness.level}
      </StatusBadge>
    </span>
  );
}

export default function AnalysisCompleteness({ completeness }: { completeness?: CompletenessCard | null }) {
  if (!completeness) return null;

  const groups = groupFields(completeness.fields, completeness.missing);
  const tone = LEVEL_TONE[completeness.level] ?? 'muted';

  return (
    <Panel
      title="Analysis completeness"
      subtitle="What this run was told, and what one more line about each gap would change"
      action={
        <div className="flex items-center gap-2">
          <StatusBadge tone={tone}>{completeness.level}</StatusBadge>
          <span className="value tabular-nums text-accent">{completeness.percent}%</span>
        </div>
      }
    >
      <div className="space-y-4">
        <div>
          <Bar value={completeness.percent / 100} color={scoreColor(completeness.percent)} />
          <p className="mt-1.5 text-[11px] leading-relaxed text-text-faint">{completeness.note}</p>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {groups.map((group) => (
            <div key={group.group} className="rounded-card border border-line bg-surface-inset px-3 py-2.5">
              <p className="label">{GROUP_LABEL[group.group] ?? group.group}</p>
              <p className="mt-1 text-sm tabular-nums text-text-strong">
                {group.earned}
                <span className="text-text-faint"> / {group.weight}</span>
              </p>
              <p className="mt-1 text-[11px] leading-snug text-text-faint">
                {group.missing.length === 0
                  ? 'nothing outstanding'
                  : `missing: ${group.missing.map((field) => field.label.toLowerCase()).join(', ')}`}
              </p>
            </div>
          ))}
        </div>

        {completeness.insights.length > 0 && (
          <div>
            <p className="label mb-1.5">What the supplied fields already rule in or out</p>
            <ul className="space-y-1.5">
              {completeness.insights.map((insight) => (
                <li key={insight.field} className="rounded-card border border-line bg-surface-inset px-3 py-2">
                  <p className="text-xs font-medium text-text">{insight.title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-text-muted">{insight.note}</p>
                  <p className="mt-1 text-[11px] leading-snug text-text-faint">{insight.affects}</p>
                  {insight.affected_recipients && insight.affected_recipients.length > 0 && (
                    <p className="mt-1 text-[11px] leading-snug text-text-faint">
                      {insight.affected_recipients.slice(0, 4).join(', ')}
                      {insight.affected_recipients.length > 4
                        ? ` +${insight.affected_recipients.length - 4} more`
                        : ''}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {completeness.missing.length > 0 ? (
          <div>
            <p className="label mb-1.5">
              Worth adding · {completeness.missing.length} field{completeness.missing.length === 1 ? '' : 's'}
            </p>
            <ul className="space-y-1.5">
              {completeness.missing.map((field) => (
                <li key={field.key} className="rounded-card border border-line px-3 py-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-xs font-medium text-text">{field.label}</p>
                    <p className="text-[11px] tabular-nums text-text-faint">worth {field.weight}%</p>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-text-muted">{field.advice}</p>
                  <p className="mt-1 text-[11px] leading-snug text-text-faint">{field.changes}</p>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <Notice tone="success">
            Every field this pipeline reads is present. Nothing further is being asked for.
          </Notice>
        )}
      </div>
    </Panel>
  );
}

/** Group the weights the backend published. Only addition happens here. */
function groupFields(fields: CompletenessField[], missing: CompletenessGap[]) {
  const order: string[] = [];
  const byGroup = new Map<string, { group: string; weight: number; earned: number; missing: CompletenessGap[] }>();
  for (const field of fields) {
    if (!byGroup.has(field.group)) {
      byGroup.set(field.group, { group: field.group, weight: 0, earned: 0, missing: [] });
      order.push(field.group);
    }
    const bucket = byGroup.get(field.group)!;
    bucket.weight += field.weight;
    if (field.provided) bucket.earned += field.weight;
  }
  for (const gap of missing) {
    const bucket = byGroup.get(gap.group);
    if (bucket) bucket.missing.push(gap);
  }
  return order.map((key) => byGroup.get(key)!);
}
