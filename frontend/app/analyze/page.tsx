'use client';

import Link from 'next/link';
import { useState } from 'react';

import AnalysisCompleteness from '@/components/AnalysisCompleteness';
import ExtractReview from '@/components/ExtractReview';
import FileDrop from '@/components/FileDrop';
import MaterialIntel from '@/components/MaterialIntel';
import ScenarioComparison from '@/components/ScenarioComparison';
import SimilarityPanel from '@/components/SimilarityPanel';
import Pathways from '@/components/Pathways';
import WhatIf from '@/components/WhatIf';
import { ConfidenceBar, ErrorState, Metric, Notice, PageHeader, Panel, ScoreRing, Spinner } from '@/components/ui';
import {
  inr,
  REUSE_TYPE_LABEL,
  relativeTime,
  reuseTypeTone,
  SAFETY_LABEL,
  safetyTone,
  SOURCE_SECTOR_LABEL,
  titleCase,
  distanceShort,
 } from '@/lib/format';
import { api, ApiError, type AnalyzeInput } from '@/lib/api';
import type {
  AnalyzeResponse,
  ExtractionPayload,
  MatchSort,
  SourceSector,
  UploadResponse,
} from '@/lib/types';

const UNITS = ['tonnes', 'kg', 'litres', 'units'];
//** The values the request schema accepts for `physical_state`. */
const PHYSICAL_STATES = ['powder', 'granular', 'solid', 'sludge', 'liquid', 'fiber', 'mixed'];
const FREQUENCIES = [
  { value: 'one_time', label: 'One-time' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'continuous', label: 'Continuous' },
];

type FormState = {
  source_type: SourceSector;
  material_description: string;
  quantity: string;
  unit: string;
  location: string;
  frequency: string;
  composition: string;
  physical_state: string;
  moisture_percent: string;
  contaminants: string;
  intended_use: string;
};

/**
 * §7 - the form asks each kind of generator for what it can actually state. A
 * household association does not have a moisture reading, so the field is not put in
 * front of it; a plant usually has loss-on-ignition and assay lines, so those fields
 * are where a plant would look. Both extra fields are real request fields scored by
 * the completeness analysis, not decoration.
 */
const FORM_DEPTH: Record<
  string,
  { assay: boolean; moisture: boolean; contaminants: boolean; note: string }
> = {
  industry: {
    assay: true,
    moisture: true,
    contaminants: true,
    note: 'A plant usually has assay, loss on ignition and moisture on file. Those three lines are what turn a generic match into one a receiver can act on.',
  },
  sme: {
    assay: true,
    moisture: true,
    contaminants: false,
    note: 'Small sites rarely hold a full assay, so composition is optional and the description carries the weight.',
  },
  agriculture: {
    assay: false,
    moisture: true,
    contaminants: false,
    note: 'For residues, moisture matters most: it decides drying, baling and what a buyer will actually pay for.',
  },
  household: {
    assay: false,
    moisture: false,
    contaminants: false,
    note: 'A description in plain words is enough. Nothing here asks for a laboratory result.',
  },
  other: {
    assay: false,
    moisture: false,
    contaminants: false,
    note: 'Describe it as you know it; the fields a laboratory would fill are not asked for.',
  },
};

const EXAMPLES: { label: string; input: FormState }[] = [
  {
    label: 'Fly ash · 5 t/month · Chennai',
    input: {
      source_type: 'industry',
      material_description:
        'Pulverised coal fly ash collected from the electrostatic precipitator of our thermal power station. Dry, fine grey powder, consistent quality.',
      quantity: '5',
      unit: 'tonnes',
      location: 'Manali, Chennai',
      frequency: 'monthly',
      composition: 'SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%',
      physical_state: '',
      moisture_percent: '',
      contaminants: '',
      intended_use: '',
    },
  },
  {
    label: 'Cardboard · 900 kg/month · household',
    input: {
      source_type: 'household',
      material_description: 'Segregated corrugated cardboard and mixed paper from 240 apartments, baled weekly.',
      quantity: '900',
      unit: 'kg',
      location: 'Anna Nagar, Chennai',
      frequency: 'monthly',
      composition: '',
      physical_state: '',
      moisture_percent: '',
      contaminants: '',
      intended_use: '',
    },
  },
  {
    label: 'Spent catalyst · hazardous',
    input: {
      source_type: 'industry',
      material_description: 'Spent hydroprocessing catalyst from our refinery hydrotreater unit.',
      quantity: '3',
      unit: 'tonnes',
      location: 'Chennai, Tamil Nadu',
      frequency: 'monthly',
      composition: '',
      physical_state: '',
      moisture_percent: '',
      contaminants: '',
      intended_use: '',
    },
  },
];

/** A comma-separated input becomes the list the request schema expects. */
function splitList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .slice(0, 20);
}

export default function AnalyzePage() {
  const [form, setForm] = useState<FormState>({
    source_type: 'industry',
    material_description: '',
    quantity: '5',
    unit: 'tonnes',
    location: '',
    frequency: 'monthly',
    composition: '',
    physical_state: '',
    moisture_percent: '',
    contaminants: '',
    intended_use: '',
  });
  const depth = FORM_DEPTH[form.source_type] ?? FORM_DEPTH.other;
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  /** Candidate fields read from an uploaded file or a pasted sentence, shown for review. */
  const [extraction, setExtraction] = useState<ExtractionPayload | null>(null);
  const [extractFrom, setExtractFrom] = useState<string | null>(null);
  const [formBeforeExtract, setFormBeforeExtract] = useState<FormState | null>(null);
  const [sentence, setSentence] = useState('');
  const [reading, setReading] = useState(false);
  /** §9 - inline, before any request: the location is the user's and is never filled in. */
  const [locationError, setLocationError] = useState<string | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  /** Exactly what the last successful analysis was given, so a correction can
   *  re-run it with one field added and nothing else. */
  const [lastInput, setLastInput] = useState<AnalyzeInput | null>(null);
  const [mode, setMode] = useState<MatchSort>('score');
  const [correcting, setCorrecting] = useState(false);

  const set = (key: keyof FormState, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }) as FormState);

  /**
   * Copy what the reader found into the form, without touching anything it did
   * not find. The review panel then shows each value next to the text it came
   * from, so a wrong reading is visible and correctable before any scoring.
   */
  const applyExtraction = (fields: ExtractionPayload, sourceLabel: string) => {
    setFormBeforeExtract(form);
    setExtraction(fields);
    setExtractFrom(sourceLabel);
    setForm((prev) => {
      const next = { ...prev };
      if (fields.quantity.found && fields.quantity.value !== null) next.quantity = String(fields.quantity.value);
      if (fields.unit.found && fields.unit.value) next.unit = fields.unit.value;
      if (fields.frequency.found && fields.frequency.value) next.frequency = fields.frequency.value;
      if (fields.location.found && fields.location.value) next.location = fields.location.value;
      if (fields.source_type.found && fields.source_type.value) next.source_type = fields.source_type.value as SourceSector;
      if (fields.composition.found && fields.composition.value && !prev.composition.trim()) {
        next.composition = Object.entries(fields.composition.value)
          .map(([oxide, pct]) => `${oxide}: ${pct}`)
          .join(', ');
      }
      return next as FormState;
    });
  };

  /** The file drop hands over the whole upload result; only its fields are new here. */
  const handleUploaded = (result: UploadResponse | null) => {
    setUpload(result);
    if (result?.fields) {
      applyExtraction(result.fields, result.filename);
      setExtractError(null);
    } else {
      setExtraction(null);
      setExtractFrom(null);
      setFormBeforeExtract(null);
    }
  };

  const extractFromSentence = async () => {
    const text = sentence.trim();
    if (text.length < 8) {
      setExtractError('Write a full sentence first, e.g. \"We produce around 5 tonnes of fly ash every month in Chennai\".');
      return;
    }
    setReading(true);
    setExtractError(null);
    try {
      const fields = await api.extract(text);
      applyExtraction(fields, 'your sentence');
      // The sentence itself is what the matcher identifies on, so it fills the
      // description only when the user has not written one.
      if (!form.material_description.trim()) set('material_description', text);
    } catch (err) {
      setExtractError(err instanceof ApiError ? err.message : 'Could not read the sentence. Fill the form instead.');
    } finally {
      setReading(false);
    }
  };

  /**
   * Human-in-the-loop correction (Feature 5): re-run the same analysis with a
   * knowledge-base material the user picked. The override is a field on the
   * request, so the knowledge base is never written to and every other analysis
   * keeps the identification the system made.
   */
  const correctMaterial = async (materialId: string) => {
    if (!lastInput) {
      setError('Run an analysis first, then correct it.');
      return;
    }
    setCorrecting(true);
    setError(null);
    try {
      const response = await api.analyze({ ...lastInput, material_override_id: materialId });
      setResult(response);
      setLastInput({ ...lastInput, material_override_id: materialId });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The corrected analysis failed');
    } finally {
      setCorrecting(false);
    }
  };

  const revertExtraction = () => {
    if (formBeforeExtract) setForm(formBeforeExtract);
    setExtraction(null);
    setExtractFrom(null);
    setFormBeforeExtract(null);
  };

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const quantity = Number(form.quantity);
      if (!form.material_description.trim()) throw new ApiError(422, 'Describe the material first.');
      if (!Number.isFinite(quantity) || quantity <= 0) throw new ApiError(422, 'Enter a quantity greater than zero.');
      // Required, and never filled in for the user: a substituted city would carry a
      // fabricated distance into every score, estimate and map pin below it.
      if (!form.location.trim()) {
        setLocationError('Add where this material is - a town or locality is enough.');
        setLoading(false);
        return;
      }

      const input: AnalyzeInput = {
        source_type: form.source_type,
        material_description: form.material_description.trim(),
        quantity,
        unit: form.unit,
        location: form.location.trim(),
        frequency: form.frequency,
        composition: form.composition.trim() || null,
        physical_state: form.physical_state.trim() || null,
        moisture_percent: depth.moisture && form.moisture_percent.trim() ? Number(form.moisture_percent) : null,
        intended_use: form.intended_use.trim() || null,
        ...(depth.contaminants ? { contaminants: splitList(form.contaminants) } : {}),
        attached_text: upload?.extracted_text?.trim() || sentence.trim() || null,
        attached_filename: upload?.filename || null,
      };
      const response = await api.analyze(input);
      setResult(response);
      setLastInput(input);
      document.getElementById('result')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Step 1"
        title="Describe or upload your material"
        subtitle="A sentence in plain words is enough to start. Only where the material sits is needed - everything else sharpens what Symbio can say about it, and is optional."      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] text-text-faint">Or start from a stream already in the network:</p>
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example.label}
              type="button"
              onClick={() => {
                setForm((prev) => ({ ...prev, ...example.input }));
                setUpload(null);
              }}
              className="rounded-md border border-ink-600 bg-ink-850 px-2.5 py-1 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
            >
              {example.label}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={submit} className="panel p-5">
        <div className="grid gap-4 lg:grid-cols-2">
          <Field label="Who is describing this stream" required>
            <select
              className="input"
              value={form.source_type}
              onChange={(e) => set('source_type', e.target.value)}
            >
              {(Object.keys(SOURCE_SECTOR_LABEL) as SourceSector[]).map((key) => (
                <option key={key} value={key}>
                  {SOURCE_SECTOR_LABEL[key]}
                </option>
              ))}
            </select>
            <p className="caption mt-1.5">{FORM_DEPTH[form.source_type]?.note}</p>
          </Field>

          <Field label="Where is it" required error={locationError}>
            <input
              className="input"
              value={form.location}
              onChange={(e) => {
                set('location', e.target.value);
                if (locationError) setLocationError(null);
              }}
              placeholder="Town, locality or estate - e.g. Peelamedu, Coimbatore"
              aria-describedby="location-help"
              aria-invalid={locationError ? true : undefined}
            />
            <p id="location-help" className="caption mt-1.5">
              Symbio works out distances from this. If the place is not one it can locate, the analysis still runs -
              the distance part is marked unavailable rather than measured from somewhere else.
            </p>
          </Field>

          <div className="lg:col-span-2">
            {/* Feature: describe it in one sentence instead of filling the form.
                The reader only proposes values - they land in the review panel below. */}
            <div className="rounded-md border border-ink-700 bg-ink-900 p-3">
              <p className="text-[11px] font-medium text-slate-300">In your own words</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                Write one plain sentence about what you have. Symbio reads quantity, material, location and frequency
                out of it and shows you what it understood before anything is analyzed.
              </p>
              <div className="mt-2 flex gap-2">
                <input
                  className="input min-w-0 flex-1"
                  value={sentence}
                  onChange={(e) => setSentence(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void extractFromSentence();
                    }
                  }}
                  placeholder="We produce around 5 tonnes of fly ash every month in Chennai"
                />
                <button type="button" onClick={() => void extractFromSentence()} disabled={reading} className="btn-secondary shrink-0">
                  {reading ? 'Reading…' : 'Extract fields'}
                </button>
              </div>
              {extractError && <p className="mt-1.5 text-[11px] text-amber-300">{extractError}</p>}
            </div>
          </div>

          <div className="lg:col-span-2">
            <Field label="Material description" required>
              <textarea
                className="input min-h-[92px] resize-y"
                value={form.material_description}
                onChange={(e) => set('material_description', e.target.value)}
                placeholder="e.g. Fine grey powder from our boiler flue gas precipitator, high silica content…"
              />
            </Field>
          </div>

          <Field label="Approximate quantity" required>
            <div className="flex gap-2">
              <input
                className="input"
                type="number"
                min="0"
                step="any"
                value={form.quantity}
                onChange={(e) => set('quantity', e.target.value)}
              />
              <select className="input w-32" value={form.unit} onChange={(e) => set('unit', e.target.value)}>
                {UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </select>
            </div>
          </Field>

          <Field label="Frequency">
            <select className="input" value={form.frequency} onChange={(e) => set('frequency', e.target.value)}>
              {FREQUENCIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Physical state (optional)">
            <select className="input" value={form.physical_state} onChange={(e) => set('physical_state', e.target.value)}>
              <option value="">Not stated</option>
              {PHYSICAL_STATES.map((state) => (
                <option key={state} value={state}>
                  {titleCase(state)}
                </option>
              ))}
            </select>
          </Field>

          {depth.assay && (
            <Field label="Composition (optional)">
              <input
                className="input"
                value={form.composition}
                onChange={(e) => set('composition', e.target.value)}
                placeholder="SiO2: 55%, Al2O3: 25%, CaO: 8%"
              />
            </Field>
          )}

          {depth.moisture && (
            <Field label="Moisture % (optional)">
              <input
                className="input"
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={form.moisture_percent}
                onChange={(e) => set('moisture_percent', e.target.value)}
                placeholder="e.g. 12"
              />
            </Field>
          )}

          {depth.contaminants && (
            <Field label="Known contaminants (optional)">
              <input
                className="input"
                value={form.contaminants}
                onChange={(e) => set('contaminants', e.target.value)}
                placeholder="unburnt carbon, heavy metals, plastic film"
              />
            </Field>
          )}

          <Field label="What you had in mind for it (optional)">
            <input
              className="input"
              value={form.intended_use}
              onChange={(e) => set('intended_use', e.target.value)}
              placeholder="e.g. road sub-base, brick manufacture, feedstock to a cement plant"
            />
          </Field>

          <Field label="Waste or material report (optional)">
            <FileDrop onExtracted={handleUploaded} />
          </Field>
        </div>

        {extraction && extractFrom && (
          <div className="mt-4">
            <ExtractReview
              extraction={extraction}
              sourceLabel={extractFrom}
              onRevert={revertExtraction}
              onDismiss={() => setExtraction(null)}
            />
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <button type="submit" className="btn-primary btn-lg" disabled={loading}>
            {loading ? 'Identifying the material…' : 'Find opportunities'}
          </button>
          <p className="text-[11px] leading-snug text-text-faint">
            Quantities are normalised to tonnes per month. Identification runs on the local model, or on the built-in
            classifier when no model is running.
          </p>
        </div>
      </form>

      {loading && (
        <div className="panel panel-pad">
          <Spinner label="Identifying material and scoring recipients…" />
        </div>
      )}

      {error && (
        <ErrorState
          title="The analysis could not be completed."
          hint={error}
          onRetry={() => void submit()}
        />
      )}

      {result && (
        <Result
          result={result}
          mode={mode}
          onModeChange={setMode}
          onCorrect={correctMaterial}
          correcting={correcting}
        />
      )}

      <div id="result" />
    </div>
  );
}

function Field({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">
        {label}
        {required && <span className="text-accent"> *</span>}
      </span>
      {error && <span className="mb-1.5 block text-[11.5px] leading-snug text-cherry">{error}</span>}
      {children}
    </label>
  );
}

function Result({
  result,
  mode,
  onModeChange,
  onCorrect,
  correcting,
}: {
  result: AnalyzeResponse;
  /** Optimisation mode, shared with the pathway panel so both read the same "best". */
  mode: MatchSort;
  onModeChange: (mode: MatchSort) => void;
  onCorrect: (materialId: string) => void;
  correcting: boolean;
}) {
  const { analysis } = result;
  const ident = analysis.identification;
  const lowConfidence = ident.confidence < 0.5;

  return (
    <div className="space-y-5">
      {analysis.warnings.map((warning, index) => (
        <Notice key={index} tone={lowConfidence ? 'warn' : 'info'}>
          {warning}
        </Notice>
      ))}

      {/* Identification */}
      <Panel
        title="Material identification"
        action={
          <span className="chip border-ink-600 bg-ink-800 font-mono text-[10px] text-slate-400">
            {ident.engine}
          </span>
        }
      >
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="text-lg font-semibold text-slate-100">{analysis.material.name}</h3>
              <span className="chip border-ink-600 bg-ink-800 text-slate-400">
                {titleCase(ident.category ?? 'unknown')}
              </span>
              <span className={`chip ${safetyTone(ident.safety_level)}`}>{SAFETY_LABEL[ident.safety_level]}</span>
              {ident.requires_processing && (
                <span className="chip border-sky-500/40 bg-sky-500/10 text-sky-300">Processing required</span>
              )}
            </div>

            <div className="mt-3 flex items-center gap-2">
              <span className="label">Confidence</span>
              <ConfidenceBar confidence={ident.confidence} />
            </div>

            {/* Feature 5's promise, in the panel itself and not only in a
                banner above: an unidentified stream says so where the material
                name would normally be. */}
            {analysis.material.id === 'unknown_material' && (
              <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100">
                Material could not be confidently identified. Nothing below is reuse advice for the material itself —
                the routes shown are the ones a licensed waste processor can take for assessment.
              </p>
            )}

            {ident.reasoning && <p className="mt-3 text-xs leading-relaxed text-slate-400">{ident.reasoning}</p>}
            {analysis.material.notes && (
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{analysis.material.notes}</p>
            )}

            {ident.alternatives.length > 0 && (
              <div className="mt-3">
                <p className="label mb-1.5">Other possibilities</p>
                <div className="flex flex-wrap gap-1.5">
                  {ident.alternatives.map((alt) => (
                    <span key={alt.material_id} className="chip border-ink-600 bg-ink-800 text-slate-400">
                      {alt.material} · {(alt.confidence * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-3">
            <div>
              <p className="label mb-1.5">Extracted composition</p>
              {Object.keys(ident.composition).length > 0 ? (
                <div className="grid grid-cols-2 gap-1.5">
                  {Object.entries(ident.composition).map(([key, value]) => (
                    <div key={key} className="rounded border border-ink-700 bg-ink-900 px-2 py-1">
                      <span className="font-mono text-[11px] text-slate-300">{key.toUpperCase()}</span>
                      <span className="ml-1.5 text-[11px] tabular-nums text-accent">{value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-600">None reported.</p>
              )}
            </div>
            <div>
              <p className="label mb-1.5">Knowledge-base reuse routes</p>
              <div className="flex flex-wrap gap-1.5">
                {analysis.material.reuse_categories.map((route) => (
                  <span key={route} className="chip border-ink-600 bg-ink-800 text-slate-400">
                    {titleCase(route)}
                  </span>
                ))}
                {analysis.material.reuse_categories.length === 0 && (
                  <span className="text-xs text-slate-600">No reuse route recorded.</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </Panel>

      {/* §3 - what this run was told and what one more line would change. Describes
          the input only: it cannot dim a match and it never blocks the analysis. */}
      <AnalysisCompleteness completeness={analysis.completeness} />

      {/* Features 3 + 7: what was found, how it was found, and what the knowledge
          base actually says - plus the correction that starts a fresh run. */}
      <MaterialIntel
        analysisId={analysis.id}
        inline={result.intelligence ?? null}
        onCorrect={onCorrect}
        correcting={correcting}
      />

      {/* §15 - what the safety layer decided, in its own words, before any
          recommendation is read. The rules below are generated from the code that
          applied them, so this cannot drift from the gate. */}
      <Panel
        title="Safety status"
        subtitle="Applied before ranking, by rule - never by the model."
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <span className={`chip ${safetyTone(analysis.material.safety_level)} !px-2.5 !py-1 text-[12px]`}>
            {SAFETY_LABEL[analysis.material.safety_level]}
          </span>
          <span className="text-[12.5px] text-text-muted">
            {analysis.material.requires_processing
              ? 'Industrial processing required before any reuse route is valid.'
              : 'Usable as it stands, subject to the partner\'s own intake conditions.'}
          </span>
        </div>
        {(analysis.material.gate_rules?.length ?? 0) > 0 && (
          <ul className="mt-3 space-y-1.5 border-t border-line pt-2.5">
            {(analysis.material.gate_rules ?? []).map((rule) => (
              <li key={rule} className="flex gap-2 text-[11.5px] leading-relaxed text-text-muted">
                <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-cherry" />
                {rule}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {analysis.excluded.length > 0 && (
        <Panel title={`Refused by the safety layer (${analysis.excluded.length})`} subtitle="Removed before scoring, so they never appear as a match.">
          <ul className="max-h-48 space-y-1 overflow-y-auto pr-1">
            {analysis.excluded.slice(0, 12).map((item) => (
              <li key={`${item.recipient_id}-${item.reason}`} className="flex gap-2 text-[11.5px] leading-relaxed">
                <span className="shrink-0 font-medium text-text-muted">{item.company_name}</span>
                <span className="text-text-faint">— {item.reason}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {/* §6 - one line about what happens to this run afterwards. Whether it survives a
          restart is the whole question a reader has here, so it is stated once, plainly,
          and not turned into a badge on every panel. */}
      <p className="text-[12px] leading-relaxed text-text-faint">
        {result.saved && result.reference ? (
          <>
            Saved as <span className="font-mono text-text-muted">{result.reference}</span> against your organisation
            and listed in{' '}
            <Link href="/history" className="link">
              analysis history
            </Link>
            .
          </>
        ) : (
          <>Kept for this session only. An operator&rsquo;s signed-in run is what stores an analysis.</>
        )}
      </p>

      {/* Ranked matches */}
      <Panel
        title={`Ranked reuse opportunities (${analysis.matches.length})`}
        subtitle={
          analysis.source.location_resolved === false
            ? `Location provided; exact geographic distance unavailable. Distance is neutral for every partner here, so this order rests on what the material, the quantity and the sector can carry.`
            : undefined
        }
        action={
          <Link href="/matches" className="text-[11px] link">
            Open all matches
          </Link>
        }
      >
        {analysis.matches.length === 0 ? (
          <p className="py-6 text-center text-[13px] leading-relaxed text-slate-500">
            No partner in the network can take this stream as it is stated. Widen the distance on the matches page, or
            publish its demand so the other side can answer.
          </p>
        ) : (
          <ol className="space-y-2">
            {analysis.matches.slice(0, 6).map((match, index) => (
              <li
                key={match.id}
                className="flex items-center gap-4 rounded-md border border-ink-700 bg-ink-900 p-3"
              >
                <span className="w-5 shrink-0 text-center font-mono text-xs text-slate-600">{index + 1}</span>
                <ScoreRing score={match.overall_score} size={56} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-100">{match.recipient.company_name}</p>
                  <p className="truncate text-[11px] text-slate-500">
                    {titleCase(match.recipient.sector)} · {distanceShort(match.distance_km)} ·{' '}
                    {match.required_quantity_range_t_per_month[0]}–{match.required_quantity_range_t_per_month[1]} t/mo
                  </p>
                  <p className="mt-1 truncate text-[11px] text-slate-500">✓ {match.reasons[0]}</p>
                </div>
                <div className="hidden shrink-0 text-right sm:block">
                  <p className="text-sm tabular-nums text-slate-200">{inr(match.estimated_value_inr_per_month)}</p>
                  <p className="text-[11px] tabular-nums text-slate-500">
                    {match.estimated_co2e_t_per_month} t CO₂e/mo
                  </p>
                  <span className={`chip mt-1 ${reuseTypeTone(match.reuse_type)}`}>
                    {REUSE_TYPE_LABEL[match.reuse_type]}
                  </span>
                </div>
                <Link href={`/matches/${match.id}`} className="btn-ghost shrink-0 py-1.5 text-xs">
                  View
                </Link>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      {/* Feature 1: this stream's routes, primary first, ranked by the mode. */}
      <Pathways analysisId={analysis.id} sort={mode} onSortChange={onModeChange} />

      {/* Feature 6: change quantity, cadence or place and re-run the same engine. */}
      <WhatIf analysis={analysis} sort={mode} />

      {/* §11 - several of those re-runs at once, so a decision has something to
          stand on instead of one number. Same engine, same safety layer per column. */}
      <ScenarioComparison analysis={analysis} />

      {/* Impact */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Available quantity"
          value={`${analysis.totals.available_t_per_month} t/mo`}
          hint={`${SOURCE_SECTOR_LABEL[analysis.source.source_type]} · ${analysis.source.location}${
            analysis.source.location_resolved === false ? ' · distance not available' : ''
          }`}
        />
        <Metric
          label="Potential diversion"
          value={`${analysis.totals.allocated_t_per_month} t/mo`}
          hint={`${analysis.totals.potential_matches} ranked matches`}
          accent
        />
        <Metric
          label="Est. economic value"
          value={inr(analysis.totals.estimated_value_inr_per_month)}
          hint="per month · estimated"
        />
        <Metric
          label="Est. CO₂e avoided"
          value={`${analysis.totals.estimated_co2e_avoided_t_per_month} t/mo`}
          hint={`factor ${analysis.totals.co2e_factor_used_t_per_tonne} t/t`}
          accent
        />
      </div>

      {/* §12 - a reading aid for the knowledge base, next to the material the run
          resolved to. It cannot touch a score or a safety decision. */}
      {analysis.material.id !== 'unknown_material' && (
        <SimilarityPanel materialId={analysis.material.id} materialName={analysis.material.name} />
      )}

      <p className="text-[11px] text-text-faint">Analysed {relativeTime(analysis.created_at)}</p>
    </div>
  );
}