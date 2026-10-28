'use client';

// Create an account, which creates the organisation it belongs to.
//
// The two are one step on purpose: an account with no tenant would make every later
// screen explain a half-made state. What is *not* here is a verification claim - the
// organisation's status is set by the platform team, never from this form, and the page
// says so once rather than in a tooltip on every badge.

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { PageHeader, Section, SymbioButton } from '@/components/ui';
import { api } from '@/lib/api';
import { useSession } from '@/lib/session';

export default function SignupPage() {
  const router = useRouter();
  const { status, refresh } = useSession();
  const [sectors, setSectors] = useState<{ sector: string; label: string; products: string[]; certifications: string[] }[]>([]);
  const [form, setForm] = useState({
    organization_name: '',
    sector: '',
    location: '',
    display_name: '',
    email: '',
    password: '',
  });
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .sectorProfiles()
      .then((payload) =>
        setSectors(
          payload.profiles.map((profile) => ({
            sector: profile.sector,
            label: profile.label,
            products: profile.products,
            certifications: profile.certifications,
          }))
        )
      )
      .catch(() => setSectors([]));
  }, []);

  useEffect(() => {
    if (status === 'signed_in') router.replace('/organization');
  }, [status, router]);

  const chosen = useMemo(() => sectors.find((entry) => entry.sector === form.sector), [sectors, form.sector]);
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((previous) => ({ ...previous, [key]: event.target.value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    try {
      await api.signUp({
        email: form.email.trim(),
        password: form.password,
        display_name: form.display_name.trim() || undefined,
        organization_name: form.organization_name.trim(),
        sector: form.sector || undefined,
        location: form.location.trim() || undefined,
      });
      await refresh();
      router.push('/organization');
    } catch (err) {
      const failure = err as { message?: string; fieldErrors?: Record<string, string> };
      setFields(failure.fieldErrors ?? {});
      setError(failure.message ?? 'Symbio could not create the account.');
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      <PageHeader
        eyebrow="Account"
        title="Create an organisation account"
        subtitle="An account is what lets Symbio keep your listings, your profile and your saved analyses between visits. Without one the product still runs; nothing is kept after the tab closes."
      />

      <Section title="The organisation" subtitle="What the marketplace will show beside a listing, and what the profile page will hold.">
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error && <div className="block-danger rounded-card px-3.5 py-2.5 text-[12.5px] leading-relaxed">{error}</div>}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Organisation name" required error={fields.organization_name}>
              <input className="input" value={form.organization_name} onChange={set('organization_name')} autoComplete="organization" />
            </Field>
            <Field label="Sector" error={fields.sector}>
              <select className="input" value={form.sector} onChange={set('sector')}>
                <option value="">Not stated</option>
                {sectors.map((entry) => (
                  <option key={entry.sector} value={entry.sector}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field
            label="Facility location"
            hint="Where the material is. Symbio places it if it can and keeps the words if it cannot - it does not move you to another city."
            error={fields.location}
          >
            <input
              className="input"
              value={form.location}
              onChange={set('location')}
              placeholder="Coimbatore, Tamil Nadu"
            />
          </Field>

          <div className="border-t border-line pt-4">
            <p className="label mb-3">Your details</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Your name" error={fields.display_name}>
                <input className="input" value={form.display_name} onChange={set('display_name')} autoComplete="name" />
              </Field>
              <Field label="Email" required error={fields.email}>
                <input className="input" type="email" value={form.email} onChange={set('email')} autoComplete="username" />
              </Field>
            </div>
            <Field
              label="Password"
              required
              className="mt-4"
              hint="At least ten characters. It is hashed with Argon2id and never leaves the database in a form a page can read."
              error={fields.password}
            >
              <input
                className="input"
                type="password"
                value={form.password}
                onChange={set('password')}
                autoComplete="new-password"
              />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <SymbioButton type="submit" disabled={busy || !form.organization_name || !form.email || !form.password}>
              {busy ? 'Creating…' : 'Create account'}
            </SymbioButton>
            <Link href="/login" className="text-[12.5px] link">
              I already have one
            </Link>
          </div>
        </form>
      </Section>

      {chosen && (
        <Section
          title="What your sector means here"
          subtitle="Reference material the platform records for this sector. Signing up does not claim any of it about you - it is what the profile page offers to start from."
        >
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] text-text-muted">
            <span>
              <span className="label mr-1.5">Products</span>
              {chosen.products.slice(0, 4).join(' · ') || 'not recorded'}
            </span>
            <span>
              <span className="label mr-1.5">Certifications seen</span>
              {chosen.certifications.slice(0, 3).join(' · ') || 'not recorded'}
            </span>
          </div>
        </Section>
      )}
    </div>
  );
}

function Field({
  label,
  required = false,
  hint,
  error,
  className = '',
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="label mb-1.5 block">
        {label}
        {required && <span className="text-accent"> *</span>}
      </span>
      {error && <span className="mb-1.5 block text-[11.5px] leading-snug text-cherry">{error}</span>}
      {children}
      {hint && <span className="mt-1.5 block text-[11.5px] leading-relaxed text-text-faint">{hint}</span>}
    </label>
  );
}
