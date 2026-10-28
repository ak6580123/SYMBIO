// Display formatting and shared labels.

import type { MatchSort, ProvenanceOrigin, ReuseType, SafetyLevel, SourceSector } from './types';
import { scoreColor } from './palette';

export const inr = (value: number): string =>
  `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

export const tonnes = (value: number): string => `${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })} t`;

/**
 * §9 - one place that decides how an absent distance is worded.
 *
 * A location that is not in the gazetteer has no coordinates, and Symbio never
 * borrows another city's to make one up. Every view therefore says the same thing
 * when there is nothing to show, instead of each inventing its own euphemism - or,
 * worse, a reassuring "0 km".
 */
export function distanceLabel(km: number | null | undefined): string {
  return km === null || km === undefined ? 'Distance not available' : `${km} km`;
}

/** The same fact, short enough for a row in a list or a table cell. */
export function distanceShort(km: number | null | undefined): string {
  return km === null || km === undefined ? 'not available' : `${km} km`;
}

/** "{km} from {place}", or the honest version when there is no {km} to state. */
export function distanceFrom(km: number | null | undefined, place?: string | null): string {
  if (km === null || km === undefined) {
    return place ? `distance from ${place} not available` : 'distance not available';
  }
  return place ? `${km} km from ${place}` : `${km} km`;
}

/** Money for a figure that may legitimately be missing, e.g. an unpriced haul. */
export function money(value: number | null | undefined, prefix = '₹'): string {
  return value === null || value === undefined ? 'not calculated' : `${prefix}${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

export const pct = (value: number, digits = 0): string => `${(value * 100).toFixed(digits)}%`;

export const scoreLabel = (score: number): string => `${score.toFixed(0)}%`;

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export const SOURCE_SECTOR_LABEL: Record<SourceSector, string> = {
  industry: 'Industry',
  household: 'Household / Community',
  sme: 'SME / Small business',
  agriculture: 'Agriculture',
  other: 'Other',
};

export const REUSE_TYPE_LABEL: Record<ReuseType, string> = {
  DIRECT_REUSE: 'Direct reuse',
  REQUIRES_PROCESSING: 'Requires processing',
  INDUSTRIAL_ONLY: 'Industrial only',
  RESTRICTED: 'Restricted',
  UNKNOWN: 'Unknown',
};

export const SAFETY_LABEL: Record<SafetyLevel, string> = {
  low: 'Low risk',
  moderate: 'Moderate risk',
  high: 'High risk',
  hazardous: 'Hazardous',
  unknown: 'Unknown risk',
};

/**
 * A reuse type always reads the same way: teal is the good news, amber is "needs
 * something first", cherry is "do not". The tone classes live in globals.css, so a
 * screen cannot invent a fourth opinion on what RESTRICTED looks like.
 */
export function reuseTypeTone(type: ReuseType): string {
  switch (type) {
    case 'DIRECT_REUSE':
      return 'chip-teal';
    case 'REQUIRES_PROCESSING':
      return 'chip-slate-deep';
    case 'INDUSTRIAL_ONLY':
      return 'chip-amber';
    case 'RESTRICTED':
      return 'chip-cherry';
    default:
      return 'chip-muted';
  }
}

/** Five safety states, five distinct tones - and they never change the ranking. */
export function safetyTone(level: SafetyLevel): string {
  switch (level) {
    case 'low':
      return 'chip-teal';
    case 'moderate':
      return 'chip-amber';
    case 'high':
      return 'chip-clay';
    case 'hazardous':
      return 'chip-cherry';
    default:
      return 'chip-muted';
  }
}

export function scoreTone(score: number): string {
  if (score >= 80) return 'text-success';
  if (score >= 65) return 'text-info';
  if (score >= 50) return 'text-warning';
  return 'text-text-muted';
}

/** The ring is a graphic, so it can use the lighter tints text cannot have. */
export const scoreRingColor = scoreColor;

export const titleCase = (value: string): string =>
  value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

/**
 * The five stages of a material flow, in order, with the label each one gets.
 *
 * This lives in a plain module rather than in the chart component because both
 * the dashboard flow chart (client) and the match page (server component) label
 * the same pathway, and a server component may not read values out of a
 * 'use client' module.
 */
export const FLOW_STAGES = ['source', 'material', 'processing', 'sector', 'product'] as const;

export const STAGE_LABEL: Record<string, string> = {
  source: 'Waste source',
  material: 'Material',
  processing: 'Processing',
  sector: 'Reuse sector',
  product: 'Product / application',
};

/**
 * The optimisation modes, in the order the selector shows them.
 *
 * These are labels for the five sort keys in `backend/main.py` (SORTS) - each
 * one re-orders the same result set by a measured field. The weights behind
 * "best overall" are fixed at 30/20/15/15/10/10 and are not editable anywhere,
 * which is why there is no weight slider next to this.
 */
export const OPTIMIZATION_MODES: { value: MatchSort; label: string; note: string }[] = [
  { value: 'score', label: 'Best overall', note: 'the weighted engine score (30/20/15/15/10/10)' },
  { value: 'value', label: 'Highest value', note: '₹ per month at the matched quantity' },
  { value: 'environmental', label: 'Best environmental', note: 'tonnes of CO₂e avoided per month' },
  { value: 'distance', label: 'Closest', note: 'straight-line distance from the source' },
  { value: 'least_processing', label: 'Least processing', note: 'fewest handling steps first' },
];

export const MODE_LABEL: Record<MatchSort, string> = OPTIMIZATION_MODES.reduce(
  (acc, mode) => ({ ...acc, [mode.value]: mode.label }),
  {} as Record<MatchSort, string>,
);

/**
 * How much treatment a reuse type demands, low = least. Mirrors
 * PROCESSING_BURDEN in backend/matching/engine.py, and is only used to paint
 * cells - the ranking itself is done server-side.
 */
export const PROCESSING_BURDEN: Record<ReuseType, number> = {
  DIRECT_REUSE: 0,
  REQUIRES_PROCESSING: 1,
  INDUSTRIAL_ONLY: 2,
  RESTRICTED: 4,
  UNKNOWN: 3,
};

/** Ordering of the provenance tags, strongest evidence first. */
export const ORIGIN_TONE: Record<ProvenanceOrigin, string> = {
  user: 'chip-slate',
  knowledge_base: 'chip-teal',
  recipient: 'chip-clay',
  calculated: 'chip-slate-deep',
  estimate: 'chip-amber',
  ai: 'chip-cherry',
  // An outside service answered this. It is the one origin that is neither ours nor the
  // reader's, so it gets the quietest chip in the set and its label says where it came from.
  external: 'chip-slate',
};

/* --------------------------------------------------------------------------
   Copy normalisation at the display boundary.
   --------------------------------------------------------------------------
   The API and the seeded records deliberately stay written for an engineer:
   `verification: "demo"`, `origin: "sector template (demo)"`, and notes that
   name the file a value was generated from are machine provenance, and the
   backend tests assert on them. A screen is not the place for that vocabulary.

   `readerCopy` rewrites *only* the lab vocabulary into product vocabulary. It
   never removes a caveat: "not a certified figure", "an estimate, not a quote"
   and "regional potential, not a purchase forecast" all survive the rewrite,
   because those are the sentences that keep a reader from over-trusting a
   number. The word "demo" is the thing a product would not say out loud - the
   limitation it points at is stated in the sentence it replaces.
   -------------------------------------------------------------------------- */
const COPY_MAP: [RegExp, string][] = [
  // labels that name how a value was produced
  [/-\s*demo calculation\b/gi, ''],
  [/\bdemo calculation\b/gi, 'estimate'],
  [/'s demo\s+/g, "'s "],
  [/\bpublished demo\b/gi, 'published'],
  [/\bdemo composite for the pitch\b/gi, 'composite index'],
  [/\bfor the pitch\b/gi, ''],
  [/\bthe demo gazetteer\b/gi, "Symbio's place list"],
  [/\bdemo (estimate|figures?|values?|factors?|records?|assumptions?|dataset|build)\b/gi, 'recorded $1'],
  [/\bdemo-authored\b/gi, 'reference'],
  [/\bDemo knowledge base:/g, 'Knowledge base:'],
  [/\(\s*demo facility\s*\)/gi, ''],
  [/\bin-memory\b/gi, 'in this session'],
  [/\bseeded\b/gi, 'recorded'],
  [/\bfictional\b/gi, 'illustrative'],
  [/\bprototype\b/gi, 'this build'],
  // last resort: the bare word never reaches a screen
  [/\bdemo\b/gi, 'recorded'],
];
/** API or data text, reworded for a product surface without losing a caveat. */
export function readerCopy(text: string | null | undefined): string {
  if (!text) return '';
  let out = text;
  for (const [pattern, replacement] of COPY_MAP) out = out.replace(pattern, replacement);
  // tidy what the deletions leave behind: doubled spaces, a dangling dash
  return out
    .replace(/\s*[-–]\s*(?=[.,;])|\s{2,}/g, (m) => (/[.,;]/.test(m) ? m.trim() : ' '))
    .replace(/\s+([.,;])/g, '$1')
    .trim();
}

/** The machine label on a provenance row or profile, as a product label. */
export function sourceLabel(label: string | null | undefined): string {
  if (!label) return '';
  const cleaned = readerCopy(label.replace(/\s*\((?:demo|recorded|reference)\)/gi, ''))
    .replace(/\s*\+\s*/g, ' + ');
  return cleaned
    .split(' + ')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' · ');
}
