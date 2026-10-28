'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import type { HealthData } from '@/lib/types';
import { useSession } from '@/lib/session';

/**
 * Two groups, deliberately. The work you come to do - describe a material, read the
 * matches, publish a listing, look at the network, check what it added up to - is the
 * row you can hit without thinking. The reference surfaces sit behind a hairline so
 * they never compete for the same attention.
 */
const PRIMARY_LINKS = [
  { href: '/analyze', label: 'Analyze' },
  { href: '/matches', label: 'Matches' },
  { href: '/marketplace', label: 'Marketplace' },
  { href: '/map', label: 'Network' },
  { href: '/impact', label: 'Impact' },
];

const SECONDARY_LINKS = [
  { href: '/dashboard', label: 'Overview' },
  { href: '/knowledge-base', label: 'Knowledge base' },
];

/** Shown only to someone with an account: the tenant's own screens. */
const ACCOUNT_LINKS = [
  { href: '/organization', label: 'Organisation' },
  { href: '/history', label: 'History' },
];

export default function Nav() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [offline, setOffline] = useState(false);
  const { status: sessionStatus, session } = useSession();
  const signedIn = sessionStatus === 'signed_in' && Boolean(session);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((data) => !cancelled && setHealth(data))
      .catch(() => !cancelled && setOffline(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className="sticky top-0 z-40 border-b border-ink-700 bg-canvas">
      {/* Two rows on purpose: the links never have to compete with the brand and
          the engine badge for 380px of width on a phone. */}
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 pt-3">
        <Link href="/" className="flex items-center gap-2.5">
          <span
            className="flex h-7 w-7 items-center justify-center text-sm font-bold"
            style={{
              background: 'rgb(var(--primary-rgb))',
              color: 'rgb(var(--primary-ink-rgb))',
              borderRadius: 'var(--radius)',
            }}
            aria-hidden
          >
            S
          </span>
          <span className="text-sm font-semibold tracking-tight text-text-strong">Symbio</span>
          <span className="hidden text-[11px] text-text-faint sm:inline">Industrial symbiosis intelligence</span>
        </Link>

        <div className="flex shrink-0 items-center gap-2">
          <StatusDot {...engineBadge(health, offline)} />
          <AccountControl />
          <Link href="/analyze" className="btn-primary hidden sm:inline-flex">
            Analyze a material
          </Link>
        </div>
      </div>

      <nav aria-label="Main" className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-4 py-2">
        {PRIMARY_LINKS.map((link) => (
          <NavLink key={link.href} {...link} active={isActive(link.href)} />
        ))}
        <span aria-hidden className="mx-1.5 h-5 w-px shrink-0 bg-line" />
        {SECONDARY_LINKS.map((link) => (
          <NavLink key={link.href} {...link} active={isActive(link.href)} secondary />
        ))}
        {/* The tenant's own screens appear with the tenant. Two more permanent links for
            a page nobody can reach without an account would be noise for everybody else. */}
        {signedIn && (
          <>
            <span aria-hidden className="mx-1.5 h-5 w-px shrink-0 bg-line" />
            {ACCOUNT_LINKS.map((link) => (
              <NavLink key={link.href} {...link} active={isActive(link.href)} secondary />
            ))}
          </>
        )}
      </nav>
    </header>
  );
}

/**
 * The badge has to tell three states apart, not two: Ollama running with a
 * usable model, Ollama running but with nothing pulled, and Ollama absent. The
 * middle one needs a different fix, and Symbio still works in it, so it is
 * amber rather than red.
 */
function engineBadge(
  health: HealthData | null,
  offline: boolean
): { tone: Tone; label: string; hint: string } {
  if (offline) {
    return { tone: 'off', label: 'Service offline', hint: 'Symbio cannot reach its analysis service, so results cannot load. Reload once it is running.' };
  }
  if (!health) {
    return { tone: 'warn', label: 'Checking…', hint: 'Asking the backend for its status.' };
  }
  const o = health.ollama;
  if (o.available && o.usable) {
    return {
      tone: 'good',
      label: `Identification · ${o.model}`,
      hint: o.auto_selected
        ? `Material identification runs locally on ${o.model}. Pull ${o.requested_model} for the model this build is tuned for.`
        : 'Material identification runs on the local language model you configured.',
    };
  }
  if (o.available) {
    return {
      tone: 'warn',
      label: 'Identification · rule-based',
      hint: 'A local model is reachable but none is installed, so identification uses the built-in classifier. ' +
        `Pulling ${o.requested_model} switches it to the model.`,
    };
  }
  return {
    tone: 'warn',
    label: 'Identification · rule-based',
    hint: 'No local language model is running, so material identification uses the built-in classifier. ' +
      'Matching, safety and impact are computed the same way either way.',
  };
}

function NavLink({
  href,
  label,
  active,
  secondary = false,
}: {
  href: string;
  label: string;
  active: boolean;
  secondary?: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={`whitespace-nowrap rounded-card px-2.5 py-1.5 text-[13px] transition-colors ${
        active
          ? 'bg-surface-muted font-medium text-text-strong'
          : `${secondary ? 'text-text-faint' : 'text-text-muted'} hover:bg-surface hover:text-text-strong`
      }`}
    >
      {label}
    </Link>
  );
}

type Tone = 'good' | 'warn' | 'off';

function StatusDot({ tone, label, hint }: { tone: Tone; label: string; hint: string }) {
  // The dot repeats the chip's own colour, and the words carry the meaning.
  const color =
    tone === 'good'
      ? 'rgb(var(--symbio-teal-strong-rgb))'
      : tone === 'warn'
        ? 'rgb(var(--symbio-amber-strong-rgb))'
        : 'rgb(var(--symbio-cherry-rgb))';
  return (
    <span
      className="chip chip-muted !py-1"
      title={hint}
      style={{ color: 'rgb(var(--text-muted-rgb))' }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {/* Always the words, never the dot alone: the label is what survives
          greyscale, a screen reader and a 360px screen. */}
      <span className="max-w-[46vw] truncate">{label}</span>
    </span>
  );
}


/**
 * The account, in the words the API used for it.
 *
 * A signed-in person sees which organisation they are looking at and what they are in it
 * as, because a marketplace with a name in the corner is a different thing from a
 * marketplace with somebody's records in it. A signed-out visitor sees one link and no
 * explanation: the demo works without an account, and saying so twice in one header is
 * how a product starts apologising for itself.
 */
function AccountControl() {
  const { status, session, signOut } = useSession();
  const router = useRouter();

  if (status === 'checking' || status === 'unreachable') return <span className="w-px" aria-hidden />;

  if (!session) {
    return (
      <Link href="/login" className="chip chip-muted !py-1 text-text-muted hover:text-text-strong">
        Sign in
      </Link>
    );
  }

  return (
    <span className="flex items-center gap-1.5">
      <Link
        href="/organization"
        className="chip chip-muted !py-1 max-w-[38vw] sm:max-w-none"
        title={`${session.organization.name} · ${session.role_label}`}
      >
        <span className="truncate">{session.organization.name}</span>
        <span className="text-text-faint">· {session.role_label}</span>
      </Link>
      <button
        type="button"
        onClick={() => {
          void signOut().then(() => router.refresh());
        }}
        className="text-[11px] text-text-faint underline decoration-line underline-offset-2 hover:text-text-strong"
      >
        Sign out
      </button>
    </span>
  );
}
