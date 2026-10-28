'use client';

/**
 * Material intelligence card (Feature 7) and provenance tags (Feature 3).
 *
 * Everything on this card is either the knowledge-base record for the identified
 * material or a check recomputed from this analysis. Nothing is summarised by a
 * model, and each row carries the tag the backend gave it, so an estimate
 * cannot be read as a measurement.
 */

import { useEffect, useState } from 'react';

import { Notice, OriginChip, Panel, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import { ORIGIN_TONE, SAFETY_LABEL, titleCase } from '@/lib/format';
import type { IntelligenceCard, MaterialRecord, ProvenanceOrigin } from '@/lib/types';


export default function MaterialIntel({
  analysisId,
  inline,
  onCorrect,
  correcting = false,
}: {
  analysisId: string;
  /** The same card `/api/analyze` already returned, so no second round-trip. */
  inline?: IntelligenceCard | null;
  /** Called with a knowledge-base material id the user picked. */
  onCorrect?: (materialId: string) => void;
  correcting?: boolean;
}) {
  const [card, setCard] = useState<IntelligenceCard | null>(inline ?? null);
  const [error, setError] = useState<string | null>(null);
  const [correcting_open, setCorrectingOpen] = useState(false);
  const [materials, setMaterials] = useState<MaterialRecord[] | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (inline) {
      setCard(inline);
      return;
    }
    let alive = true;
    api
      .intelligence(analysisId)
      .then((body) => alive && setCard(body))
      .catch((err) => alive && setError(err instanceof Error ? err.message : 'Could not load the material record'));
    return () => {
      alive = false;
    };
  }, [analysisId, inline]);

  const openSearch = async () => {
    setCorrectingOpen((open) => !open);
    if (materials === null) {
      try {
        const body = await api.materials();
        setMaterials(body.materials);
      } catch {
        setMaterials([]);
        setError('The knowledge base could not be listed, so no correction can be offered.');
      }
    }
  };

  if (error && !card) return <Notice tone="danger">{error}</Notice>;
  if (!card) {
    return (
      <Panel title="Material intelligence">
        <Spinner label="Reading the knowledge base…" />
      </Panel>
    );
  }

  const needle = search.trim().toLowerCase();
  const options = (materials ?? []).filter(
    (item) =>
      !needle ||
      [item.name, item.id, item.category, ...(item.aliases ?? [])].some((value) => value.toLowerCase().includes(needle)),
  );
  const identified = card.material.name;

  return (
    <Panel
      title="Material intelligence"
      action={
        <span className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="chip chip-amber" title="Reference record in the knowledge base - not verified against a laboratory report or a regulation.">
            {card.verification === 'verified' ? 'knowledge base · verified' : 'knowledge base'}
          </span>
        </span>
      }
    >
      <div className="space-y-4">
        {/* What the identifier did, and what it was built from. */}
        <div className="rounded-md border border-ink-700 bg-ink-900 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-100">{identified}</h3>
            <span className="chip border-ink-600 text-slate-400">{titleCase(card.material.category)}</span>
            <span className="chip border-ink-600 text-slate-400">{SAFETY_LABEL[card.material.safety_level]}</span>
            {card.identification.user_corrected && (
              <span className="chip border-sky-500/40 bg-sky-500/10 text-sky-200">
                Material manually corrected by user
              </span>
            )}
          </div>
          <p className="mt-1.5 text-[11px] text-slate-500">
            {card.identification.user_corrected
              ? 'Selected from the knowledge base by you. The knowledge base itself was not modified, and this correction applies to this analysis only.'
              : `Confidence ${(card.identification.confidence * 100).toFixed(0)}% · engine ${card.identification.engine ?? 'unknown'}`}
          </p>
          {card.identification.uncertainty_note && (
            <p className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-relaxed text-amber-100">
              {card.identification.uncertainty_note}
            </p>
          )}

          <ul className="mt-3 space-y-1.5">
            {card.evidence.map((row) => (
              <li key={row.check} className="flex items-start gap-2 text-[11px] leading-relaxed">
                <span className={row.passed ? 'text-emerald-400' : 'text-slate-600'} aria-hidden>
                  {row.passed ? '✓' : '•'}
                </span>
                <span className={row.passed ? 'text-slate-300' : 'text-slate-500'}>{row.check}</span>
                <OriginChip origin={row.origin} label={row.origin_label} />
                <span className="text-slate-600">{row.detail}</span>
              </li>
            ))}
          </ul>

          {onCorrect && (
            <div className="mt-3 border-t border-ink-700 pt-3">
              <button onClick={openSearch} className="text-[11px] link" disabled={correcting}>
                {correcting_open ? 'cancel' : `Is “${identified}” wrong? Correct it for this analysis`}
              </button>
              {correcting_open && (
                <div className="mt-2 rounded-md border border-ink-700 bg-ink-950/60 p-3">
                  <p className="caption leading-relaxed">
                    Pick the material you actually have. Symbio re-runs matching and the safety layer against that
                    knowledge-base record — the record itself is not edited, and no new material is created.
                  </p>
                  <input
                    autoFocus
                    className="input mt-2"
                    placeholder="Search the knowledge base…"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                  {materials === null ? (
                    <Spinner label="Loading the knowledge base…" />
                  ) : (
                    <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto pr-1">
                      {options.map((item) => (
                        <li key={item.id}>
                          <button
                            disabled={correcting}
                            onClick={() => {
                              onCorrect(item.id);
                              setCorrectingOpen(false);
                            }}
                            className="flex w-full items-center gap-2 rounded border border-transparent px-2 py-1 text-left text-[11px] hover:border-ink-700 hover:bg-ink-900 disabled:opacity-60"
                          >
                            <span className="font-medium text-slate-200">{item.name}</span>
                            <span className="chip border-ink-600 text-slate-500">{titleCase(item.category)}</span>
                            <span className="ml-auto text-slate-600">{item.id}</span>
                          </button>
                        </li>
                      ))}
                      {options.length === 0 && (
                        <li className="px-2 py-1 text-[11px] text-slate-600">
                          Nothing in the knowledge base matches “{search}”. A material that is not in the knowledge
                          base cannot be selected — and Symbio will not guess one.
                        </li>
                      )}
                    </ul>
                  )}
                  {correcting && <p className="mt-2 text-[11px] text-slate-500">Re-running the analysis…</p>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* The knowledge base record itself. */}
        <div className="grid gap-2 sm:grid-cols-2">
          {card.sections.map((section) => (
            <div key={section.title} className="rounded-md border border-ink-700 bg-ink-900 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="label">{section.title}</p>
                <OriginChip origin={section.origin} label={section.origin_label} title={section.origin_note} />
              </div>
              <SectionValue section={section} />
            </div>
          ))}
        </div>

        {/* Gate rules, published by the code that enforces them. */}
        {(card.material.gate_rules ?? []).length > 0 && (
          <div className="rounded-md border border-rose-500/20 bg-rose-500/5 p-3">
            <p className="label mb-1.5 text-rose-200/80">Rules the safety layer applies to this material</p>
            <ul className="space-y-1 text-[11px] leading-relaxed text-slate-300">
              {card.material.gate_rules!.map((rule) => (
                <li key={rule} className="flex gap-2">
                  <span className="text-rose-300" aria-hidden>
                    !
                  </span>
                  {rule}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-600">
          <span className="uppercase tracking-wider">Where these values come from</span>
          {Object.entries(card.origins).map(([key, label]) => (
            <span key={key} className={`chip ${ORIGIN_TONE[key as ProvenanceOrigin]}`} title={card.origin_notes[key]}>
              {label}
            </span>
          ))}
        </div>
        {error && <Notice tone="warn">{error}</Notice>}
      </div>
    </Panel>
  );
}

function SectionValue({ section }: { section: IntelligenceCard['sections'][number] }) {
  if (section.kind === 'list') {
    const items = (section.value as string[]) ?? [];
    if (items.length === 0) return <p className="mt-1 text-[11px] text-slate-600">{section.empty ?? 'Nothing recorded.'}</p>;
    return (
      <ul className="mt-1.5 space-y-1 text-[11px] leading-relaxed text-slate-300">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span className="text-slate-600">—</span>
            {item}
          </li>
        ))}
      </ul>
    );
  }
  if (section.kind === 'kv') {
    const entries = Object.entries((section.value as Record<string, string>) ?? {});
    if (entries.length === 0) return <p className="mt-1 text-[11px] text-slate-600">{section.empty ?? 'Nothing recorded.'}</p>;
    return (
      <dl className="mt-1.5 grid grid-cols-2 gap-1 text-[11px]">
        {entries.map(([key, value]) => (
          <div key={key} className="rounded border border-ink-700 bg-ink-950/60 px-2 py-1">
            <dt className="font-mono text-[10px] text-slate-500">{key.toUpperCase()}</dt>
            <dd className="tabular-nums text-slate-200">{value}</dd>
          </div>
        ))}
      </dl>
    );
  }
  const text = (section.value as string) ?? '';
  return <p className={`mt-1 text-[11px] leading-relaxed ${text ? 'text-slate-300' : 'text-slate-600'}`}>{text || section.empty || 'Nothing recorded.'}</p>;
}
