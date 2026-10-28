'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useMemo, useState } from 'react';

import { CompareTable, MATCH_COLUMNS } from '@/components/Compare';
import { TransportChip } from '@/components/TransportPanel';
import { Empty, ErrorState, PageHeader, ScoreRing, Section, SymbioButton, Spinner } from '@/components/ui';
import { api } from '@/lib/api';
import {
  inr,
  OPTIMIZATION_MODES,
  REUSE_TYPE_LABEL,
  reuseTypeTone,
  SAFETY_LABEL,
  titleCase,
  distanceShort,
  distanceFrom,
 } from '@/lib/format';
import type { MatchCard, MatchSort, PartnerType, SafetyLevel } from '@/lib/types';

// Every option here has a matching value on the backend, so a filter can never
// quietly select nothing.
const REUSE_OPTIONS = ['DIRECT_REUSE', 'REQUIRES_PROCESSING', 'INDUSTRIAL_ONLY', 'RESTRICTED', 'UNKNOWN'];
const SAFETY_OPTIONS: SafetyLevel[] = ['low', 'moderate', 'high', 'hazardous', 'unknown'];
const PARTNER_OPTIONS: { value: PartnerType; label: string }[] = [
  { value: 'industry', label: 'Industry' },
  { value: 'sme', label: 'SME / artisan' },
  { value: 'recycler', label: 'Recycler' },
  { value: 'processing', label: 'Processing / recovery' },
  { value: 'agriculture', label: 'Agriculture' },
  { value: 'community', label: 'Community' },
];
/** The six engine factors, named the way a person reads them. */
const FACTOR_LABEL: Record<string, string> = {
  compatibility: 'Material',
  quantity: 'Quantity',
  location: 'Distance',
  sector: 'Sector',
  value: 'Value',
  environmental: 'CO₂e',
};

/**
 * A history row arrives as `/matches?analysis=<id>` so a stored run opens without
 * anybody hunting for it in the select. `useSearchParams` needs a boundary, because a
 * prerendered page has no query string to read.
 */
export default function MatchesPage() {
  return (
    <Suspense fallback={<Spinner label="Loading matches…" />}>
      <MatchesView />
    </Suspense>
  );
}

function MatchesView() {
  const [filters, setFilters] = useState({
    sector: '',
    max_distance_km: '',
    min_match_score: '0',
    min_quantity: '',
    reuse_type: '',
    processing: '',
    min_estimated_value: '',
    safety_level: '',
    partner_type: '',
  });
  const [sort, setSort] = useState<MatchSort>('score');
  const [analysisId, setAnalysisId] = useState('');
  const [analyses, setAnalyses] = useState<{ id: string; material: string }[]>([]);
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [sectors, setSectors] = useState<{ sector: string; label: string }[]>([]);
  const [meta, setMeta] = useState({ count: 0, filtered_from: 0 });
  /** The backend's own explanation when a mode cannot change the order. */
  const [sortNote, setSortNote] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped by "Try again" so a failed fetch can be re-run without touching a filter.
  const [attempt, setAttempt] = useState(0);
  const params = useSearchParams();
  const requested = params.get('analysis');

  useEffect(() => {
    if (requested) setAnalysisId(requested);
  }, [requested]);

  useEffect(() => {
    api
      .recipients()
      .then((data) => setSectors(data.sectors))
      .catch(() => setSectors([]));
    api
      .analyses()
      .then((data) => setAnalyses(data.analyses))
      .catch(() => setAnalyses([]));
  }, []);

  // Debounced so dragging the distance slider does not hammer the API.
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true);
      api
        .matches({
          analysis_id: analysisId || undefined,
          sector: filters.sector || undefined,
          max_distance_km: filters.max_distance_km ? Number(filters.max_distance_km) : undefined,
          min_match_score: Number(filters.min_match_score) || 0,
          min_quantity: filters.min_quantity ? Number(filters.min_quantity) : undefined,
          reuse_type: filters.reuse_type || undefined,
          processing: filters.processing || undefined,
          min_estimated_value: filters.min_estimated_value ? Number(filters.min_estimated_value) : undefined,
          safety_level: filters.safety_level || undefined,
          partner_type: filters.partner_type || undefined,
          sort,
        })
        .then((data) => {
          setMatches(data.matches);
          setMeta({ count: data.count, filtered_from: data.filtered_from });
          setSortNote(data.sort_note);
          // A selection that a filter just emptied must not silently compare
          // partners that are no longer on screen.
          setSelected((prev) => prev.filter((id) => data.matches.some((m) => m.id === id)));
          setError(null);
        })
        .catch((err) => setError(err instanceof Error ? err.message : 'Could not load matches'))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [filters, sort, analysisId, attempt]);

  const set = (key: string, value: string) => setFilters((prev) => ({ ...prev, [key]: value }));
  const reset = () => {
    setFilters({
      sector: '',
      max_distance_km: '',
      min_match_score: '0',
      min_quantity: '',
      reuse_type: '',
      processing: '',
      min_estimated_value: '',
      safety_level: '',
      partner_type: '',
    });
    setSort('score');
    setAnalysisId('');
  };

  const active =
    Object.values(filters).some((v) => v !== '' && v !== '0') || sort !== 'score' || analysisId !== '';
  const modeNote = OPTIMIZATION_MODES.find((option) => option.value === sort)?.note ?? '';
  const compared = selected
    .map((id) => matches.find((match) => match.id === id))
    .filter((match): match is MatchCard => Boolean(match));

  const distanceMax = useMemo(() => Number(filters.max_distance_km) || 300, [filters.max_distance_km]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Opportunities"
        title="Matches"
        subtitle="Every partner who can take a stream, ranked by the deterministic engine. Changing the order changes what leads; it never changes a score."
        actions={<SymbioButton href="/analyze">Analyze a material</SymbioButton>}
      />

      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        {/* Filters */}
        <aside className="panel h-fit p-4 lg:sticky lg:top-20">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">Filters</h2>
            <button onClick={reset} className="text-[11px] text-slate-500 underline hover:text-slate-300">
              reset
            </button>
          </div>

          <div className="space-y-4">
            <FilterField label="Analysis">
              <select className="input" value={analysisId} onChange={(e) => setAnalysisId(e.target.value)}>
                <option value="">All analyses</option>
                {requested && !analyses.some((item) => item.id === requested) && (
                  <option value={requested}>Stored analysis</option>
                )}
                {analyses.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.material}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-600">
                One analysis ranks against every recipient in the network; all of them keeps the whole picture.
              </p>
            </FilterField>

            <FilterField label="Sector">
              <select className="input" value={filters.sector} onChange={(e) => set('sector', e.target.value)}>
                <option value="">All sectors</option>
                {sectors.map((s) => (
                  <option key={s.sector} value={s.sector}>
                    {s.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label={`Maximum distance · ${filters.max_distance_km || 300} km`}>
              <input
                type="range"
                min={5}
                max={300}
                step={5}
                value={distanceMax}
                onChange={(e) => set('max_distance_km', e.target.value)}
                className="w-full accent-emerald-400"
              />
            </FilterField>

            <FilterField label={`Minimum match score · ${filters.min_match_score}%`}>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={Number(filters.min_match_score)}
                onChange={(e) => set('min_match_score', e.target.value)}
                className="w-full accent-emerald-400"
              />
            </FilterField>

            <FilterField label="Minimum quantity (t/month)">
              <input
                type="number"
                min={0}
                step="0.5"
                className="input"
                value={filters.min_quantity}
                onChange={(e) => set('min_quantity', e.target.value)}
                placeholder="any"
              />
            </FilterField>

            <FilterField label="Reuse type">
              <select className="input" value={filters.reuse_type} onChange={(e) => set('reuse_type', e.target.value)}>
                <option value="">Any</option>
                {REUSE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {REUSE_TYPE_LABEL[option as keyof typeof REUSE_TYPE_LABEL]}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Safety / use category">
              <select
                className="input"
                value={filters.safety_level}
                onChange={(e) => set('safety_level', e.target.value)}
              >
                <option value="">Any</option>
                {SAFETY_OPTIONS.map((level) => (
                  <option key={level} value={level}>
                    {SAFETY_LABEL[level]} handling
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Recipient type">
              <select
                className="input"
                value={filters.partner_type}
                onChange={(e) => set('partner_type', e.target.value)}
              >
                <option value="">Any</option>
                {PARTNER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Processing">
              <select className="input" value={filters.processing} onChange={(e) => set('processing', e.target.value)}>
                <option value="">Any</option>
                <option value="direct">Direct reuse only</option>
                <option value="processing_required">Processing required</option>
              </select>
            </FilterField>

            <FilterField label="Minimum est. value (₹/month)">
              <input
                type="number"
                min={0}
                step={500}
                className="input"
                value={filters.min_estimated_value}
                onChange={(e) => set('min_estimated_value', e.target.value)}
                placeholder="any"
              />
            </FilterField>
          </div>
        </aside>

        {/* Results */}
        <div className="space-y-3">
          {/* Optimisation modes: the control that decides what "best" means. */}
          <div className="border-b border-line pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="label">Rank these matches by</p>
              <p className="text-[11px] text-text-faint">
                same result set, same scores - only the order changes · {modeNote}
              </p>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Optimisation mode">
              {OPTIMIZATION_MODES.map((mode) => (
                <button
                  key={mode.value}
                  onClick={() => setSort(mode.value)}
                  title={mode.note}
                  aria-pressed={sort === mode.value}
                  className={`rounded-chip border px-2.5 py-1 text-[11px] transition-colors ${
                    sort === mode.value
                      ? 'border-transparent bg-accent-fill font-medium text-accent-ink'
                      : 'border-line text-text-muted hover:bg-surface-muted hover:text-text-strong'
                  }`}
                >
                  {mode.label}
                </button>
              ))}
            </div>
            {sortNote && <p className="caption mt-2">{sortNote}</p>}
          </div>

          <p className="text-xs text-text-faint">
            {loading ? 'Filtering…' : `${meta.count} of ${meta.filtered_from} matches`}
            {!loading && active ? ` · ${modeNote}` : ''}
          </p>

          {error && (
            <ErrorState
              title="Something went wrong while loading matches."
              hint={error}
              onRetry={() => setAttempt((n) => n + 1)}
              retryLabel="Try again"
            />
          )}

          {compared.length > 0 && (
            <div className="panel p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h2 className="card-title">Comparison {compared.length < 2 ? '' : `· ${compared.length} partners`}</h2>
                <button onClick={() => setSelected([])} className="text-[11px] text-text-faint underline hover:text-text-strong">
                  Clear
                </button>
              </div>
              <CompareTable
                rows={compared}
                columns={MATCH_COLUMNS}
                titleOf={(match) => match.company_name}
                subOf={(match) => `${match.sector_label} · ${distanceShort(match.distance_km)}`}
                onRemove={(index) => setSelected((prev) => prev.filter((_, i) => i !== index))}
              />
            </div>
          )}

          {loading ? (
            <div className="panel panel-pad">
              <Spinner label="Ranking partners…" />
            </div>
          ) : matches.length === 0 ? (
            <div className="panel">
              <Empty
                title="No compatible demand found"
                hint="Widen the distance or lower the minimum score. If nothing in the network can take this stream as it stands, publishing its demand is what opens a route."
                action={<SymbioButton href="/marketplace" variant="quiet" size="sm">Publish a listing</SymbioButton>}
              />
            </div>
          ) : (
            <div className="space-y-6">
              <LeadMatch match={matches[0]} mode={sort} />
              {matches.length > 1 && (
                <Section
                  title="Other pathways"
                  subtitle={`${matches.length - 1} more partner${matches.length - 1 === 1 ? '' : 's'} that can take this stream, in the same order.`}
                >
                  <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                    {matches.slice(1).map((match) => (
                      <MatchRow
                        key={match.id}
                        match={match}
                        checked={selected.includes(match.id)}
                        onToggle={(checked) =>
                          setSelected((prev) =>
                            checked ? [...prev, match.id].slice(-3) : prev.filter((id) => id !== match.id),
                          )
                        }
                      />
                    ))}
                  </ul>
                </Section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The lead. §8 asked for the best match to visually dominate, and the honest way to
 * do that is to give it the space the others do not need: the full reasoning, the
 * component bars, the freight verdict, and the two things you can do next.
 */
function LeadMatch({ match, mode }: { match: MatchCard; mode: MatchSort }) {
  return (
    <section className="rounded-card border border-line bg-surface px-5 py-4.5 sm:px-6 sm:py-5.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="tag-label text-brand-strong">Best opportunity</p>
        <p className="text-[11px] text-text-faint">
          ranked by {OPTIMIZATION_MODES.find((option) => option.value === mode)?.label.toLowerCase() ?? 'score'}
        </p>
      </div>
      <div className="mt-3 flex flex-wrap items-start gap-5">
        <ScoreRing score={match.score} size={96} />
        <div className="min-w-0 flex-1">
          <h2 className="text-[22px] font-semibold leading-tight text-text-strong">{match.company_name}</h2>
          <p className="mt-1 text-[12.5px] text-text-muted">
            {match.sector_label} · {match.location} · {distanceFrom(match.distance_km, match.source_location)}
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className={`chip ${reuseTypeTone(match.reuse_type)}`}>{REUSE_TYPE_LABEL[match.reuse_type]}</span>
            <span className="chip chip-slate">{match.partner_type_label}</span>
            <TransportChip estimate={match.transport} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2.5 border-t border-line pt-3 sm:grid-cols-4">
            <Cell label="Compatibility" value={`${match.score.toFixed(1)}%`} accent />
            <Cell label="Quantity" value={`${match.matched_quantity_t_per_month || match.available_quantity_t_per_month} t/mo`} />
            <Cell label="Est. value" value={`${inr(match.estimated_value_inr_per_month)}/mo`} />
            <Cell label="Est. CO₂e avoided" value={`${match.estimated_co2e_t_per_month} t/mo`} />
          </dl>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto">
          <SymbioButton href={`/matches/${match.id}`}>View match</SymbioButton>
          <SymbioButton href={`/map?analysis=${match.analysis_id}`} variant="ghost" size="sm">
            See it on the network
          </SymbioButton>
        </div>
      </div>

      <div className="mt-4 border-t border-line pt-3">
        <p className="tag-label">Why this match</p>
        <p className="mt-1.5 max-w-[76ch] text-[12.5px] leading-relaxed text-text-muted">{match.summary}</p>
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 lg:grid-cols-6">
          {Object.entries(match.breakdown)
            .filter(([factor]) => factor in FACTOR_LABEL)
            .map(([factor, value]) => (
              <div
                key={factor}
                title={`${titleCase(factor)} scored ${Math.round(value * 100)}% of the weight it carries`}
              >
                <div className="flex items-baseline justify-between text-[10px] text-text-faint">
                  <span>{FACTOR_LABEL[factor] ?? factor}</span>
                  <span className="tabular-nums text-text-muted">{Math.round(value * 100)}%</span>
                </div>
                <div className="mt-1 h-1 rounded-full bg-surface-muted">
                  <div className="h-1 rounded-full bg-brand" style={{ width: `${value * 100}%` }} />
                </div>
              </div>
            ))}
        </div>
      </div>
    </section>
  );
}

/**
 * Everything below the lead is a line, not a card. Ranking has to be visible in the
 * shape of the list, or "best" is just a word.
 */
function MatchRow({
  match,
  checked,
  onToggle,
}: {
  match: MatchCard;
  checked: boolean;
  onToggle: (checked: boolean) => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 hover:bg-surface-inset">
      <span className="w-11 shrink-0 text-right text-[15px] font-semibold tabular-nums text-text-strong">
        {match.score.toFixed(0)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13.5px] font-medium text-text-strong">{match.company_name}</p>
        <p className="mt-0.5 truncate text-[11px] text-text-faint">
          {match.material} · {match.sector_label} · {distanceShort(match.distance_km)} ·{' '}
          {match.available_quantity_t_per_month} t/mo · {inr(match.estimated_value_inr_per_month)}/mo
        </p>
      </div>
      <span className={`chip shrink-0 ${reuseTypeTone(match.reuse_type)}`}>{REUSE_TYPE_LABEL[match.reuse_type]}</span>
      <label className="flex shrink-0 items-center gap-1.5 text-[11px] text-text-faint" title="Compare this partner">
        <input
          type="checkbox"
          aria-label={`Compare ${match.company_name}`}
          className="accent-emerald-400"
          checked={checked}
          onChange={(event) => onToggle(event.target.checked)}
        />
        Compare
      </label>
      <Link href={`/matches/${match.id}`} className="btn-ghost btn-sm shrink-0">
        View
      </Link>
    </li>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

function Cell({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-slate-600">{label}</dt>
      <dd className={`truncate tabular-nums ${accent ? 'text-accent' : 'text-slate-300'}`}>{value}</dd>
    </div>
  );
}
