import type { ReactNode } from 'react';

import { scoreRingColor, scoreTone } from '@/lib/format';

export function Panel({
  title,
  action,
  children,
  className = '',
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-700 px-4 py-3">
          {title && <h2 className="text-sm font-semibold text-slate-200">{title}</h2>}
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className="panel panel-pad">
      <p className="label">{label}</p>
      <p className={`value mt-1 ${accent ? 'text-accent' : ''}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function DemoTag({ label = 'Demo data' }: { label?: string }) {
  return (
    <span className="chip border-amber-500/30 bg-amber-500/10 text-amber-300/90" title="Seeded demonstration data, not live records">
      {label}
    </span>
  );
}

export function EstimatedTag() {
  return (
    <span className="chip border-slate-500/30 bg-slate-500/10 text-slate-400" title="Estimated value - demo calculation">
      Estimated
    </span>
  );
}

export function ScoreRing({ score, size = 68 }: { score: number; size?: number }) {
  const stroke = 6;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.max(0, Math.min(100, score)) / 100) * circumference;
  const color = scoreRingColor(score);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1E2833" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-base font-semibold tabular-nums ${scoreTone(score)}`}>{score.toFixed(0)}</span>
        <span className="text-[9px] uppercase tracking-wider text-slate-500">match</span>
      </div>
    </div>
  );
}

export function Bar({ value, color = '#34D399' }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${Math.max(0, Math.min(100, value * 100))}%`, background: color }}
      />
    </div>
  );
}

export function ConfidenceBar({ confidence }: { confidence: number }) {
  const color = confidence >= 0.7 ? '#34D399' : confidence >= 0.5 ? '#FCD34D' : '#FB7185';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-700">
        <div className="h-full rounded-full" style={{ width: `${confidence * 100}%`, background: color }} />
      </div>
      <span className="text-xs tabular-nums text-slate-400">{(confidence * 100).toFixed(0)}%</span>
    </div>
  );
}

export function Notice({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'danger'; children: ReactNode }) {
  const tones = {
    info: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
    warn: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    danger: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  };
  return <div className={`rounded-md border px-3 py-2 text-xs leading-relaxed ${tones[tone]}`}>{children}</div>;
}

export function Spinner({ label = 'Working…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-accent" />
      {label}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="py-10 text-center">
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
