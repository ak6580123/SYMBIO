import type { Config } from 'tailwindcss';

/**
 * Palette contract: a colour enters the app only through a token defined in
 * `app/globals.css`. Values here are `rgb(var(--x) / <alpha-value>)` so that
 * opacity modifiers (`bg-surface/60`) keep working against a variable.
 *
 * `ink-*` and `slate-*` are historical names from the dark prototype: `ink` is now
 * the surface ramp and `slate` is the text ramp. They stay as aliases because
 * several hundred class names use them; new code should reach for the semantic
 * names (`surface`, `text-muted`, `line`, `brand`, `accent`). Status families
 * (emerald/amber/rose/sky/…) likewise alias onto the five brand colours so a
 * "caution" anywhere in the app is the same amber.
 */
const alpha = (token: string) => `rgb(var(${token}) / <alpha-value>)`;

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ---- backgrounds and surfaces ------------------------------------
        canvas: alpha('--canvas-rgb'),
        surface: alpha('--surface-rgb'),
        'surface-inset': alpha('--surface-inset-rgb'),
        'surface-muted': alpha('--surface-muted-rgb'),
        honeydew: alpha('--symbio-honeydew-rgb'),

        // ---- text --------------------------------------------------------
        'text-strong': alpha('--text-strong-rgb'),
        text: alpha('--text-rgb'),
        'text-muted': alpha('--text-muted-rgb'),
        'text-faint': alpha('--text-faint-rgb'),
        'text-disabled': alpha('--text-disabled-rgb'),

        // ---- borders: the alpha is baked in, so `border-line` is the right weight
        // everywhere and nobody has to pick a number.
        line: 'rgb(var(--line-rgb) / 0.32)',
        'line-strong': 'rgb(var(--line-rgb) / 0.5)',

        // ---- brand roles -------------------------------------------------
        brand: alpha('--primary-rgb'), // muted teal: navigation, links, circularity
        'brand-strong': alpha('--symbio-teal-strong-rgb'),
        'brand-ink': alpha('--primary-ink-rgb'),
        accent: alpha('--symbio-amber-strong-rgb'), // amber: highlights, key metrics, insight
        'accent-fill': alpha('--accent-rgb'), // the pale amber itself, for CTA fills
        'accent-ink': alpha('--accent-ink-rgb'),
        cherry: alpha('--symbio-cherry-rgb'), // emphasis, warnings, critical safety

        // ---- semantic state (aliases used by existing screens) -----------
        success: alpha('--success-rgb'),
        warning: alpha('--warning-rgb'),
        danger: alpha('--danger-rgb'),
        info: alpha('--info-rgb'),

        // ---- legacy aliases ----------------------------------------------
        ink: {
          500: alpha('--symbio-slate-rgb'),
          600: `rgb(var(--line-rgb) / 0.5)`,
          700: `rgb(var(--line-rgb) / 0.32)`,
          800: alpha('--surface-muted-rgb'),
          850: alpha('--surface-rgb'),
          900: alpha('--surface-inset-rgb'),
          950: alpha('--canvas-rgb'),
        },
        slate: {
          50: `rgb(12 23 27)`,
          100: alpha('--text-strong-rgb'),
          200: alpha('--text-rgb'),
          300: alpha('--text-rgb'),
          400: alpha('--text-muted-rgb'),
          500: alpha('--text-muted-rgb'),
          600: alpha('--text-faint-rgb'),
          700: alpha('--text-faint-rgb'),
          800: alpha('--text-disabled-rgb'),
          900: alpha('--symbio-honeydew-rgb'),
        },
        // teal family = "safe / circular / positive"
        emerald: {
          200: alpha('--symbio-teal-rgb'),
          300: alpha('--symbio-teal-strong-rgb'),
          400: alpha('--symbio-teal-strong-rgb'),
          500: alpha('--symbio-teal-rgb'),
        },
        teal: {
          200: alpha('--symbio-teal-rgb'),
          300: alpha('--symbio-teal-strong-rgb'),
          400: alpha('--symbio-teal-rgb'),
          500: alpha('--symbio-teal-rgb'),
        },
        lime: { 300: alpha('--symbio-teal-strong-rgb') },
        // amber family = "caution / estimate / insight"
        amber: {
          50: alpha('--symbio-amber-rgb'),
          100: alpha('--symbio-amber-strong-rgb'),
          200: alpha('--symbio-amber-strong-rgb'),
          300: alpha('--symbio-amber-strong-rgb'),
          400: alpha('--symbio-amber-strong-rgb'),
          500: alpha('--symbio-amber-rgb'),
          600: alpha('--symbio-amber-strong-rgb'),
        },
        // cherry family = "danger / safety gate"
        rose: {
          200: alpha('--symbio-cherry-mid-rgb'),
          300: alpha('--symbio-cherry-rgb'),
          400: alpha('--symbio-cherry-rgb'),
          500: alpha('--symbio-cherry-rgb'),
        },
        orange: {
          300: alpha('--symbio-clay-rgb'),
          500: alpha('--symbio-clay-rgb'),
        },
        // blue slate + deep teal = informational and provenance tags
        sky: {
          200: alpha('--symbio-slate-deep-rgb'),
          300: alpha('--symbio-slate-deep-rgb'),
          400: alpha('--symbio-slate-rgb'),
          500: alpha('--symbio-slate-rgb'),
        },
        violet: {
          200: alpha('--symbio-slate-rgb'),
          300: alpha('--symbio-slate-deep-rgb'),
          400: alpha('--symbio-slate-rgb'),
          500: alpha('--symbio-slate-rgb'),
        },
        fuchsia: {
          200: alpha('--symbio-teal-rgb'),
          300: alpha('--symbio-teal-strong-rgb'),
          400: alpha('--symbio-teal-rgb'),
          500: alpha('--symbio-teal-rgb'),
        },
      },
      borderRadius: {
        card: 'var(--radius)',
        chip: '4px',
      },
      boxShadow: {
        panel: 'var(--shadow)',
        lift: '0 2px 10px rgba(16, 31, 36, 0.10)',
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
        display: ['var(--font-display)'],
      },
      spacing: {
        // one hairline, so "thin border" is not a judgement call per screen
        hair: '1px',
        // and one rhythm: major sections are 44px apart on every page, never
        // 24px here and 40px there
        section: '44px',
        block: '28px',
      },
    },
  },
  plugins: [],
};

export default config;
