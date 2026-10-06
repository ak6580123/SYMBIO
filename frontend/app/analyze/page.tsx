'use client';

import Link from 'next/link';
import { useState } from 'react';

import FileDrop from '@/components/FileDrop';
import { ConfidenceBar, DemoTag, Metric, Notice, Panel, ScoreRing, Spinner } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import {
  inr,
  REUSE_TYPE_LABEL,
  relativeTime,
  reuseTypeTone,
  SAFETY_LABEL,
  safetyTone,
  SOURCE_SECTOR_LABEL,
  titleCase,
} from '@/lib/format';
import type { AnalyzeResponse, SourceSector, UploadResponse } from '@/lib/types';

const UNITS = ['tonnes', 'kg', 'litres', 'units'];
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
    },
  },
];

export default function AnalyzePage() {
  const [form, setForm] = useState<FormState>({
    source_type: 'industry',
    material_description: '',
    quantity: '5',
    unit: 'tonnes',
    location: 'Chennai, Tamil Nadu',
    frequency: 'monthly',
    composition: '',
  });
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  const set = (key: keyof FormState, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }) as FormState);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const quantity = Number(form.quantity);
      if (!form.material_description.trim()) throw new ApiError(422, 'Describe the material first.');
      if (!Number.isFinite(quantity) || quantity <= 0) throw new ApiError(422, 'Enter a quantity greater than zero.');

      const response = await api.analyze({
        source_type: form.source_type,
        material_description: form.material_description.trim(),
        quantity,
        unit: form.unit,
        location: form.location.trim() || 'Chennai, Tamil Nadu',
        frequency: form.frequency,
        composition: form.composition.trim() || null,
        attached_text: upload?.extracted_text || null,
        attached_filename: upload?.filename || null,
      });
      setResult(response);
      document.getElementById('result')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-100">Analyze Waste</h1>
          <p className="mt-1 text-sm text-slate-500">
            Describe the stream in plain language. Symbio identifies the material and ranks who could use it.
          </p>
        </div>
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
      </header>

      <form onSubmit={submit} className="panel p-5">
        <div className="grid gap-4 lg:grid-cols-2">
          <Field label="Waste source type">
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
          </Field>

          <Field label="Location">
            <input
              className="input"
              value={form.location}
              onChange={(e) => set('location', e.target.value)}
              placeholder="e.g. Manali, Chennai"
            />
          </Field>

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

          <Field label="Composition (optional)">
            <input
              className="input"
              value={form.composition}
              onChange={(e) => set('composition', e.target.value)}
              placeholder="SiO2: 55%, Al2O3: 25%, CaO: 8%"
            />
          </Field>

          <Field label="Report upload (optional)">
            <FileDrop onExtracted={setUpload} />
          </Field>
        </div>

        <div className="mt-5 flex items-center gap-3 border-t border-ink-700 pt-4">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Analyzing…' : 'Analyze with Symbio'}
          </button>
          <p className="text-[11px] text-slate-600">
            Quantities are normalised to tonnes per month. Identification runs locally.
          </p>
        </div>
      </form>

      {loading && (
        <div className="panel panel-pad">
          <Spinner label="Identifying material and scoring recipients…" />
        </div>
      )}

      {error && <Notice tone="danger">{error}</Notice>}

      {result && <Result result={result} />}

      <div id="result" />
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">
        {label}
        {required && <span className="text-accent"> *</span>}
      </span>
      {children}
    </label>
  );
}

function Result({ result }: { result: AnalyzeResponse }) {
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

      {/* Impact */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Available quantity"
          value={`${analysis.totals.available_t_per_month} t/mo`}
          hint={`${SOURCE_SECTOR_LABEL[analysis.source.source_type]} · ${analysis.source.location}`}
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
          hint="per month · demo calculation"
        />
        <Metric
          label="Est. CO₂e avoided"
          value={`${analysis.totals.estimated_co2e_avoided_t_per_month} t/mo`}
          hint={`factor ${analysis.totals.co2e_factor_used_t_per_tonne} t/t · demo`}
          accent
        />
      </div>

      {/* Ranked matches */}
      <Panel
        title={`Ranked reuse opportunities (${analysis.matches.length})`}
        action={
          <Link href="/matches" className="text-[11px] text-accent hover:underline">
            Open all matches
          </Link>
        }
      >
        {analysis.matches.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
            No compatible recipient in the demo dataset for this stream.
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
                    {titleCase(match.recipient.sector)} · {match.distance_km} km ·{' '}
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

      {analysis.excluded.length > 0 && (
        <Panel title={`Excluded by the safety layer (${analysis.excluded.length})`}>
          <p className="mb-3 text-xs text-slate-500">
            These recipients were removed before scoring. The rule-based safety layer refuses hazardous and
            unidentified streams for casual end uses.
          </p>
          <ul className="max-h-48 space-y-1 overflow-y-auto pr-1">
            {analysis.excluded.slice(0, 12).map((item) => (
              <li key={`${item.recipient_id}-${item.reason}`} className="flex gap-2 text-[11px] leading-relaxed">
                <span className="shrink-0 font-medium text-slate-400">{item.company_name}</span>
                <span className="text-slate-600">— {item.reason}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <p className="flex items-center gap-2 text-[11px] text-slate-600">
        <DemoTag /> Analyzed {relativeTime(analysis.created_at)} · id {analysis.id}
      </p>
    </div>
  );
}
