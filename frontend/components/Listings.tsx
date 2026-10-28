'use client';

/**
 * §6 - the marketplace view.
 *
 * One rule shapes this whole component: a listing is a claim about the world, so the
 * only listings here come from the seeded records or from a person filling in this form.
 * The publish button posts to `POST /api/listings`, which validates every field and
 * refuses anything it cannot stand behind - the form has no client-side validator that
 * could disagree with it, and nothing here lets a model draft an entry.
 *
 * "Find counterparties" is also not a second matcher. The fit column is the listing-to-
 * listing comparison, and the engine rows underneath it are the same deterministic
 * ranking the matches page shows, safety layer included.
 */

import { useMemo, useState } from 'react';

import { Empty, Notice, OriginChip, Panel, Section, SymbioButton, StatusBadge, type Tone } from '@/components/ui';
import { ApiError, api } from '@/lib/api';
import {
  inr,
  REUSE_TYPE_LABEL,
  reuseTypeTone,
  titleCase,
  distanceShort,
 } from '@/lib/format';
import type { Listing, ListingCounterparty, ListingEngineMatch, ListingMatchResponse, ListingPayload } from '@/lib/types';

const KIND_TONE: Record<string, Tone> = { demand: 'teal', supply: 'amber' };

/** The heading of the publish form, per stage. One line, so the form never has to
    explain itself in a paragraph. */
const STEPS: Record<'draft' | 'review', string> = {
  draft: 'State the material, the tonnage and the terms. Values are checked against the record they belong to.',
  review: 'Step two: publish this as stated, then see who in the network it matches.',
};

/**
 * One card for both sides of the marketplace. The verbs differ - a receiver says what
 * it will take and pay, a source says what it produces and asks - so those two wordings
 * are the only thing a `kind` switch changes. Layout, provenance and the match action
 * stay shared, which is what keeps the two sides honest against each other.
 */
function ListingCard({
  listing,
  onMatch,
  busy,
}: {
  listing: Listing;
  onMatch: (listing: Listing) => void;
  busy: boolean;
}) {
  const demand = listing.kind === 'demand';
  const price = demand ? listing.offer_price_inr_per_tonne : listing.asking_price_inr_per_tonne;
  return (
    <article className="flex h-full flex-col justify-between rounded-card border border-line bg-surface px-4 py-3.5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="tag-label">{demand ? 'Demand · material needed' : 'Supply · available material'}</span>
          <StatusBadge tone={KIND_TONE[listing.kind]}>{demand ? 'Wanted' : 'Offered'}</StatusBadge>
          <span className="chip chip-muted capitalize">{listing.status}</span>
        </div>
        <p className="mt-2 text-[15px] font-semibold leading-snug text-text-strong">{listing.party_name}</p>
        <p className="mt-0.5 text-[11px] text-text-faint">
          {titleCase(listing.party_sector)} · {listing.location ?? 'location not stated'}
        </p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {listing.material_names.map((material) => (
            <li key={material} className="chip chip-teal">
              {material}
            </li>
          ))}
        </ul>
        <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-line pt-2.5 text-[11px]">
          <Row label={demand ? 'Needed' : 'Available'} value={`${listing.quantity_t_per_month} t/mo`} />
          <Row label="Frequency" value="monthly" />
          <Row label={demand ? 'Pays' : 'Asks'} value={price ? `${inr(price)}/t` : 'not stated'} />
          <Row label="Within" value={`${listing.max_distance_km} km`} />
          {listing.quantity_window_t_per_month && (
            <Row
              label="Window"
              value={`${listing.quantity_window_t_per_month[0]}–${listing.quantity_window_t_per_month[1]} t`}
            />
          )}
        </dl>
        {(listing.processing_capability?.length ?? 0) > 0 && (
          <p className="mt-1.5 text-[11px] leading-snug text-text-faint">
            {demand
              ? `Can do: ${(listing.processing_capability ?? []).map((step) => step.replace(/_/g, ' ')).join(', ')}`
              : ''}
            {listing.kind === 'supply' ? `Arrives from ${titleCase(listing.party_sector)} operations` : ''}
          </p>
        )}
        {Object.keys(listing.requirements).length > 0 && (
          <p className="mt-1.5 text-[11px] leading-snug text-text-muted">{requirements(listing)}</p>
        )}
        <div className="mt-2.5 border-t border-line pt-2">
          <p className="tag-label">Intended use</p>
          <p className="mt-1 text-[11px] leading-snug text-text-muted">
            {listing.notes || (demand ? 'No handling terms stated.' : `Arrives from ${titleCase(listing.party_sector)} operations.`)}
          </p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <OriginChip
          origin={listing.origin === 'seed' ? 'knowledge_base' : 'user'}
          label={listing.origin === 'seed' ? 'Partner record' : 'Session listing'}
          title={
            listing.origin === 'seed'
              ? 'Drawn from the stated capacity on this partner\'s record'
              : 'Published in this session, not carried over between sessions'
          }
        />
        <button type="button" className="btn-quiet btn-sm" onClick={() => onMatch(listing)} disabled={busy}>
          Find counterparties
        </button>
      </div>
    </article>
  );
}

export function DemandCard(props: Parameters<typeof ListingCard>[0]) {
  return <ListingCard {...props} />;
}

export function SupplyCard(props: Parameters<typeof ListingCard>[0]) {
  return <ListingCard {...props} />;
}

export default function Marketplace({
  initial,
  materials,
  partners,
}: {
  initial: ListingPayload;
  materials: { id: string; name: string }[];
  partners: { id: string; name: string; kind: 'demand' | 'supply' }[];
}) {
  const [payload, setPayload] = useState(initial);
  const [kind, setKind] = useState<'' | 'demand' | 'supply'>('');
  const [materialId, setMaterialId] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [match, setMatch] = useState<{ listing: Listing; result: ListingMatchResponse } | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const visible = useMemo(
    () =>
      payload.listings.filter(
        (listing) => (!kind || listing.kind === kind) && (!materialId || listing.material_ids.includes(materialId)),
      ),
    [payload.listings, kind, materialId],
  );

  const load = async (nextKind: string, nextMaterial: string) => {
    try {
      setPayload(await api.listings({ kind: (nextKind || undefined) as 'demand' | 'supply', material_id: nextMaterial || undefined }));
    } catch (error) {
      setMatchError(error instanceof Error ? error.message : 'Could not load listings');
    }
  };

  const findCounterparties = async (listing: Listing) => {
    setBusy(listing.id);
    setMatchError(null);
    setMatch(null);
    try {
      setMatch({ listing, result: await api.matchListing({ listing_id: listing.id }) });
    } catch (error) {
      setMatchError(error instanceof Error ? error.message : 'The comparison could not be run.');
    } finally {
      setBusy(null);
    }
  };

  const balance = payload.stats.by_material;
  const widest = Math.max(1, ...balance.map((row) => Math.max(row.demand_t_per_month, row.supply_t_per_month)));

  return (
    <div className="space-y-4">
      <Section
        title="Open listings"
        subtitle={`${payload.count} listings in the network · ${payload.stats.session_published} published in this session`}
        divided
        action={
          <SymbioButton variant={showForm ? 'ghost' : 'primary'} size="sm" onClick={() => setShowForm((open) => !open)}>
            {showForm ? 'Close' : 'Publish a listing'}
          </SymbioButton>
        }
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <span className="label mb-1 block">Side of the market</span>
              <div role="group" aria-label="Side of the market" className="flex">
                {([
                  ['', 'All listings'],
                  ['demand', 'Material needed'],
                  ['supply', 'Available material'],
                ] as const).map(([value, label], index) => (
                  <button
                    key={value || 'both'}
                    type="button"
                    aria-pressed={kind === value}
                    onClick={() => {
                      const next = value as '' | 'demand' | 'supply';
                      setKind(next);
                      void load(next, materialId);
                    }}
                    className={`border border-line px-2.5 py-1.5 text-[12px] transition-colors first:rounded-l-card last:rounded-r-card ${
                      index > 0 ? '-ml-px' : ''
                    } ${
                      kind === value
                        ? 'bg-surface-muted font-medium text-text-strong'
                        : 'bg-surface text-text-muted hover:text-text-strong'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <label className="block">
              <span className="label mb-1 block">Material</span>
              <select
                className="input min-w-[190px]"
                value={materialId}
                onChange={(event) => {
                  setMaterialId(event.target.value);
                  void load(kind, event.target.value);
                }}
              >
                <option value="">Any material</option>
                {balance.map((row) => (
                  <option key={row.material_id} value={row.material_id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="pb-2 text-[11px] leading-snug text-text-faint">
              A listing is one party&#39;s stated need or offer, with the price and tonnage from that party&#39;s own
              record. Nothing here is a tender or a quotation.
            </p>
          </div>

          {visible.length === 0 ? (
            <Empty
              title="No listings match both filters"
              hint="Clear one filter, or publish a listing for this material to widen the network."
            />
          ) : (
            <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {visible.map((listing) => (
                <li key={listing.id}>
                  {listing.kind === 'demand' ? (
                    <DemandCard listing={listing} onMatch={findCounterparties} busy={busy !== null} />
                  ) : (
                    <SupplyCard listing={listing} onMatch={findCounterparties} busy={busy !== null} />
                  )}
                </li>
              ))}
            </ul>
          )}

          <div>
            <p className="label mb-1.5">Stated demand against stated supply · tonnes per month</p>
            <ul className="space-y-1">
              {balance.map((row) => (
                <li key={row.material_id} className="grid grid-cols-[minmax(120px,1fr)_2fr_auto] items-center gap-2 text-[11px]">
                  <span className="truncate text-text-muted">{row.name}</span>
                  <span className="flex h-3 items-center gap-0.5">
                    <span
                      className="h-full rounded-sm"
                      style={{ width: `${(row.demand_t_per_month / widest) * 50}%`, background: 'var(--primary-rgb)' }}
                      title={`demand ${row.demand_t_per_month} t/mo`}
                    />
                    <span
                      className="h-full rounded-sm"
                      style={{ width: `${(row.supply_t_per_month / widest) * 50}%`, background: 'var(--accent-rgb)' }}
                      title={`supply ${row.supply_t_per_month} t/mo`}
                    />
                  </span>
                  <span className="tabular-nums text-text-faint">
                    {row.demand_t_per_month} vs {row.supply_t_per_month} t
                    <span className={row.balance_t_per_month >= 0 ? 'ml-1.5 text-success' : 'ml-1.5 text-warning'}>
                      {row.balance_t_per_month >= 0 ? '+' : ''}
                      {row.balance_t_per_month}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[11px] leading-snug text-text-faint">
              Demand is what partners stated they can take; supply is what listed sources stated they produce. A
              positive balance means more supply than stated demand sits in this material.
            </p>
          </div>
        </div>
      </Section>

      {showForm && (
        <PublishForm
          materials={materials}
          partners={partners}
          onPublished={async (listing) => {
            setPayload(await api.listings({}));
            setKind('');
            setMaterialId('');
            void findCounterparties(listing);
          }}
        />
      )}

      {matchError && <Notice tone="danger">{matchError}</Notice>}

      {match && <MatchResult match={match} busy={busy === match.listing.id} />}
    </div>
  );
}

function MatchResult({
  match,
  busy,
}: {
  match: { listing: Listing; result: ListingMatchResponse };
  busy: boolean;
}) {
  const { result } = match;
  return (
    <Section
      title={`Counterparties for ${match.listing.party_name}`}
      subtitle={`${result.counterparty_count} listing-to-listing fit${
        result.counterparty_count === 1 ? '' : 's'
      } · ${result.engine_match_count} engine match${result.engine_match_count === 1 ? '' : 'es'} · ${result.listing_source}`}
      divided
    >
      {busy ? (
        <p className="text-xs text-text-muted">Comparing both sides…</p>
      ) : (
        <div className="space-y-5">
          <ul className="divide-y divide-line">
            {result.counterparties.map((row: ListingCounterparty) => (
              <li key={row.listing.id} className="py-2.5 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-xs font-medium text-text">
                    {row.listing.party_name}
                    <span className="ml-2 font-normal text-text-faint">
                      {row.listing.kind === 'demand' ? 'wants' : 'offers'} {row.listing.material_names.join(', ')}
                    </span>
                  </p>
                  <p className="text-[11px] tabular-nums text-text-muted">
                    Fit {row.fit.toFixed(1)} · {distanceShort(row.distance_km)} ·{' '}
                    {row.within_stated_range === null
                      ? 'range not comparable without coordinates'
                      : row.within_stated_range
                        ? 'inside the stated range'
                        : 'outside the stated range'}
                  </p>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-text-faint">
                  {Object.entries(row.fit_components).map(([key, value]) => (
                    <span key={key} className="tabular-nums">
                      {titleCase(key.replace(/_/g, ' '))} {(value * 100).toFixed(0)}%
                      <span className="text-text-faint"> of {((row.weights_used[key] ?? 0) * 100).toFixed(0)}</span>
                    </span>
                  ))}
                  <span className="text-text-muted">{row.scored_by}</span>
                </div>
                {Object.keys(row.gap).length > 0 && (
                  <p className="mt-1 text-[11px] leading-snug text-warning">
                    to close it:{' '}
                    {Object.entries(row.gap)
                      .map(([key, value]) => `${key.replace(/_/g, ' ')} ${typeof value === 'number' ? value.toLocaleString('en-IN') : value}`)
                      .join(' · ')}
                  </p>
                )}
              </li>
            ))}
            {result.counterparties.length === 0 && (
              <li className="py-2.5 text-[11px] leading-relaxed text-text-faint">
                No other listing states this material. Publishing the other side of it is what opens the route.
              </li>
            )}
          </ul>

          <div>
            <p className="label mb-1.5">Same partners, ranked by the matching engine</p>
            <ul className="space-y-1">
              {result.engine_matches.map((row: ListingEngineMatch) => (
                <li key={row.id} className="flex flex-wrap items-baseline justify-between gap-2 text-[11px]">
                  <span className="text-text-muted">
                    {row.recipient.company_name}
                    <span className="ml-1.5 text-text-faint">{REUSE_TYPE_LABEL[row.reuse_type]}</span>
                  </span>
                  <span className="flex items-center gap-2 tabular-nums text-text-faint">
                    <StatusBadge tone={reuseTypeTone(row.reuse_type) as Tone}>{row.reuse_type.replace(/_/g, ' ').toLowerCase()}</StatusBadge>
                    {row.overall_score.toFixed(1)} · {distanceShort(row.distance_km)} ·{' '}
                    {inr(row.estimated_value_inr_per_month)}/mo
                    {row.transport && (
                      <span title={row.transport.status_label}> · freight {inr(row.transport.transport_cost_inr_per_month)}</span>
                    )}
                    <span className="chip chip-muted">{row.scored_by}</span>
                  </span>
                </li>
              ))}
              {result.engine_matches.length === 0 && (
                <li className="text-[11px] leading-relaxed text-text-faint">
                  No partner in the network can take this stream as it is stated.
                </li>
              )}
            </ul>
          </div>

          {result.excluded_by_safety.length > 0 && (
            <Notice tone="danger">
              <span className="font-medium">Refused by the safety layer: </span>
              {result.excluded_by_safety.map((row) => `${row.company_name} — ${row.reason}`).join('; ')}
            </Notice>
          )}

          <p className="text-[11px] leading-relaxed text-text-faint">{result.note}</p>
        </div>
      )}
    </Section>
  );
}

function PublishForm({
  materials,
  partners,
  onPublished,
}: {
  materials: { id: string; name: string }[];
  partners: { id: string; name: string; kind: 'demand' | 'supply' }[];
  onPublished: (listing: Listing) => void | Promise<void>;
}) {
  const [form, setForm] = useState({
    kind: 'supply' as 'demand' | 'supply',
    party_id: '',
    material_ids: [] as string[],
    quantity_t_per_month: '',
    price: '',
    max_distance_km: '',
    notes: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Three steps, all of them real: the form is checked by the browser, the review
  // screen shows the exact record that is about to exist, and publishing hands
  // straight to the counterparty comparison, so the last step is not a promise.
  const [stage, setStage] = useState<'draft' | 'review'>('draft');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (stage === 'draft') {
      setError(null);
      setFieldErrors({});
      setStage('review');
      return;
    }
    setBusy(true);
    setError(null);
    setDone(null);
    const priceKey = form.kind === 'demand' ? 'offer_price_inr_per_tonne' : 'asking_price_inr_per_tonne';
    try {
      const response = await api.publishListing({
        kind: form.kind,
        party_id: form.party_id || null,
        material_ids: form.material_ids,
        quantity_t_per_month: Number(form.quantity_t_per_month),
        max_distance_km: form.max_distance_km ? Number(form.max_distance_km) : null,
        [priceKey]: form.price ? Number(form.price) : null,
        notes: form.notes || null,
      });
      setDone(
        `${response.listing.party_name} · ${response.listing.material_names.join(', ')} · ` +
          `${response.listing.quantity_t_per_month} t per month · published. Counterparties are ranked below.`,
      );
      setStage('draft');
      await onPublished(response.listing);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The listing could not be published. Try again.');
      setFieldErrors(err instanceof ApiError ? (err.fieldErrors ?? {}) : {});
      setStage('draft');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Publish a listing"
      subtitle={STEPS[stage]}
    >
      <form className="space-y-3" onSubmit={submit}>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="label mb-1 block">Side</span>
            <select className="input" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as 'demand' | 'supply' })}>
              <option value="supply">Supply — available material</option>
              <option value="demand">Demand — material needed</option>
            </select>
          </label>
          <label className="block">
            <span className="label mb-1 block">Party</span>
            <select
              className="input"
              value={form.party_id}
              onChange={(event) => setForm({ ...form, party_id: event.target.value })}
            >
              <option value="">Choose the party this is stated for</option>
              {partners
                .filter((partner) => partner.kind === form.kind)
                .map((partner) => (
                  <option key={partner.id} value={partner.id}>
                    {partner.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="block">
            <span className="label mb-1 block">Quantity t/month</span>
            <input
              className="input"
              inputMode="decimal"
              value={form.quantity_t_per_month}
              onChange={(event) => setForm({ ...form, quantity_t_per_month: event.target.value })}
              placeholder="12"
              required
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">{form.kind === 'demand' ? 'Offering ₹/tonne' : 'Asking ₹/tonne'}</span>
            <input
              className="input"
              inputMode="decimal"
              value={form.price}
              onChange={(event) => setForm({ ...form, price: event.target.value })}
              placeholder="optional"
            />
          </label>
        </div>

        <fieldset className="rounded-card border border-line px-3 py-2">
          <legend className="label px-1">Materials</legend>
          <div className="flex flex-wrap gap-1.5">
            {materials.map((material) => {
              const on = form.material_ids.includes(material.id);
              return (
                <button
                  type="button"
                  key={material.id}
                  className={`chip ${on ? 'chip-teal' : 'chip-muted'}`}
                  onClick={() =>
                    setForm({
                      ...form,
                      material_ids: on
                        ? form.material_ids.filter((id) => id !== material.id)
                        : [...form.material_ids, material.id],
                    })
                  }
                >
                  {material.name}
                </button>
              );
            })}
          </div>
          <p className="mt-1.5 text-[11px] text-text-faint">
            Only knowledge-base materials can be listed, and a demand listing is refused if the chosen partner does not
            already record that material in its accepted list.
          </p>
        </fieldset>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="label mb-1 block">Max distance km</span>
            <input
              className="input"
              inputMode="decimal"
              value={form.max_distance_km}
              onChange={(event) => setForm({ ...form, max_distance_km: event.target.value })}
              placeholder="optional"
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">Notes for the other side</span>
            <input
              className="input"
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              placeholder="gate tests, cadence, packaging"
            />
          </label>
        </div>

        {stage === 'review' && (
          <div className="rounded-card border border-line bg-surface-inset px-3.5 py-3">
            <p className="tag-label">Review before publishing</p>
            <dl className="mt-2 grid gap-x-6 gap-y-1 text-[11px] sm:grid-cols-2">
              <Row label={form.kind === 'demand' ? 'Needed' : 'Available'} value={`${form.quantity_t_per_month} t/mo`} />
              <Row label="Frequency" value="monthly" />
              <Row
                label={form.kind === 'demand' ? 'Offering' : 'Asking'}
                value={form.price ? `${inr(Number(form.price))}/t` : 'not stated'}
              />
              <Row label="Within" value={form.max_distance_km ? `${form.max_distance_km} km` : 'no ceiling stated'} />
              <Row label="Materials" value={form.material_ids.length ? form.material_ids.join(', ') : 'none chosen'} />
              <Row
                label="Party"
                value={partners.find((partner) => partner.id === form.party_id)?.name ?? 'not chosen'}
              />
            </dl>
            {form.notes && <p className="mt-2 text-[11px] leading-snug text-text-muted">{form.notes}</p>}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2.5">
          {stage === 'review' && (
            <SymbioButton type="button" variant="ghost" size="sm" onClick={() => setStage('draft')} disabled={busy}>
              Edit details
            </SymbioButton>
          )}
          <SymbioButton type="submit" size="sm" disabled={busy}>
            {stage === 'draft'
              ? 'Review listing'
              : busy
                ? 'Publishing…'
                : form.kind === 'demand'
                  ? 'Publish demand'
                  : 'Publish supply'}
          </SymbioButton>
          <span className="text-[11px] leading-snug text-text-faint">
            Applies to this session only; a published listing is matched against the network, not sent to anyone.
          </span>
        </div>

        {Object.values(fieldErrors).length > 0 && (
          <ul className="space-y-1 text-[11px] leading-snug text-danger">
            {Object.entries(fieldErrors).map(([field, message]) => (
              <li key={field}>{message}</li>
            ))}
          </ul>
        )}
        {error && <Notice tone="danger">{error}</Notice>}
        {done && <Notice tone="success">{done}</Notice>}
      </form>
    </Panel>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-text-faint">{label}</dt>
      <dd className="text-right tabular-nums text-text">{value}</dd>
    </>
  );
}

function requirements(listing: Listing): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(listing.requirements)) {
    const label = titleCase(key.replace(/_/g, ' '));
    parts.push(Array.isArray(value) ? `${label}: ${value.map(String).join(', ')}` : `${label} ${value}`);
  }
  return parts.length ? `Conditions · ${parts.join(' · ')}` : '';
}
