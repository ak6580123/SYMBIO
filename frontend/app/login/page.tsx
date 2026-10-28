'use client';

// Sign in, and nothing else.
//
// An account exists so that an organisation's listings, profile and saved analyses have
// somewhere to live. Every public screen in Symbio works without signing in, and this
// page says so once instead of implying that a visitor is locked out of the product.

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { PageHeader, Section, SymbioButton } from '@/components/ui';
import { api } from '@/lib/api';
import { useSession } from '@/lib/session';

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { status, refresh, session, persistence } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Where to go after a sign-in. `?next=` is only honoured for a path on this site, so
  // the form cannot be turned into a redirect to somebody else's.
  const next = safeNext(params.get('next'));

  useEffect(() => {
    if (status === 'signed_in' && session) router.replace(next ?? '/organization');
  }, [status, session, next, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.signIn(email.trim(), password);
      await refresh();
      router.replace(next ?? '/organization');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Symbio could not sign you in.');
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[560px] space-y-8">
      <PageHeader
        eyebrow="Account"
        title="Sign in"
        subtitle="Your organisation's listings, profile and saved analyses are the reason to have one. The marketplace, the matcher and the network map stay open."
      />

      {/* A deployment with no database has no accounts to sign into. Saying so before a
          password is typed is kinder than a failed attempt, and it is the same sentence the
          API gave rather than one invented here. */}
      {status !== 'checking' && persistence && !persistence.reachable && (
        <div className="block-warn rounded-card px-3.5 py-2.5 text-[12.5px] leading-relaxed">
          This Symbio has no database it can reach, so it cannot check a password. {persistence.note}
        </div>
      )}

      <Section title="Sign in" subtitle="One cookie, which ends when you sign out or the session expires.">
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error && (
            <div className="block-danger rounded-card px-3.5 py-2.5 text-[12.5px] leading-relaxed">{error}</div>
          )}
          <label className="block">
            <span className="label mb-1.5 block">Email</span>
            <input
              className="input"
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="label mb-1.5 block">Password</span>
            <input
              className="input"
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <SymbioButton type="submit" disabled={busy || !email || !password}>
              {busy ? 'Checking…' : 'Sign in'}
            </SymbioButton>
            <Link href="/signup" className="text-[12.5px] link">
              Create an organisation account
            </Link>
          </div>
        </form>
      </Section>
    </div>
  );
}

/** Only an in-site path, and never a protocol. */
function safeNext(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith('/') || raw.startsWith('//')) return null;
  return raw;
}
