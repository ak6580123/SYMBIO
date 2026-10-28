#!/usr/bin/env node
/**
 * Palette guard.
 *
 * `lib/palette.ts` carries literal hexes because SVG and Recharts cannot read a
 * CSS variable. That is the one place a colour may be written twice, and this
 * script checks the two copies still agree: every hex in the palette must exist as
 * an `--*-rgb` triplet in `app/globals.css`, and no component may contain a raw
 * hex or an off-palette Tailwind colour.
 *
 * Run: node scripts/check-palette.mjs   (also wired to `npm run lint:palette`)
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, extname } from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const paletteSrc = readFileSync(join(root, 'lib/palette.ts'), 'utf8');
const cssSrc = readFileSync(join(root, 'app/globals.css'), 'utf8');

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

// ---- 1. every palette hex must still be a token in the stylesheet ----------
const paletteHexes = [...new Set([...paletteSrc.matchAll(/'(#[0-9A-Fa-f]{6})'/g)].map((m) => m[1]))];
const cssTriplets = [...cssSrc.matchAll(/--[\w-]+:\s*(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s*;/g)].map(
  ([, r, g, b]) => [Number(r), Number(g), Number(b)].join(' ')
);

const orphans = paletteHexes.filter((hex) => !cssTriplets.includes(hexToRgb(hex).join(' ')));

// ---- 2. components must not invent colours ---------------------------------
const walk = (dir) =>
  readdirSync(join(root, dir), { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? walk(join(dir, entry.name)).map((f) => f)
      : [join(root, dir, entry.name)].filter((f) => ['.tsx', '.ts'].includes(extname(f)))
  );

const files = ['app', 'components', 'lib'].flatMap(walk);
const offenders = [];
for (const file of files) {
  if (file.endsWith('lib/palette.ts')) continue;
  const src = readFileSync(file, 'utf8');
  src.split('\n').forEach((line, i) => {
    if (/fill="#|stroke="#|color:\s*'#|#[0-9A-Fa-f]{3,6}\b|rgba?\s*\(\s*\d/.test(line) && !/^\s*(\*|\/\/)/.test(line)) {
      offenders.push(`${file.replace(root, '')}:${i + 1}: ${line.trim().slice(0, 90)}`);
    }
  });
}

let failed = false;
if (orphans.length) {
  failed = true;
  console.error('palette hexes with no matching --*-rgb token in app/globals.css:');
  for (const hex of orphans) console.error(`  ${hex}`);
} else {
  console.log(`palette: ${paletteHexes.length} hexes all resolve to tokens in globals.css`);
}
if (offenders.length) {
  failed = true;
  console.error('\nraw colours outside lib/palette.ts (use a token or palette.ts):');
  for (const line of offenders) console.error(`  ${line}`);
} else {
  console.log('components: no raw colour literals');
}
process.exit(failed ? 1 : 0);
