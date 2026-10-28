// Which raster tile provider the map is allowed to draw, and why.
//
// Kept out of the component so the policy is importable without Leaflet: a .tsx that
// pulls in `leaflet/dist/leaflet.css` cannot be exercised in a plain server render, and
// an untestable policy is one that quietly regresses.

const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Hosts whose free tier is keyed. This matters because a keyed provider answers a tile
 * request with HTTP 200 and a valid PNG that has "API KEY REQUIRED" painted into it -
 * so neither the reachability probe nor Leaflet's `tileerror` can see the failure, and
 * the map silently fills with watermark tiles. A `NEXT_PUBLIC_TILE_URL` naming one of
 * these is therefore ignored rather than obeyed, and `ignoredHost` lets the panel say so
 * instead of changing the provider quietly.
 */
export const KEYED_TILE_HOSTS = ['basemaps.cartocdn.com', 'api.maptiler.com', 'tiles.mapbox.com'];

/** The tile layer to draw, with any keyed provider swapped out for OpenStreetMap. */
export function tileSource(
  configuredUrl = process.env.NEXT_PUBLIC_TILE_URL,
  configuredAttribution = process.env.NEXT_PUBLIC_TILE_ATTRIBUTION,
): { url: string; attribution: string; ignoredHost: string | null } {
  const configured = configuredUrl?.trim() ?? '';
  const attribution = configuredAttribution?.trim() || OSM_ATTRIBUTION;
  const keyed = KEYED_TILE_HOSTS.find((host) => configured.includes(host));
  if (keyed) return { url: OSM_TILE_URL, attribution: OSM_ATTRIBUTION, ignoredHost: keyed };
  return { url: configured || OSM_TILE_URL, attribution, ignoredHost: null };
}

/**
 * The host tiles come from, for the legend label. Read with a pattern rather than
 * `new URL`, because a hand-typed `NEXT_PUBLIC_TILE_URL` is allowed to be anything and a
 * cosmetic label must not be able to take the map down.
 */
export function tileHost(url: string): string {
  return url.match(/^https?:\/\/([^/]+)/)?.[1] ?? url;
}

export const DEFAULT_TILE_URL = OSM_TILE_URL;
