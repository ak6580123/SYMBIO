/**
 * The palette, for the places that cannot use a Tailwind class: SVG fills in the
 * diagrams, chart series, Leaflet marker and polyline colours, and the canvas-
 * drawn score ring.
 *
 * These hexes mirror the CSS custom properties in `app/globals.css` (SVG
 * attributes and Recharts props are resolved before the cascade, so they need a
 * literal). Change a value here *and* there - `scripts/check-palette.mjs` fails if
 * a hex here stops appearing in the stylesheet, which is what keeps the two from
 * drifting apart.
 */

export const BRAND = {
  amber: '#F1E379',
  honeydew: '#D0E1CB',
  teal: '#87BBA2',
  slate: '#5D737E',
  cherry: '#500303',
} as const;

/** Readable variants of the same five (globals.css: "readable variants"). */
export const TEAL_STRONG = '#2F6B54';
export const TEAL_DEEP = '#24523F';
export const AMBER_STRONG = '#6E5E06';
export const SLATE_DEEP = '#3C5460';
export const CLAY = '#A9583F';
export const CHERRY_MID = '#7E2A22';
export const AMBER_LIGHT_LINE = '#C9B447';

export const INK = {
  strong: '#101F24',
  DEFAULT: '#1B2E34',
  muted: '#31474F',
  faint: '#4E6570',
} as const;

export const SURFACE = {
  canvas: '#EEF3EA',
  card: '#E7EFE2',
  inset: '#DFEAD9',
  muted: '#D6E4CF',
} as const;

/** Recharts draws the hover band itself, so this one needs a literal. */
export const HOVER_BAND = 'rgb(135 187 162 / 0.18)';

/** Hairline colour for grid lines and diagram scaffolding. */
export const GRID = 'rgba(93, 115, 126, 0.22)';
export const AXIS_TEXT = INK.faint;
export const TOOLTIP_STYLE = {
  background: SURFACE.card,
  border: '1px solid rgba(93, 115, 126, 0.5)',
  borderRadius: 6,
  color: INK.DEFAULT,
  fontSize: 11,
} as const;

/**
 * Categorical series. Order matters: the first four are the brand colours in the
 * hierarchy the brief asks for (teal, amber, slate, deep teal), and the last four
 * exist only so a six-bar chart is not forced to repeat a colour.
 */
export const SERIES = [
  TEAL_STRONG,
  BRAND.teal,
  BRAND.slate,
  TEAL_DEEP,
  BRAND.amber,
  SLATE_DEEP,
  CLAY,
  CHERRY_MID,
] as const;

/** Reuse type is a status, so it uses the status colours, not the series order. */
export const REUSE_TYPE_COLOR: Record<string, string> = {
  DIRECT_REUSE: TEAL_STRONG,
  REQUIRES_PROCESSING: SLATE_DEEP,
  INDUSTRIAL_ONLY: AMBER_STRONG,
  RESTRICTED: BRAND.cherry,
  UNKNOWN: BRAND.slate,
};

/** Where a number came from. Colour is decoration; every tag also says so in words. */
export const ORIGIN_COLOR: Record<string, string> = {
  user: BRAND.slate,
  knowledge_base: TEAL_STRONG,
  recipient: SLATE_DEEP,
  calculated: TEAL_DEEP,
  estimate: AMBER_STRONG,
  ai: CLAY,
};

/** Score banding, shared by the ring, the bar and the compare table. */
export function scoreColor(score: number): string {
  if (score >= 80) return TEAL_STRONG;
  if (score >= 65) return BRAND.teal;
  if (score >= 50) return AMBER_STRONG;
  return BRAND.slate;
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 0.7) return TEAL_STRONG;
  if (confidence >= 0.5) return BRAND.amber;
  return BRAND.cherry;
}

/** How much of an available weight a match actually earned (detail page bars). */
export function weightBarColor(fraction: number): string {
  if (fraction >= 0.75) return TEAL_STRONG;
  if (fraction >= 0.5) return BRAND.teal;
  return AMBER_STRONG;
}

export const MAP = {
  /** The one site the user is standing on: amber fill, dark amber ring. */
  sourceFill: BRAND.amber,
  sourceRing: AMBER_STRONG,
  recipientFill: BRAND.teal,
  recipientRing: TEAL_DEEP,
  link: 'rgba(93, 115, 126, 0.55)',
  linkActive: 'rgba(47, 107, 84, 0.85)',
  linkDim: 'rgba(93, 115, 126, 0.25)',
  popupSource: AMBER_STRONG,
  popupRecipient: TEAL_DEEP,
} as const;
