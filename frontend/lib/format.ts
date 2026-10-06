// Display formatting and shared labels.

import type { ReuseType, SafetyLevel, SourceSector } from './types';

export const inr = (value: number): string =>
  `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

export const tonnes = (value: number): string => `${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })} t`;

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

export function reuseTypeTone(type: ReuseType): string {
  switch (type) {
    case 'DIRECT_REUSE':
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300';
    case 'REQUIRES_PROCESSING':
      return 'border-sky-500/40 bg-sky-500/10 text-sky-300';
    case 'INDUSTRIAL_ONLY':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-300';
    case 'RESTRICTED':
      return 'border-rose-500/40 bg-rose-500/10 text-rose-300';
    default:
      return 'border-slate-500/40 bg-slate-500/10 text-slate-300';
  }
}

export function safetyTone(level: SafetyLevel): string {
  switch (level) {
    case 'low':
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300';
    case 'moderate':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
    case 'high':
      return 'border-orange-500/40 bg-orange-500/10 text-orange-300';
    case 'hazardous':
      return 'border-rose-500/40 bg-rose-500/10 text-rose-300';
    default:
      return 'border-slate-500/40 bg-slate-500/10 text-slate-300';
  }
}

export function scoreTone(score: number): string {
  if (score >= 80) return 'text-emerald-400';
  if (score >= 65) return 'text-lime-300';
  if (score >= 50) return 'text-amber-300';
  return 'text-slate-400';
}

export function scoreRingColor(score: number): string {
  if (score >= 80) return '#34D399';
  if (score >= 65) return '#A3E635';
  if (score >= 50) return '#FCD34D';
  return '#64748B';
}

export const titleCase = (value: string): string =>
  value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
