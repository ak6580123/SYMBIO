import { SOURCE_SECTOR_LABEL, titleCase } from '@/lib/format';
import type { ExtractionPayload } from '@/lib/types';

/**
 * Review sheet for anything Symbio read out of a file or a sentence.
 *
 * This exists because extracted data must never be trusted silently. Every
 * value shown here carries the text it came from, a value that was *not* found
 * is labelled as the form's own default rather than presented as a reading, and
 * the user can put the form back exactly as it was before applying.
 *
 * The form above stays the source of truth: this panel annotates it and offers
 * to revert. There is deliberately no second set of inputs to keep in sync.
 */

const FREQUENCY_LABEL: Record<string, string> = {
  one_time: 'One-time',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  continuous: 'Continuous',
};

type RowState = 'found' | 'default';

export default function ExtractReview({
  extraction,
  sourceLabel,
  onRevert,
  onDismiss,
}: {
  extraction: ExtractionPayload;
  sourceLabel: string;
  onRevert: () => void;
  onDismiss: () => void;
}) {
  const material = extraction.material.value;
  const composition = Object.entries(extraction.composition.value ?? {});
  const found = countFound(extraction);
  const missing = extraction.missing;

  return (
    <section className="rounded-card border border-ink-700 bg-ink-850/60 p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-slate-200">Review what Symbio read — before analysing</p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            From <span className="text-slate-300">{sourceLabel}</span>. {found} field
            {found === 1 ? '' : 's'} found
            {missing.length ? `, ${missing.length} still to check` : ''}. Nothing is applied to the score until you
            analyze.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={onRevert}
            className="rounded-md border border-ink-600 px-2 py-1 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
          >
            Revert form
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-md border border-ink-600 px-2 py-1 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
          >
            Dismiss
          </button>
        </div>
      </header>

      <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Row
          label="Material"
          state={material ? 'found' : 'default'}
          value={material ? `${material.name} · ${(material.confidence * 100).toFixed(0)}% match` : 'Not identified from the text'}
          evidence={material ? extraction.material.evidence : null}
          hint={
            material
              ? undefined
              : 'The keyword classifier found nothing it could anchor. Type a description and Symbio will identify it on analyze.'
          }
        />
        <Row
          label="Quantity"
          state={extraction.quantity.found ? 'found' : 'default'}
          value={
            extraction.quantity.found
              ? `${extraction.quantity.value} ${extraction.unit.value ?? ''}`.trim()
              : 'Not stated — the form keeps its own default'
          }
          evidence={extraction.quantity.evidence}
        />
        <Row
          label="Frequency"
          state={extraction.frequency.found ? 'found' : 'default'}
          value={extraction.frequency.value ? FREQUENCY_LABEL[extraction.frequency.value] ?? titleCase(extraction.frequency.value) : 'Not stated — assumed per month'}
          evidence={extraction.frequency.evidence}
        />
        <Row
          label="Location"
          state={extraction.location.found ? 'found' : 'default'}
          value={extraction.location.value ?? 'Not a place Symbio can locate'}
          evidence={extraction.location.evidence}
          hint={
            extraction.location.found
              ? undefined
              : 'Only places Symbio can geocode are offered, so the map never shows a pin that was guessed.'
          }
        />
        <Row
          label="Source type"
          state={extraction.source_type.found ? 'found' : 'default'}
          value={
            extraction.source_type.value
              ? SOURCE_SECTOR_LABEL[extraction.source_type.value as keyof typeof SOURCE_SECTOR_LABEL] ??
                titleCase(extraction.source_type.value)
              : 'Not stated — the form keeps its own default'
          }
          evidence={extraction.source_type.evidence}
        />
        <Row
          label="Composition"
          state={composition.length ? 'found' : 'default'}
          value={
            composition.length
              ? composition.map(([k, v]) => `${k.toUpperCase()} ${v}`).join(' · ')
              : 'No oxide percentages found'
          }
          evidence={null}
        />
      </dl>

      {extraction.safety_flags.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-[11px] font-medium text-amber-200">
            Caution words in the text: {extraction.safety_flags.map((f) => f.marker).join(', ')}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-amber-100/70">
            These are shown so nothing in your report goes unnoticed. They do not change any score: the safety layer
            decides routing from the knowledge-base classification of the identified material, during analysis.
          </p>
        </div>
      )}

      {extraction.notes.length > 0 && (
        <ul className="mt-3 space-y-1">
          {extraction.notes.map((note, index) => (
            <li key={index} className="flex gap-2 text-[11px] leading-relaxed text-slate-500">
              <span className="shrink-0 text-slate-600">·</span>
              {note}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function countFound(extraction: ExtractionPayload): number {
  const keys = ['quantity', 'unit', 'frequency', 'location', 'source_type'] as const;
  let found = keys.filter((key) => extraction[key].found).length;
  if (extraction.material.value) found += 1;
  if (Object.keys(extraction.composition.value ?? {}).length) found += 1;
  return found;
}

function Row({
  label,
  value,
  state,
  evidence,
  hint,
}: {
  label: string;
  value: string;
  state: RowState;
  evidence: string | null;
  hint?: string;
}) {
  return (
    <div
      className={`rounded-md border px-2.5 py-2 ${
        state === 'found' ? 'border-emerald-500/25 bg-emerald-500/5' : 'border-ink-700 bg-ink-900'
      }`}
    >
      <dt className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        {state === 'found' ? <span className="text-accent">✓</span> : <span className="text-slate-600">—</span>}
        {label}
      </dt>
      <dd className={`mt-0.5 text-[11px] ${state === 'found' ? 'text-slate-200' : 'text-slate-500'}`}>{value}</dd>
      {evidence && (
        <p className="mt-1 truncate font-mono text-[10px] text-slate-600" title={evidence}>
          “{evidence}”
        </p>
      )}
      {hint && <p className="mt-1 text-[10px] leading-relaxed text-slate-600">{hint}</p>}
    </div>
  );
}
