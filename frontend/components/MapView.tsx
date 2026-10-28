'use client';

// Leaflet touches `window`, so it can only render in the client bundle.
// Uses OpenStreetMap tiles - no API key, no Mapbox account.

import 'leaflet/dist/leaflet.css';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';

import {
  inr,
  REUSE_TYPE_LABEL,
  SAFETY_LABEL,
  distanceShort,
  titleCase,
} from '@/lib/format';
import { MAP } from '@/lib/palette';
import { tileHost, tileSource } from '@/lib/tiles';
import type { MapNodeExtra, MapPayload, ReuseType, SafetyLevel } from '@/lib/types';

/*
 * Basemap tiles. One provider is used: the OpenStreetMap raster endpoint, which
 * needs no key and no account. It is also the only honest option - the free
 * third-party mirror this used to hand off to now paints "API KEY REQUIRED"
 * watermarks over the map, and a watermarked street layer tells the reader less
 * than no street layer at all.
 *
 * OSM's volunteer-run tile servers answer HTTP 403 ("App is not following the
 * tile usage policy") to traffic they cannot attribute to an app - typically
 * cloud, preview and some campus networks. So when tiles are refused the map
 * drops to a plain canvas and keeps drawing what it actually computed: every
 * marker, route, distance and score here comes from /api/map, and none of it
 * depends on who draws the streets underneath.
 *
 * NEXT_PUBLIC_TILE_URL points the layer at your own provider if you have one.
 */// Markers and routes come from lib/palette.ts so the map cannot drift away from
// the rest of the app. Amber is the source you are standing on, teal is a partner.
const SOURCE_COLOR = MAP.sourceFill;
const LINK_COLOR = MAP.recipientFill;
const LINK_COLOR_DIM = MAP.linkDim;

/**
 * The centre of the *seeded* partner network, used only to frame a map that has
 * nothing measurable to show. It is a view choice about the demo network, never a
 * stand-in for where a user's material sits - that stays null until it is known.
 */
const NETWORK_OVERVIEW: LatLngExpression = [13.0827, 80.2707];

const TILES = tileSource();

export default function MapView({ data, height = 560 }: { data: MapPayload; height?: number }) {
  const [selectedLink, setSelectedLink] = useState<MapPayload['links'][number] | null>(null);
  // Two states, both useful: streets underneath, or the analysis on its own canvas.
  const [basemap, setBasemap] = useState<'tiles' | 'plain'>('tiles');
  // Why the basemap is off, so the wording can tell a refusal from a choice.
  const [tileReason, setTileReason] = useState<null | 'refused' | 'broken'>(null);
  const provider = TILES;

  /**
   * Leaflet fires `tileerror` for every tile of a broken provider, so the drop to a
   * plain canvas happens once and then stops: no retry loop, no grey squares.
   */
  const handleTileError = useCallback(() => {
    setBasemap((current) => {
      if (current === 'tiles') setTileReason('broken');
      return 'plain';
    });
  }, []);

  const nodeById = useMemo(() => new Map(data.nodes.map((node) => [node.id, node])), [data.nodes]);

  /**
   * Plotted means measurable. A place the analysis could not locate carries no
   * coordinates, so it is left off the map and said out loud below - it is never
   * pinned to the nearest city the gazetteer happens to know, which would put
   * someone's material in Chennai on the strength of a guess.
   */
  const placedNodes = useMemo(
    () => data.nodes.filter((node) => node.latitude !== null && node.longitude !== null),
    [data.nodes],
  );
  const unplacedCount = data.nodes.length - placedNodes.length;

  const center = useMemo<LatLngExpression>(() => {
    if (placedNodes.length === 0) {
      // Nothing to frame. This is the seeded network's own overview, used only to
      // choose a sensible empty view; it is not presented as anyone's location.
      return NETWORK_OVERVIEW;
    }
    const lat = placedNodes.reduce((sum, n) => sum + (n.latitude ?? 0), 0) / placedNodes.length;
    const lng = placedNodes.reduce((sum, n) => sum + (n.longitude ?? 0), 0) / placedNodes.length;
    return [lat, lng];
  }, [placedNodes]);

  // Recreate the map when the dataset changes so the view recentres.
  const [nonce, setNonce] = useState(0);
  useEffect(() => setNonce((n) => n + 1), [data.analysis_id, data.nodes.length]);

  // A blocked tile server answers with an image and an HTTP 403, so the <img>
  // element reports success and Leaflet never raises `tileerror` - which is exactly
  // how OSM's block shows up. Reading one tile with fetch is what sees the status.
  // If the answer cannot be read at all (no CORS header, offline), the layer is left
  // alone rather than switched off on a guess; `tileerror` covers that case.
  useEffect(() => {
    if (basemap !== 'tiles') return;
    let cancelled = false;
    fetch(probeUrl(TILES.url), { method: 'GET', cache: 'no-store' })
      .then((res) => {
        if (!cancelled && !res.ok) {
          setBasemap('plain');
          setTileReason('refused');
        }
      })
      .catch(() => {
        /* unreadable: keep the layer and rely on tileerror */
      });
    return () => {
      cancelled = true;
    };
  }, [basemap]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: SOURCE_COLOR }} /> Waste source
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: LINK_COLOR }} /> Potential recipient
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5" style={{ background: LINK_COLOR }} /> Match connection
        </span>
        <span className="ml-auto">{data.nodes.length} nodes · {data.links.length} connections</span>
        <button
          type="button"
          onClick={() => {
            setBasemap((current) => (current === 'tiles' ? 'plain' : 'tiles'));
            setTileReason(null);
          }}
          className="rounded-md border border-ink-600 px-2 py-0.5 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
          title="Streets come from OpenStreetMap's public tile servers. Turning them off changes nothing about the analysis."
        >
          Basemap: {basemap === 'tiles' ? 'streets' : 'off'}
        </button>
        {/* Naming the tile host is how you tell a stale browser bundle from a live
            one: watermarked tiles next to an OpenStreetMap host here means the page
            needs a hard reload, not that the app is asking for that provider. */}
        <span className="text-[10px] text-slate-600">
          tiles: {basemap === 'tiles' ? tileHost(TILES.url) : 'none'}
        </span>
      </div>

      {TILES.ignoredHost && (
        <p className="caption leading-relaxed">
          <code className="font-mono">NEXT_PUBLIC_TILE_URL</code> points at{' '}
          <code className="font-mono">{TILES.ignoredHost}</code>, whose tiles now require an API key and arrive
          watermarked, so that override is being ignored and OpenStreetMap is being used. Delete the line from{' '}
          <code className="font-mono">frontend/.env.local</code> to make it permanent, or point it at a provider you
          have a key for.
        </p>
      )}

      <div className={`overflow-hidden rounded-card border border-ink-700 ${basemap === 'plain' ? 'map-plain' : ''}`}>
        <MapContainer
          key={`${data.analysis_id ?? 'network'}-${nonce}`}
          center={center}
          zoom={data.analysis_id ? 11 : 9}
          scrollWheelZoom
          style={{ height, width: '100%' }}
        >
          {basemap === 'tiles' && (
            <TileLayer
              // Remounting the layer is how turning the basemap back on takes effect.
              key="tiles"
              attribution={provider.attribution}
              url={provider.url}
              eventHandlers={{ tileerror: handleTileError }}
            />
          )}
          {basemap === 'plain' && (
            // Attribution is about the imagery, so it is withdrawn with the imagery:
            // on a plain canvas nothing on screen comes from OpenStreetMap.
            <span className="sr-only">Basemap tiles are off.</span>
          )}

          {data.links.map((link) => {
            const from = nodeById.get(link.source);
            const to = nodeById.get(link.target);
            if (!from || !to) return null;
            // A line needs two measurable ends; one unplaced node ends the route here.
            if (from.latitude === null || from.longitude === null || to.latitude === null || to.longitude === null) {
              return null;
            }
            const active = link.match_score > 0;
            return (
              <Polyline
                key={link.id}
                positions={[
                  [from.latitude, from.longitude],
                  [to.latitude, to.longitude],
                ]}
                pathOptions={{
                  color: active ? LINK_COLOR : LINK_COLOR_DIM,
                  weight: active ? Math.max(1.5, link.match_score / 28) : 1,
                  opacity: active ? 0.75 : 0.35,
                }}
                eventHandlers={{
                  click: () => setSelectedLink(link),
                  mouseover: (e) => {
                    const target = e.target as { setStyle: (s: Record<string, unknown>) => void };
                    target.setStyle({ opacity: 1, weight: 4 });
                  },
                  mouseout: (e) => {
                    const target = e.target as { setStyle: (s: Record<string, unknown>) => void };
                    target.setStyle({ opacity: active ? 0.75 : 0.35, weight: active ? Math.max(1.5, link.match_score / 28) : 1 });
                  },
                }}
              >
                <Tooltip sticky>
                  {link.material} → {to.name}
                  {active ? ` · ${link.match_score.toFixed(0)}% match` : ' · compatible route'}
                </Tooltip>
              </Polyline>
            );
          })}

          {placedNodes.map((node) => (
            <CircleMarker
              key={node.id}
              center={[node.latitude ?? 0, node.longitude ?? 0]}
              radius={node.kind === 'source' ? 9 : 6}
              pathOptions={{
                color: node.kind === 'source' ? MAP.sourceRing : MAP.recipientRing,
                fillColor: node.kind === 'source' ? SOURCE_COLOR : LINK_COLOR,
                fillOpacity: 0.9,
                weight: 2,
              }}
            >
              <Popup minWidth={230}>
                {node.kind === 'source' ? <SourcePopup node={node} /> : <RecipientPopup node={node} />}
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      {unplacedCount > 0 && (
        <p className="caption">
          {unplacedCount} {unplacedCount === 1 ? 'place is' : 'places are'} not plotted, because that location has no
          coordinates. Distances and haulage for {unplacedCount === 1 ? 'it are' : 'them are'} marked unavailable
          rather than measured from somewhere else.
        </p>
      )}

      {basemap === 'plain' && tileReason === 'refused' && (
        <div className="rounded-card border border-ink-700 bg-ink-850/60 p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="max-w-[70ch] text-[11px] leading-relaxed text-slate-400">
              OpenStreetMap&#39;s volunteer tile servers refused the tile request this browser made (HTTP 403 - they
              block traffic they cannot attribute to an app, which covers most cloud previews and some campus
              networks), so the streets are off and the map is drawing only what Symbio computed. Nothing about the
              analysis changed: markers, routes, distances and scores come from <code className="font-mono">/api/map</code>,
              never from the tile provider. A previous version of this panel handed off to a public mirror instead; that
              mirror now stamps &ldquo;API KEY REQUIRED&rdquo; across the map, which says less than a plain canvas does.
            </p>
            <button
              onClick={() => {
                setBasemap('tiles');
                setTileReason(null);
              }}
              className="shrink-0 rounded-md border border-ink-600 px-2.5 py-1 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
            >
              Try the OpenStreetMap servers again
            </button>
          </div>
        </div>
      )}

      {basemap === 'plain' && tileReason === 'broken' && (
        <div className="rounded-card border border-amber-500/30 bg-amber-500/10 p-3">
          <p className="max-w-[70ch] text-[11px] leading-relaxed text-amber-100/80">
            The tile server returned images the map could not load, so the basemap is off. Everything drawn on top of
            it - sources, partners, connections, distances and match scores - is unaffected, because none of it comes
            from the tiles. This is a network condition, not missing data.
          </p>
          <p className="mt-1.5 text-[10px] leading-relaxed opacity-70">
            A different tile provider can be configured in the frontend environment; only tile coordinates are ever
            sent, and the README covers it.
          </p>
        </div>
      )}

      {basemap === 'plain' && tileReason === null && (
        <p className="caption leading-relaxed">
          Basemap off by choice: the canvas carries a coordinate grid instead of streets. Zoom and pan still work, and
          every marker, route and score is the same one the matching engine produced.
        </p>
      )}

      {/* Clicking a connection is how the network view reads one route at a time.
          Everything here is the link the backend sent - no derived score, no
          invented price - and an unscored link says so instead of showing a zero. */}
      {selectedLink && (
        <div className="rounded-card border border-ink-700 bg-ink-850/60 p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="text-xs font-semibold text-slate-100">
              {nodeById.get(selectedLink.source)?.name} → {nodeById.get(selectedLink.target)?.name}
            </p>
            <button
              onClick={() => setSelectedLink(null)}
              className="shrink-0 rounded-md border border-ink-600 px-2 py-0.5 text-[11px] text-slate-400 hover:border-ink-500 hover:text-slate-200"
            >
              Clear
            </button>
          </div>
          <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-[11px] sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Material" value={selectedLink.material} />
            <Field
              label="Match score"
              value={selectedLink.match_score > 0 ? `${selectedLink.match_score.toFixed(1)}%` : 'unscored route'}
            />
            <Field label="Distance" value={distanceShort(selectedLink.distance_km)} />
            <Field
              label="Quantity"
              value={
                selectedLink.quantity_t_per_month > 0
                  ? `${selectedLink.quantity_t_per_month} t/mo`
                  : 'not quantified'
              }
            />
            <Field
              label="Est. value"
              value={
                selectedLink.estimated_value_inr_per_month > 0
                  ? `${inr(selectedLink.estimated_value_inr_per_month)}/mo`
                  : 'no recorded price'
              }
            />
            <Field
              label="Reuse type"
              value={REUSE_TYPE_LABEL[selectedLink.reuse_type] ?? titleCase(selectedLink.reuse_type)}
            />
          </dl>
        </div>
      )}
    </div>
  );
}

/**
 * Popups read `node.extra`, which the backend fills from the same scored match
 * the Matches page lists - there is no second data path here. Fields the
 * payload does not carry are simply not rendered, so an unscored partner in the
 * network view never looks like it has a score.
 */
function SourcePopup({ node }: { node: MapPayload['nodes'][number] }) {
  const extra = node.extra as MapNodeExtra;
  return (
    <div className="min-w-[210px]">
      <p className="text-[10px] uppercase tracking-wider text-amber-400">Waste source</p>
      <p className="mt-0.5 text-[13px] font-semibold text-slate-100">{node.name}</p>
      <p className="caption">
        {titleCase(node.sector)} · {node.location}
      </p>
      {extra.material ? (
        <div className="mt-2 space-y-1 text-[11px] text-slate-300">
          <p>
            {extra.material} · {extra.quantity_t_per_month} t/month
            {extra.frequency ? ` · ${titleCase(extra.frequency)}` : ''}
          </p>
          <p className="text-slate-500">
            identification confidence {((extra.confidence ?? 0) * 100).toFixed(0)}% via {extra.engine ?? 'analysis'}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          {extra.description || 'No analysis has been run for this source yet.'}
        </p>
      )}
    </div>
  );
}

function RecipientPopup({ node }: { node: MapPayload['nodes'][number] }) {
  const extra = node.extra as MapNodeExtra;
  const range = extra.required_quantity_range_t_per_month;
  return (
    <div className="min-w-[230px]">
      <p className="text-[10px] uppercase tracking-wider text-emerald-400">
        {extra.partner_type_label ?? 'Potential recipient'}
      </p>
      <p className="mt-0.5 text-[13px] font-semibold text-slate-100">{node.name}</p>
      <p className="caption">
        {extra.sector_label ?? titleCase(node.sector)} · {node.location}
      </p>

      {extra.scored && (
        <p className="mt-1.5 text-[11px] text-slate-300">
          <span className="text-accent">{(extra.match_score ?? 0).toFixed(1)}% match</span>
          {extra.distance_km !== undefined ? ` · ${extra.distance_km} km away` : ''}
          {extra.material ? ` · ${extra.material}` : ''}
        </p>
      )}

      <dl className="mt-2 space-y-1 text-[11px]">
        <Line label="Accepts" value={extra.accepted_materials?.length ? extra.accepted_materials.join(', ') : null} />
        <Line
          label="Needs"
          value={range ? `${range[0]}–${range[1]} t/month` : null}
        />
        {extra.scored && extra.matched_quantity_t_per_month !== undefined && (
          <Line label="Would take" value={`${extra.matched_quantity_t_per_month} t/month`} />
        )}
        <Line
          label="Processing"
          value={extra.processing_capability?.length ? extra.processing_capability.join(', ') : 'none listed'}
        />
        <Line
          label="Use category"
          value={extra.reuse_type ? REUSE_TYPE_LABEL[extra.reuse_type as ReuseType] ?? titleCase(extra.reuse_type) : null}
        />
        <Line
          label="Safety"
          value={extra.safety_level ? SAFETY_LABEL[extra.safety_level as SafetyLevel] ?? extra.safety_level : null}
        />
        {extra.estimated_value_inr_per_month ? (
          <Line label="Est. value" value={`${inr(extra.estimated_value_inr_per_month)}/month`} />
        ) : null}
        {extra.estimated_price_inr_per_tonne ? (
          <Line label="Price" value={`${inr(extra.estimated_price_inr_per_tonne)}/t`} />
        ) : null}
      </dl>

      {extra.summary ? (
        <p className="mt-2 border-t border-ink-700 pt-1.5 text-[11px] leading-relaxed text-slate-400">
          {extra.summary}
        </p>
      ) : (
        <p className="mt-2 border-t border-ink-700 pt-1.5 text-[11px] leading-relaxed text-slate-500">
          Listed for the materials it accepts. Run an analysis for a scored match and a safety reading.
        </p>
      )}
    </div>
  );
}

function Line({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex gap-2">
      <dt className="w-[72px] shrink-0 text-slate-600">{label}</dt>
      <dd className="min-w-0 flex-1 text-slate-300">{value}</dd>
    </div>
  );
}

/** A real, cacheable tile address with the template placeholders resolved. */
function probeUrl(template: string): string {
  return template
    .replace('{s}', 'a')
    .replace('{z}', '1')
    .replace('{x}', '1')
    .replace('{y}', '1')
    .replace('{r}', '');
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-slate-600">{label}</dt>
      <dd className="truncate text-slate-300">{value}</dd>
    </div>
  );
}
