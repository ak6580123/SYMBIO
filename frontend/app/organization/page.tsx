'use client';

/**
 * §4 - the organisation's own record, in its own words.
 *
 * This page reads and writes the tenant row set: the profile an organisation declares,
 * the facilities it names, the people it admits. Nothing here is scored and nothing here
 * is verified - `verification_status` is shown because the platform team sets it, and no
 * route in Symbio accepts it from a request body.
 *
 * The profile is stored as written. A sector template is not merged into it: the two
 * arrive from different places, so the page labels which line came from which instead of
 * quietly filling in what the organisation never stated.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

import OwnListings from '@/components/OwnListings';
import { Empty, ErrorState, Notice, PageHeader, Section, Spinner, SymbioButton, StatusBadge, type Tone } from '@/components/ui';
import { ApiError, api } from '@/lib/api';
import { useSession } from '@/lib/session';
import { titleCase } from '@/lib/format';
import type { MaterialLine, OrganizationBundle, OrganizationProfile, OrganizationRole } from '@/lib/types';

const VERIFICATION_TONE: Record<string, Tone> = {
  unverified: 'muted',
  pending: 'amber',
  verified: 'teal',
};

export default function OrganizationPage() {
  const { status, session, signOut, refresh } = useSession();
  const [bundle, setBundle] = useState<OrganizationBundle | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    try {
      setBundle(await api.organization());
    } catch (err) {
      setBundle(null);
      setFailure(err instanceof ApiError ? err.message : 'This organisation could not be read.');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (status === 'signed_in') void load();
    if (status !== 'checking') setBusy(false);
  }, [status, load]);

  if (status === 'checking' || (status === 'signed_in' && busy && !bundle)) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Organisation" title="Your organisation" subtitle="Reading the record Symbio holds for you." />
        <Spinner />
      </div>
    );
  }

  if (status === 'anonymous' || status === 'unreachable') {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Organisation"
          title="Your organisation"
          subtitle="A profile, its facilities, the people in it and the listings it has published."
        />
        <Notice tone="info">
          {status === 'unreachable'
            ? 'Symbio cannot reach its service right now, so there is no organisation to show.'
            : 'Organisation records belong to a signed-in account. Sign in, or create one if this organisation has no account yet.'}
          <span className="mt-1.5 flex flex-wrap gap-3">
            <Link href="/login?next=/organization" className="link text-[12.5px]">
              Sign in
            </Link>
            <Link href="/signup" className="link text-[12.5px]">
              Create an organisation account
            </Link>
          </span>
        </Notice>
      </div>
    );
  }

  if (failure || !bundle) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Organisation" title="Your organisation" />
        <ErrorState
          title="This organisation could not be read."
          hint={failure ?? 'The record was empty.'}
          onRetry={load}
        />
      </div>
    );
  }

  const canManage = session?.role === 'organization_admin';
  const me = session?.user?.id ?? '';
  const canWrite = Boolean(bundle.you?.can_write);

  return (
    <div className="space-y-9">
      <PageHeader
        eyebrow="Organisation"
        title={bundle.organization.name}
        subtitle="What Symbio stores about this organisation. An organisation states it; Symbio records it."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={VERIFICATION_TONE[bundle.organization.verification.status] ?? 'muted'} title={bundle.organization.verification.meaning}>
              {titleCase(bundle.organization.verification.status)}
            </StatusBadge>
            <span className="chip chip-muted">{bundle.you.role_label}</span>
            <SymbioButton variant="ghost" size="sm" onClick={() => void signOut().then(refresh)}>
              Sign out
            </SymbioButton>
          </div>
        }
        meta={
          <p className="flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-text-faint">
            <span>
              {bundle.counts.listings} listing{bundle.counts.listings === 1 ? '' : 's'} · {bundle.counts.analyses} saved
              analys{bundle.counts.analyses === 1 ? 'is' : 'es'} · {bundle.counts.facilities} facilit
              {bundle.counts.facilities === 1 ? 'y' : 'ies'}
            </span>
            <Link href="/history" className="link">
              Analysis history
            </Link>
          </p>
        }
      />

      {(!bundle.persistence.configured || !bundle.persistence.reachable) && (
        <Notice tone="warn">
          {bundle.persistence.configured
            ? 'Symbio cannot reach its database right now. The profile below is readable; saving it has to wait.'
            : 'No database is configured, so saving a profile needs an account and a store. The public network works either way.'}
        </Notice>
      )}

      <ProfileSection bundle={bundle} canEdit={canManage} onSaved={setBundle} />
      <FacilitySection bundle={bundle} canEdit={canWrite} onSaved={setBundle} />
      <MemberSection bundle={bundle} canManage={canManage} currentUserId={me} onSaved={setBundle} />

      <Section
        title="Listings"
        subtitle="What this organisation has published, and the only listings its members can change."
        action={
          <Link href="/marketplace" className="link text-[12.5px]">
            Publish on the marketplace
          </Link>
        }
      >
        <OwnListings canWrite={canWrite} />
      </Section>
    </div>
  );
}

/* ------------------------------------------------------------------- profile */

function ProfileSection({
  bundle,
  canEdit,
  onSaved,
}: {
  bundle: OrganizationBundle;
  canEdit: boolean;
  onSaved: (bundle: OrganizationBundle) => void;
}) {
  const profile = bundle.profile ?? emptyProfile();
  const [draft, setDraft] = useState<OrganizationProfile>(profile);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [sectors, setSectors] = useState<string[]>([]);

  useEffect(() => {
    setDraft(profile);
  }, [profile]);

  useEffect(() => {
    api
      .sectorProfiles()
      .then((payload) => setSectors((payload.profiles ?? []).map((entry) => entry.sector)))
      .catch(() => setSectors([]));
  }, []);

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(profile), [draft, profile]);

  async function save() {
    setBusy(true);
    setFailure(null);
    setFields({});
    setSaved(null);
    try {
      const result = await api.saveProfile(draft);
      const next = { ...bundle, profile: result.profile };
      onSaved(next);
      setDraft(result.profile);
      setSaved(result.note);
    } catch (err) {
      if (err instanceof ApiError) {
        setFields(err.fieldErrors ?? {});
        setFailure(Object.keys(err.fieldErrors ?? {}).length ? null : err.message);
      } else {
        setFailure('The profile was not saved.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="Profile"
      subtitle="What the organisation states about itself. Material lines are checked against the knowledge base; nothing here is scored."
      action={
        canEdit ? (
          <SymbioButton size="sm" onClick={save} disabled={busy || !dirty}>
            {busy ? 'Saving…' : dirty ? 'Save profile' : 'Saved'}
          </SymbioButton>
        ) : (
          <span className="chip chip-muted" title="Only an administrator of this organisation can change it.">
            Read-only for {bundle.you.role_label.toLowerCase()}s
          </span>
        )
      }
    >
      <div className="space-y-4">
        {failure && <ErrorState title="The profile was not saved." hint={failure} />}
        {saved && <Notice tone="success">{saved}</Notice>}

        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Organisation name" hint="Set with the account. Symbio shows it on anything this organisation publishes.">
            <input className="input" value={bundle.organization.name} readOnly disabled={!canEdit} />
          </Field>
          <Field label="Sector" error={fields.sector}>
            <select
              className="input"
              value={draft.sector}
              disabled={!canEdit}
              onChange={(event) => setDraft({ ...draft, sector: event.target.value })}
            >
              <option value="">Not stated</option>
              {Array.from(new Set([...sectors, draft.sector].filter(Boolean))).map((option) => (
                <option key={option} value={option}>
                  {titleCase(option)}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <StringLines
          label="Products produced"
          hint="One per line, as the organisation states it."
          value={draft.products_produced}
          disabled={!canEdit}
          onChange={(rows) => setDraft({ ...draft, products_produced: rows })}
        />
        <MaterialLines
          label="Materials required"
          hint="Each line names a material Symbio knows. Optional quantity in tonnes per month."
          value={draft.materials_required}
          disabled={!canEdit}
          onChange={(rows) => setDraft({ ...draft, materials_required: rows })}
        />
        <MaterialLines
          label="Waste streams"
          hint="What leaves the site. This is what the matching network reads a source listing against."
          value={draft.waste_streams}
          disabled={!canEdit}
          onChange={(rows) => setDraft({ ...draft, waste_streams: rows })}
        />
        <StringLines
          label="Processing capabilities"
          hint="Grinding, drying, pelletising and so on, in the organisation's words."
          value={draft.processing_capabilities}
          disabled={!canEdit}
          onChange={(rows) => setDraft({ ...draft, processing_capabilities: rows })}
        />
        <StringLines
          label="Certifications"
          hint="Stated, not verified. Symbio does not confirm a certificate from inside the product."
          value={draft.certifications}
          disabled={!canEdit}
          onChange={(rows) => setDraft({ ...draft, certifications: rows })}
        />

        {profile.updated_at && (
          <p className="text-[11.5px] text-text-faint">Last saved {profile.updated_at.replace('T', ' ').slice(0, 16)}</p>
        )}
      </div>
    </Section>
  );
}

function emptyProfile(): OrganizationProfile {
  return {
    sector: '',
    products_produced: [],
    materials_required: [],
    waste_streams: [],
    processing_capabilities: [],
    certifications: [],
    contact: {},
  };
}

/* ---------------------------------------------------------------- facilities */

function FacilitySection({
  bundle,
  canEdit,
  onSaved,
}: {
  bundle: OrganizationBundle;
  canEdit: boolean;
  onSaved: (bundle: OrganizationBundle) => void;
}) {
  const [form, setForm] = useState({ name: '', location: '', notes: '' });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function add() {
    setBusy(true);
    setFailure(null);
    try {
      const created = await api.addFacility({
        name: form.name.trim(),
        location: form.location.trim() || undefined,
        notes: form.notes.trim() || undefined,
      });
      onSaved({
        ...bundle,
        facilities: [...bundle.facilities, created.facility],
        counts: { ...bundle.counts, facilities: bundle.counts.facilities + 1 },
      });
      setForm({ name: '', location: '', notes: '' });
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : 'The facility was not added.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setFailure(null);
    try {
      await api.removeFacility(id);
      onSaved({
        ...bundle,
        facilities: bundle.facilities.filter((row) => row.id !== id),
        counts: { ...bundle.counts, facilities: Math.max(0, bundle.counts.facilities - 1) },
      });
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : 'The facility was not removed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Facilities" subtitle="Where this organisation works. A place is placed only if something can actually place it.">
      <div className="space-y-2.5">
        {failure && <ErrorState title="That change did not go through." hint={failure} />}
        {bundle.facilities.length === 0 && (
          <Empty title="No facility recorded." hint="Add the site a listing or analysis will be measured from." />
        )}
        {bundle.facilities.map((facility) => (
          <div key={facility.id} className="panel px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-text-strong">{facility.name}</p>
                <p className="mt-1 text-[12.5px] text-text-muted">
                  {facility.location || 'No location stated'}
                  {facility.location_resolved && facility.latitude !== null
                    ? ` · placed from ${facility.location_source || 'the recorded network'} (${facility.latitude.toFixed(
                        4
                      )}, ${facility.longitude?.toFixed(4)})`
                    : facility.location
                      ? ' · Symbio could not place this text, so no distance is quoted for it'
                      : ''}
                </p>
                {facility.notes && <p className="mt-1 max-w-[70ch] text-[12.5px] leading-relaxed text-text-faint">{facility.notes}</p>}
              </div>
              {canEdit && (
                <SymbioButton variant="quiet" size="sm" disabled={busy} onClick={() => void remove(facility.id)}>
                  Remove
                </SymbioButton>
              )}
            </div>
          </div>
        ))}

        {canEdit && (
          <div className="panel px-4 py-3">
            <p className="text-[12.5px] font-semibold text-text-strong">Add a facility</p>
            <div className="mt-2.5 grid gap-3 sm:grid-cols-3">
              <Field label="Name">
                <input className="input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} maxLength={120} />
              </Field>
              <Field label="Location" hint="Typed as you would say it. Nothing is guessed.">
                <input
                  className="input"
                  value={form.location}
                  onChange={(event) => setForm({ ...form, location: event.target.value })}
                  maxLength={200}
                />
              </Field>
              <Field label="Notes">
                <input
                  className="input"
                  value={form.notes}
                  onChange={(event) => setForm({ ...form, notes: event.target.value })}
                  maxLength={1000}
                />
              </Field>
            </div>
            <div className="pt-2.5">
              <SymbioButton size="sm" disabled={busy || form.name.trim().length < 2} onClick={add}>
                {busy ? 'Saving…' : 'Add facility'}
              </SymbioButton>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------- members */

function MemberSection({
  bundle,
  canManage,
  currentUserId,
  onSaved,
}: {
  bundle: OrganizationBundle;
  canManage: boolean;
  currentUserId: string;
  onSaved: (bundle: OrganizationBundle) => void;
}) {
  const [form, setForm] = useState<{ email: string; role: OrganizationRole }>({ email: '', role: 'viewer' });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function add() {
    setBusy(true);
    setFailure(null);
    setNote(null);
    try {
      const result = await api.addMember(form.email.trim(), form.role);
      onSaved({
        ...bundle,
        members: [...bundle.members, { user_id: result.member.user_id, email: result.member.email, role: result.member.role, role_label: titleCase(result.member.role) }],
      });
      setForm({ email: '', role: 'viewer' });
      setNote(result.note);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : 'That person could not be added.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(userId: string) {
    setBusy(true);
    setFailure(null);
    try {
      const result = await api.removeMember(userId);
      onSaved({ ...bundle, members: bundle.members.filter((row) => row.user_id !== userId) });
      setNote(result.note);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : 'That person could not be removed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="People"
      subtitle="Three roles, and nothing finer: an administrator changes the record, an operator publishes and analyses, a viewer reads."
    >
      <div className="space-y-2.5">
        {failure && <ErrorState title="Membership did not change." hint={failure} />}
        {note && <Notice tone="success">{note}</Notice>}
        {bundle.members.map((member) => (
          <div key={member.user_id} className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
            <p className="min-w-0 text-[12.5px]">
              <span className="font-semibold text-text-strong">{member.email}</span>
              {member.display_name ? <span className="text-text-muted"> · {member.display_name}</span> : null}
              <span className="chip chip-muted ml-2">{member.role_label}</span>
            </p>
            {canManage && member.user_id !== currentUserId && (
              <SymbioButton variant="quiet" size="sm" disabled={busy} onClick={() => void remove(member.user_id)}>
                Remove
              </SymbioButton>
            )}
          </div>
        ))}
        {canManage && (
          <div className="panel flex flex-wrap items-end gap-3 px-4 py-3">
            <Field label="Invite by email" className="min-w-[240px] flex-1">
              <input
                className="input"
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                placeholder="person@organisation.in"
              />
            </Field>
            <Field label="Role">
              <select className="input" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as OrganizationRole })}>
                <option value="organization_admin">Organization admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </Field>
            <SymbioButton size="sm" disabled={busy || !form.email.includes('@')} onClick={add}>
              Add person
            </SymbioButton>
          </div>
        )}
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ shared UI */

function Field({
  label,
  hint,
  error,
  className = '',
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="label mb-1.5 block">{label}</span>
      {error && <span className="mb-1.5 block text-[11.5px] leading-snug text-cherry">{error}</span>}
      {children}
      {hint && <span className="mt-1.5 block text-[11.5px] leading-relaxed text-text-faint">{hint}</span>}
    </label>
  );
}

/** A list of plain strings, edited one line per entry. Order is what the organisation typed. */
function StringLines({
  label,
  hint,
  value,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  value: string[];
  disabled: boolean;
  onChange: (rows: string[]) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <textarea
        className="input min-h-[84px] font-sans text-[12.5px]"
        value={value.join('\n')}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value.split('\n').map((row) => row.trim()).filter(Boolean))}
        placeholder="One per line"
      />
    </Field>
  );
}

/**
 * Material lines, where an id has to exist. The select is the knowledge base's own
 * catalogue, so a line that reaches the server is a line the server recognises; the
 * quantity stays optional because stating a stock is not the same as measuring one.
 */
function MaterialLines({
  label,
  hint,
  value,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  value: MaterialLine[];
  disabled: boolean;
  onChange: (rows: MaterialLine[]) => void;
}) {
  const [catalogue, setCatalogue] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    api
      .materials()
      .then((payload) => setCatalogue(payload.materials.map((row) => ({ id: row.id, name: row.name }))))
      .catch(() => setCatalogue([]));
  }, []);

  const options = useMemo(() => {
    const known = new Map(catalogue.map((row) => [row.id, row.name]));
    value.forEach((row) => {
      if (row.material_id && !known.has(row.material_id)) known.set(row.material_id, row.name ?? row.material_id);
    });
    return Array.from(known.entries());
  }, [catalogue, value]);

  function update(index: number, changes: Partial<MaterialLine>) {
    onChange(value.map((row, position) => (position === index ? { ...row, ...changes } : row)));
  }

  return (
    <Field label={label} hint={hint}>
      <div className="space-y-2">
        {value.length === 0 && <p className="text-[12px] text-text-faint">Nothing stated.</p>}
        {value.map((row, index) => (
          <div key={`${row.material_id}-${index}`} className="flex flex-wrap items-center gap-2">
            <select
              className="input h-9 min-w-[200px] flex-1"
              value={row.material_id}
              disabled={disabled}
              onChange={(event) => update(index, { material_id: event.target.value })}
            >
              {options.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
            <input
              className="input h-9 w-24 tabular-nums"
              value={row.quantity_t_per_month ?? ''}
              inputMode="decimal"
              disabled={disabled}
              placeholder="t/month"
              onChange={(event) =>
                update(index, { quantity_t_per_month: event.target.value === '' ? undefined : Number(event.target.value) })
              }
            />
            <input
              className="input h-9 min-w-[160px] flex-1"
              value={row.note ?? ''}
              disabled={disabled}
              placeholder="note (optional)"
              onChange={(event) => update(index, { note: event.target.value })}
            />
            {!disabled && (
              <button
                type="button"
                className="text-[12px] link"
                onClick={() => onChange(value.filter((_, position) => position !== index))}
              >
                Remove
              </button>
            )}
          </div>
        ))}
        {!disabled && (
          <button
            type="button"
            className="text-[12px] link"
            onClick={() => onChange([...value, { material_id: options[0]?.[0] ?? '', quantity_t_per_month: undefined }])}
          >
            Add a line
          </button>
        )}
      </div>
    </Field>
  );
}
