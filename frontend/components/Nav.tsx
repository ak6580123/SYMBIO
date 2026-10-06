'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import type { HealthData } from '@/lib/types';

const LINKS = [
  { href: '/', label: 'Overview' },
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/analyze', label: 'Analyze Waste' },
  { href: '/matches', label: 'Matches' },
  { href: '/map', label: 'Map' },
  { href: '/impact', label: 'Impact' },
  { href: '/knowledge-base', label: 'Knowledge Base' },
];

export default function Nav() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [offline, setOffline] = useState(false);

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
    <header className="sticky top-0 z-40 border-b border-ink-700 bg-ink-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm font-bold text-ink-950">
            S
          </span>
          <span className="text-sm font-semibold tracking-tight text-slate-100">Symbio</span>
        </Link>

        <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${
                isActive(link.href)
                  ? 'bg-ink-800 font-medium text-slate-100'
                  : 'text-slate-400 hover:bg-ink-850 hover:text-slate-200'
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden shrink-0 items-center gap-2 sm:flex">
          <StatusDot
            ok={health ? health.ollama.available : false}
            offline={offline}
            label={
              offline
                ? 'API offline'
                : health
                  ? health.ollama.available
                    ? `Ollama · ${health.ollama.model}`
                    : 'Demo mode · no Ollama'
                  : 'Checking…'
            }
          />
          <Link href="/analyze" className="btn-primary">
            Analyze Waste
          </Link>
        </div>
      </div>
    </header>
  );
}

function StatusDot({ ok, offline, label }: { ok: boolean; offline: boolean; label: string }) {
  const color = offline ? 'bg-rose-400' : ok ? 'bg-emerald-400' : 'bg-amber-400';
  return (
    <span
      className="flex items-center gap-1.5 rounded-md border border-ink-700 bg-ink-850 px-2 py-1 text-[11px] text-slate-400"
      title={
        offline
          ? 'The FastAPI backend is not reachable on port 8000.'
          : ok
            ? 'Ollama is running - identification uses the local LLM.'
            : 'Ollama is not running - Symbio is using its deterministic fallback classifier.'
      }
    >
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}
