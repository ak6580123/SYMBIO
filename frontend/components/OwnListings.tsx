'use client';

/**
 * §6 - the listings this organisation published, and the only place they can be changed.
 *
 * These rows come from `GET /api/org/listings/mine`, which the server scopes to the
 * caller's organisation; there is no id in this file that could fetch another tenant's
 * listing, and the API answers 404 rather than 403 when one is tried.
 *
 * Three verbs, because three are needed: the number changes (edit), the material is not
 * available this month (pause), the stream has gone (close). Pausing and closing update
 * the row in place - a closed listing keeps its history and stops being advertised.
 */

import { useCallback, useEffect, useState } from 'react';

import { Empty, ErrorState, Notice, Panel, SymbioButton, Spinner, StatusBadge, type Tone } from '@/components/ui';
import { ApiError, api } from '@/lib/api';
import { distanceShort, inr, titleCase } from '@/lib/format';
import type { Listing, ListingPatch, MyListingsResponse } from '@/lib/types';

const LIFECYCLE_TONE: Record<string, Tone> = {
  active: 'teal',
  paused: 'amber',
  closed: 'muted',
};

const LIFECYCLE_TITLE: Record<string, string> = {
  active: 'Advertised on the marketplace',
  paused: 'Kept on the record, hidden from the marketplace',
  closed: 'Finished. The row stays so the history still reads correctly',
};

export default function OwnListings({ canWrite }: { canWrite: boolean }) {
  const [payload, setPayload] = useState<MyListingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setPayload(await api.myListings());
    } catch (err) {
      setPayload(null);
      setError(err instanceof ApiError ? err.message : 'The listings could not be read.');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function changeStatus(listing: Listing, status: 'active' | 'paused' | 'closed') {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await api.setListingStatus(listing.id, status);
      setNote(
        status === 'active'
          ? `${listing.material_names.join(', ')} is advertised again.`
          : status === 'paused'
            ? `${listing.material_names.join(', ')} is hidden from the marketplace and stays on your record.`
            : result.note || `${listing.material_names.join(', ')} is closed. The row and its history are kept.`
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'That change was not saved.');
    } finally {
      setBusy(false);
    }
  }

  if (busy && !payload) {
    return <Spinner label="Reading your listings…" />;
  }
  if (error && !payload) {
    return <ErrorState title="Your listings could not be read." hint={error} onRetry={load} />;
  }
  if (!payload || payload.listings.length === 0) {
    return (
      <Empty
        title="Nothing published by this organisation yet."
        hint="A listing is published from the marketplace. Once the database behind Symbio is configured, it survives a restart and appears here for editing."
      />
    );
  }

  return (
    <div className="space-y-3">
      {error && <ErrorState title="The last change did not go through." hint={error} onRetry={load} />}
      {note && <Notice tone="success">{note}</Notice>}
      {payload.persistence && !payload.persistence.reachable && (
        <Notice tone="warn">
          These rows are held for this session only: {payload.persistence.note}
        </Notice>
      )}
      <div className="space-y-2.5">
        {payload.listings.map((row) => {
          const listing = {
            ...row,
            lifecycle: row.lifecycle ?? 'active',
            location: row.location ?? '',
            location_resolved: row.location_resolved ?? false,
            frequency: row.frequency ?? 'monthly',
            application_use: row.application_use ?? '',
            notes: row.notes ?? '',
            material_names: row.material_names ?? [],
          };
          return (
          editing === listing.id ? (
            <EditListing
              key={listing.id}
              listing={listing}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSaved={async (message) => {
                setEditing(null);
                setNote(message);
                await load();
              }}
            />
          ) : (
            <Panel key={listing.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-text-strong">{listing.material_names.join(' · ')}</span>
                    <span className="chip chip-muted">{listing.kind === 'demand' ? 'Demand' : 'Supply'}</span>
                    <StatusBadge tone={LIFECYCLE_TONE[listing.lifecycle] ?? 'muted'} title={LIFECYCLE_TITLE[listing.lifecycle]}>
                      {titleCase(listing.lifecycle)}
                    </StatusBadge>
                    {!listing.persisted && (
                      <span className="chip chip-muted" title="Nothing was written to a database for this listing.">
                        Session listing
                      </span>
                    )}
                  </p>
                  <p className="mt-1.5 text-[12.5px] text-text-muted">
                    {listing.quantity_t_per_month} t/month · {listing.location}
                    {listing.max_distance_km ? ` · within ${distanceShort(listing.max_distance_km)}` : ''} ·{' '}
                    {listing.application_use ? titleCase(listing.application_use) : 'use not stated'} ·{' '}
                    {titleCase(listing.frequency)}
                  </p>
                  <p className="mt-1 text-[12px] text-text-faint">
                    {price(listing) !== null ? `${inr(price(listing) as number)}/t · ` : 'no price stated · '}
                    published {listing.created_at}
                    {listing.updated_at && listing.updated_at.slice(0, 10) !== listing.created_at
                      ? ` · changed ${listing.updated_at.slice(0, 10)}`
                      : ''}
                  </p>
                  {!listing.location_resolved && listing.location && (
                    <p className="mt-1 text-[12px] text-cherry">
                      Symbio could not place “{listing.location}” on a map, so no distance is quoted for it anywhere.
                    </p>
                  )}
                  {listing.notes && <p className="mt-1.5 max-w-[70ch] text-[12.5px] leading-relaxed text-text-muted">{listing.notes}</p>}
                </div>
                {canWrite && (
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <SymbioButton variant="ghost" size="sm" disabled={busy} onClick={() => setEditing(listing.id)}>
                      Edit
                    </SymbioButton>
                    {listing.lifecycle === 'active' ? (
                      <SymbioButton variant="ghost" size="sm" disabled={busy} onClick={() => void changeStatus(listing, 'paused')}>
                        Pause
                      </SymbioButton>
                    ) : (
                      <SymbioButton variant="ghost" size="sm" disabled={busy} onClick={() => void changeStatus(listing, 'active')}>
                        Resume
                      </SymbioButton>
                    )}
                    {listing.lifecycle !== 'closed' && (
                      <SymbioButton variant="quiet" size="sm" disabled={busy} onClick={() => void changeStatus(listing, 'closed')}>
                        Close
                      </SymbioButton>
                    )}
                  </div>
                )}
              </div>
            </Panel>
            )
          );
        })}
      </div>
    </div>
  );
}

/**
 * The edit form holds only what a publisher is allowed to change later. `kind`, the
 * material and who owns the row are not in it, because the API refuses them too - a
 * listing that changes what it is about is a different listing.
 */
function EditListing({
  listing,
  busy,
  onCancel,
  onSaved,
}: {
  listing: Listing;
  busy: boolean;
  onCancel: () => void;
  onSaved: (message: string) => void;
}) {
  const [form, setForm] = useState({
    quantity_t_per_month: String(listing.quantity_t_per_month ?? ''),
    price_inr_per_tonne: price(listing) === null ? '' : String(price(listing)),
    max_distance_km: String(listing.max_distance_km ?? ''),
    location: listing.location ?? '',
    frequency: listing.frequency ?? 'monthly',
    application_use: listing.application_use ?? '',
    notes: listing.notes ?? '',
  });
  const [fields, setFields] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);

  const set =
    (key: keyof typeof form) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFields({});
    setFailure(null);
    const body: ListingPatch = {};
    const number = (value: string) => (value.trim() === '' ? undefined : Number(value));
    const quantity = number(form.quantity_t_per_month);
    const price = number(form.price_inr_per_tonne);
    const distance = number(form.max_distance_km);
    if (quantity !== undefined) body.quantity_t_per_month = quantity;
    if (price !== undefined) body.price_inr_per_tonne = price;
    if (distance !== undefined) body.max_distance_km = distance;
    if (form.location.trim() !== (listing.location ?? '')) body.location = form.location.trim();
    if (form.frequency !== listing.frequency) body.frequency = form.frequency;
    if (form.application_use.trim() !== (listing.application_use ?? '')) body.application_use = form.application_use.trim();
    if (form.notes.trim() !== (listing.notes ?? '')) body.notes = form.notes.trim();
    try {
      const result = await api.editListing(listing.id, body);
      onSaved(result.changed.length ? `Saved: ${result.changed.map(titleCase).join(', ').toLowerCase()}.` : 'Saved. Nothing had changed.');
    } catch (err) {
      if (err instanceof ApiError) {
        setFields(err.fieldErrors ?? {});
        setFailure(Object.keys(err.fieldErrors ?? {}).length ? null : err.message);
      } else {
        setFailure('That change was not saved.');
      }
    }
  }

  return (
    <Panel className="border-ink-600">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm font-semibold text-text-strong">Edit this listing</p>
        {failure && <Notice tone="danger">{failure}</Notice>}
        <div className="grid gap-3 sm:grid-cols-3">
          <NumberField label="Tonnes per month" value={form.quantity_t_per_month} error={fields.quantity_t_per_month} onChange={set('quantity_t_per_month')} />
          <NumberField label="Price ₹/tonne" value={form.price_inr_per_tonne} error={fields.price_inr_per_tonne} onChange={set('price_inr_per_tonne')} />
          <NumberField label="Max distance km" value={form.max_distance_km} error={fields.max_distance_km} onChange={set('max_distance_km')} />
          <label className="block sm:col-span-2">
            <span className="label mb-1.5 block">Location</span>
            <input className="input" value={form.location} onChange={set('location')} maxLength={200} />
            {fields.location && <span className="mt-1 block text-[11.5px] text-cherry">{fields.location}</span>}
          </label>
          <label className="block">
            <span className="label mb-1.5 block">Frequency</span>
            <select className="input" value={form.frequency} onChange={set('frequency')}>
              {['continuous', 'daily', 'weekly', 'monthly', 'quarterly', 'one_off'].map((option) => (
                <option key={option} value={option}>
                  {titleCase(option)}
                </option>
              ))}
            </select>
          </label>
          <label className="block sm:col-span-3">
            <span className="label mb-1.5 block">Intended use</span>
            <input className="input" value={form.application_use} onChange={set('application_use')} maxLength={200} />
          </label>
          <label className="block sm:col-span-3">
            <span className="label mb-1.5 block">Notes</span>
            <textarea className="input min-h-[72px]" value={form.notes} onChange={set('notes')} maxLength={1000} />
          </label>
        </div>
        <div className="flex items-center gap-2">
          <SymbioButton type="submit" size="sm" disabled={busy}>
            Save changes
          </SymbioButton>
          <SymbioButton type="button" variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
            Cancel
          </SymbioButton>
          <span className="text-[11.5px] text-text-faint">The material and the kind of listing are fixed; publish a new one for that.</span>
        </div>
      </form>
    </Panel>
  );
}

/** The one number a listing states, under whichever name its kind gives it. */
function price(listing: Listing): number | null {
  const value = listing.kind === 'demand' ? listing.offer_price_inr_per_tonne : listing.asking_price_inr_per_tonne;
  return typeof value === 'number' ? value : null;
}

function NumberField({
  label,
  value,
  error,
  onChange,
}: {
  label: string;
  value: string;
  error?: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">{label}</span>
      <input className="input tabular-nums" value={value} onChange={onChange} inputMode="decimal" />
      {error && <span className="mt-1 block text-[11.5px] text-cherry">{error}</span>}
    </label>
  );
}
