import type { ButtonHTMLAttributes, ReactNode } from 'react';

import {
  ORIGIN_TONE,
  REUSE_TYPE_LABEL,
  SAFETY_LABEL,
  reuseTypeTone,
  safetyTone,
  scoreRingColor,
  scoreTone,
 } from '@/lib/format';
import { confidenceColor, GRID, TEAL_STRONG } from '@/lib/palette';
import type { ProvenanceOrigin, ReuseType, SafetyLevel } from '@/lib/types';

/**
 * The Symbio UI kit.
 *
 * Three rules hold this together, and every component below obeys them:
 *
 * 1. No colour is written here. Spacing, radius and colour come from the tokens in
 *    `app/globals.css` (`surface`, `line`, `chip-teal`, `btn-primary`, …), so the
 *    palette is one file and a component cannot invent a sixth colour.
 * 2. A status is never only a colour. `StatusBadge`, `SafetyIndicator` and
 *    `MaterialBadge` all print the word; the tone is reinforcement.
 * 3. A number says where it came from. `MetricCard` accepts a `provenance` and a
 *    `title`, which is how an estimate stays labelled as an estimate.
 *
 * 4. A card is a thing. `SymbioCard` is for objects a user could point at - a match,
 *    a listing, a material, a pathway. Blocks that only group prose are `Section`:
 *    a title, a rule, whitespace, no border.
 *
 * `Panel`, `Metric` and `ScoreRing` are the names the earlier screens already use;
 * they are aliases for the components below rather than a second implementation, so
 * there is exactly one card, one metric and one ring.
 */

export type Tone = 'teal' | 'amber' | 'slate' | 'slate-deep' | 'clay' | 'cherry' | 'muted';

/** Background + border + text for a semantic status, from the token sheet. */
export const CHIP_TONE: Record<Tone, string> = {
  teal: 'chip-teal',
  amber: 'chip-amber',
  slate: 'chip-slate',
  'slate-deep': 'chip-slate-deep',
  clay: 'chip-clay',
  cherry: 'chip-cherry',
  muted: 'chip-muted',
};

export function StatusBadge({
  tone = 'muted',
  children,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`chip ${CHIP_TONE[tone]}`} title={title}>
      {children}
    </span>
  );
}

/**
 * The card. One hairline, one radius, no drop shadow beyond the 1px token, and a
 * header that is a rule rather than a second block of chrome.
 */
export function SymbioCard({
  title,
  subtitle,
  action,
  children,
  className = '',
  padded = true,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-700 px-4 py-3">
          <div className="min-w-0">
            {typeof title === 'string' ? (
              <h2 className="card-title">{title}</h2>
            ) : (
              <div className="card-title">{title}</div>
            )}
            {subtitle && <p className="caption mt-0.5 leading-snug">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children && <div className={padded ? 'p-4' : undefined}>{children}</div>}
    </section>
  );
}

/**
 * Every page opens with this and only this: an eyebrow that names the area, one
 * title, one line of intent, the primary action. Pages used to write their own
 * `<h1 className="text-xl">` each time, which is how eight screens ended up with
 * eight slightly different titles.
 */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  meta,
  className = '',
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <header className={`flex flex-wrap items-end justify-between gap-x-8 gap-y-4 ${className}`}>
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="page-title mt-1.5">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
        {meta && <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-text-faint">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/**
 * A titled block of the page that is not an object: a table, a chart, an
 * explanation. It carries a heading and a hairline instead of a border and a
 * background, so a page can have six sections without becoming six cards.
 */
export function Section({
  id,
  title,
  subtitle,
  action,
  children,
  divided = false,
  className = '',
}: {
  id?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  divided?: boolean;
  className?: string;
}) {
  return (
    <section id={id} className={className}>
      {(title || action) && (
        <div className={divided ? 'border-b border-line pb-2.5' : ''}>
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
            <div className="min-w-0">
              {typeof title === 'string' ? <h2 className="section-title">{title}</h2> : <div className="section-title">{title}</div>}
              {subtitle && <p className="section-subtitle">{subtitle}</p>}
            </div>
            {action && <div className="shrink-0">{action}</div>}
          </div>
        </div>
      )}
      {children && <div className={title || action ? 'pt-3.5' : undefined}>{children}</div>}
    </section>
  );
}

/** Section heading on its own, for pages that already have a container. */
export function SectionHeader({
  eyebrow,
  title,
  description,
  action,
  level = 'h2',
  className = '',
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  level?: 'h1' | 'h2';
  className?: string;
}) {
  const Heading = level;
  return (
    <div className={`flex flex-wrap items-end justify-between gap-3 ${className}`}>
      <div className="min-w-0 max-w-[70ch]">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <Heading className={level === 'h1' ? 'page-title mt-1.5' : 'section-title mt-0.5'}>{title}</Heading>
        {description &&
          (level === 'h1' ? <p className="page-subtitle">{description}</p> : <p className="section-subtitle">{description}</p>)}
      </div>
      {action}
    </div>
  );
}

/**
 * Buttons. `primary` is the only filled one, and it is pale amber with ink on it -
 * everything else is a hairline, so a screen never has three competing CTAs.
 */
export function SymbioButton({
  children,
  variant = 'primary',
  size = 'md',
  href,
  className = '',
  ...rest
}: {
  children: ReactNode;
  variant?: 'primary' | 'ghost' | 'quiet' | 'hero';
  size?: 'sm' | 'md' | 'lg';
  href?: string;
  className?: string;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'>) {
  const base =
    variant === 'primary' ? 'btn-primary' : variant === 'hero' ? 'btn-primary btn-lg' : variant === 'quiet' ? 'btn-quiet' : 'btn-ghost';
  const classes = `${base}${size === 'sm' ? ' btn-sm' : size === 'lg' ? ' btn-lg' : ''} ${className}`;
  if (href) {
    return (
      <a href={href} className={classes}>
        {children}
      </a>
    );
  }
  return (
    <button className={classes} {...rest}>
      {children}
    </button>
  );
}

/** Key metric: label, big tabular number, one line of context, and its source. */
export function MetricCard({
  label,
  value,
  hint,
  tone = 'default',
  provenance,
  className = '',
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'default' | 'accent' | 'success' | 'warning' | 'danger';
  provenance?: { origin: ProvenanceOrigin; title?: string };
  className?: string;
}) {
  const valueTone = {
    default: '',
    accent: 'text-accent',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-danger',
  }[tone];
  return (
    <div className={`panel panel-pad ${className}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="label">{label}</p>
        {provenance && <OriginChip origin={provenance.origin} title={provenance.title} />}
      </div>
      <p className={`value mt-1 ${valueTone}`}>{value}</p>
      {hint && <p className="mt-1 text-xs leading-snug text-text-faint">{hint}</p>}
    </div>
  );
}

/** A material as a chip: name plus the knowledge-base category it resolved to. */
export function MaterialBadge({
  name,
  category,
  title,
  className = '',
}: {
  name: ReactNode;
  category?: string;
  title?: string;
  className?: string;
}) {
  return (
    <span className={`chip chip-slate ${className}`} title={title}>
      <span className="font-medium text-text-strong">{name}</span>
      {category && <span className="text-[10px] uppercase tracking-wide opacity-80">{category}</span>}
    </span>
  );
}

/** The five safety states, in words. Colour is decoration on top of the label. */
export function SafetyIndicator({
  level,
  note,
  showLabel = true,
}: {
  level: SafetyLevel | string;
  note?: ReactNode;
  showLabel?: boolean;
}) {
  const known = (['low', 'moderate', 'high', 'hazardous', 'unknown'] as const).includes(level as SafetyLevel);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span className={`chip ${safetyTone(level as SafetyLevel)}`}>
        <span aria-hidden className="text-[8px] leading-none">
          ●
        </span>
        {showLabel ? (known ? SAFETY_LABEL[level as SafetyLevel] : String(level).replace(/_/g, ' ')) : null}
      </span>
      {note && <span className="text-[11px] leading-snug text-text-faint">{note}</span>}
    </span>
  );
}

/** How well a stream fits a partner, with the reuse route that earned it. */
export function MatchScore({
  score,
  size = 68,
  reuseType,
  caption,
}: {
  score: number;
  size?: number;
  reuseType?: ReuseType;
  caption?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <ScoreRing score={score} size={size} />
      {(reuseType || caption) && (
        <div className="min-w-0">
          {reuseType && <span className={`chip ${reuseTypeTone(reuseType)}`}>{REUSE_TYPE_LABEL[reuseType]}</span>}
          {caption && <p className="mt-1 text-[11px] leading-snug text-text-faint">{caption}</p>}
        </div>
      )}
    </div>
  );
}

/**
 * Key numbers as a row on hairlines instead of a grid of cards. Four or five
 * `MetricCard`s side by side reads as a dashboard; the same numbers set on a rule
 * read as a statement, which is what they are.
 */
export function MetricStrip({
  items,
  className = '',
}: {
  items: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'default' | 'accent' | 'success' | 'warning' | 'danger' }[];
  className?: string;
}) {
  const tone = {
    default: 'text-text-strong',
    accent: 'text-accent',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-danger',
  };
  // Written out as literals on purpose: a class name assembled at runtime is
  // invisible to Tailwind's scanner and simply does not exist in the stylesheet.
  const columns = ['sm:grid-cols-2 lg:grid-cols-2', 'sm:grid-cols-2 lg:grid-cols-3', 'sm:grid-cols-2 lg:grid-cols-4', 'sm:grid-cols-2 lg:grid-cols-4', 'sm:grid-cols-2 lg:grid-cols-5'][
    Math.min(4, Math.max(0, items.length - 1))
  ];
  return (
    <dl className={`grid gap-x-8 gap-y-4 border-y border-line py-4 ${columns} ${className}`}>
      {items.map((item) => (
        <div key={item.label}>
          <dt className="label">{item.label}</dt>
          <dd className={`stat mt-1 ${tone[item.tone ?? 'default']}`}>{item.value}</dd>
          {item.hint && <dd className="caption mt-0.5">{item.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

export function Panel(props: Parameters<typeof SymbioCard>[0]) {
  return <SymbioCard {...props} />;
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
  return <MetricCard label={label} value={value} hint={hint} tone={accent ? 'accent' : 'default'} />;
}

/**
 * The one label a number can carry. "Estimated" is the honest word for a figure
 * computed from recorded factors rather than invoiced, and it does not need a
 * second sentence apologising for itself.
 */
export function EstimatedTag() {
  return (
    <span className="chip chip-muted" title="Computed from recorded quantities and factors - an estimate, not a quotation">
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
      <svg width={size} height={size} className="-rotate-90" role="img" aria-label={`${score.toFixed(1)} match score`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={GRID} strokeWidth={stroke} />
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
        <span className="text-[9px] uppercase tracking-wider text-text-faint">match</span>
      </div>
    </div>
  );
}

export function Bar({ value, color = TEAL_STRONG }: { value: number; color?: string }) {
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
  const color = confidenceColor(confidence);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-700">
        <div className="h-full rounded-full" style={{ width: `${confidence * 100}%`, background: color }} />
      </div>
      <span className="text-xs tabular-nums text-text-muted">{(confidence * 100).toFixed(0)}%</span>
    </div>
  );
}

export function Notice({
  tone = 'info',
  children,
  className = '',
}: {
  tone?: 'info' | 'warn' | 'danger' | 'success';
  children: ReactNode;
  className?: string;
}) {
  const tones: Record<string, string> = {
    info: 'block-info',
    warn: 'block-warn',
    danger: 'block-danger',
    success: 'block-success',
  };
  return (
    <div className={`rounded-card px-3.5 py-2.5 text-[12.5px] leading-relaxed ${tones[tone]} ${className}`}>
      {children}
    </div>
  );
}

export function Spinner({ label = 'Working…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-accent" />
      {label}
    </div>
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="py-10 text-center">
      <p className="text-sm font-medium text-text">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-[52ch] text-xs leading-relaxed text-text-faint">{hint}</p>}
      {action && <div className="mt-3.5 flex justify-center">{action}</div>}
    </div>
  );
}

/**
 * A failure, stated once in plain language, with the way back. What went wrong in
 * detail - status codes, endpoints, stack traces - belongs in the server log, not
 * in the middle of someone's decision.
 */
export function ErrorState({
  title = 'Something went wrong while loading this.',
  hint,
  onRetry,
  retryHref,
  retryLabel = 'Try again',
}: {
  title?: string;
  hint?: ReactNode;
  onRetry?: () => void;
  /** For a server-rendered page, where there is no handler to call, a reload link. */
  retryHref?: string;
  retryLabel?: string;
}) {
  return (
    <div className="block-danger rounded-card px-4 py-3.5">
      <p className="text-sm font-semibold">{title}</p>
      {hint && <p className="mt-1 max-w-[64ch] text-[12.5px] leading-relaxed opacity-90">{hint}</p>}
      {(onRetry || retryHref) && (
        <div className="mt-3">
          <SymbioButton variant="ghost" size="sm" onClick={onRetry} href={retryHref}>
            {retryLabel}
          </SymbioButton>
        </div>
      )}
    </div>
  );
}

/**
 * The provenance tag every "why" value carries (Feature 3).
 *
 * The label and the tooltip arrive from the API rather than being written here,
 * so a screen cannot quietly rebrand an estimate as a measurement.
 */
export function OriginChip({ origin, label, title }: { origin: ProvenanceOrigin; label?: string; title?: string }) {
  return (
    <span className={`chip ${ORIGIN_TONE[origin] ?? 'chip-muted'}`} title={title}>
      {label ?? origin}
    </span>
  );
}
