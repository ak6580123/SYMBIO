'use client';

// Leaflet touches `window`, so it can only render in the client bundle.
// Uses OpenStreetMap tiles - no API key, no Mapbox account.

import 'leaflet/dist/leaflet.css';

import { useEffect, useMemo, useState } from 'react';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';

import { inr, titleCase } from '@/lib/format';
import type { MapPayload } from '@/lib/types';

const SOURCE_COLOR = '#FCD34D';
const LINK_COLOR = '#34D399';
const LINK_COLOR_DIM = '#3D4C5C';

export default function MapView({ data, height = 560 }: { data: MapPayload; height?: number }) {
  const [selectedLink, setSelectedLink] = useState<MapPayload['links'][number] | null>(null);

  const nodeById = useMemo(() => new Map(data.nodes.map((node) => [node.id, node])), [data.nodes]);

  const center = useMemo<LatLngExpression>(() => {
    if (data.nodes.length === 0) return [13.0827, 80.2707];
    const lat = data.nodes.reduce((sum, n) => sum + n.latitude, 0) / data.nodes.length;
    const lng = data.nodes.reduce((sum, n) => sum + n.longitude, 0) / data.nodes.length;
    return [lat, lng];
  }, [data.nodes]);

  // Recreate the map when the dataset changes so the view recentres.
  const [nonce, setNonce] = useState(0);
  useEffect(() => setNonce((n) => n + 1), [data.analysis_id, data.nodes.length]);

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
      </div>

      <div className="overflow-hidden rounded-lg border border-ink-700">
        <MapContainer
          key={`${data.analysis_id ?? 'network'}-${nonce}`}
          center={center}
          zoom={data.analysis_id ? 11 : 9}
          scrollWheelZoom
          style={{ height, width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {data.links.map((link) => {
            const from = nodeById.get(link.source);
            const to = nodeById.get(link.target);
            if (!from || !to) return null;
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

          {data.nodes.map((node) => (
            <CircleMarker
              key={node.id}
              center={[node.latitude, node.longitude]}
              radius={node.kind === 'source' ? 9 : 6}
              pathOptions={{
                color: node.kind === 'source' ? '#B45309' : '#065F46',
                fillColor: node.kind === 'source' ? SOURCE_COLOR : LINK_COLOR,
                fillOpacity: 0.9,
                weight: 2,
              }}
            >
              <Popup>
                <div className="min-w-[190px]">
                  <p className="text-[10px] uppercase tracking-wider text-emerald-400">
                    {node.kind === 'source' ? 'Waste source' : 'Recipient'}
                  </p>
                  <p className="mt-0.5 text-[13px] font-semibold text-slate-100">{node.name}</p>
                  <p className="text-[11px] text-slate-400">
                    {titleCase(node.sector)} · {node.location}
                  </p>
                  {node.kind === 'source' && node.extra?.material ? (
                    <p className="mt-1.5 text-[11px] text-slate-300">
                      {String(node.extra.material)} · {String(node.extra.quantity_t_per_month)} t/month
                      <br />
                      <span className="text-slate-500">
                        identification confidence {((Number(node.extra.confidence) || 0) * 100).toFixed(0)}%
                      </span>
                    </p>
                  ) : null}
                  {node.kind === 'recipient' && node.extra?.match_score ? (
                    <p className="mt-1.5 text-[11px] text-slate-300">
                      {Number(node.extra.match_score).toFixed(0)}% match · {String(node.extra.reuse_type)}
                    </p>
                  ) : null}
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      {selectedLink && (
        <div className="panel panel-pad">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="label">Connection</p>
              <p className="mt-1 text-sm font-medium text-slate-100">
                {nodeById.get(selectedLink.source)?.name} → {nodeById.get(selectedLink.target)?.name}
              </p>
              <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] sm:grid-cols-3">
                <Field label="Material" value={selectedLink.material} />
                <Field
                  label="Match score"
                  value={selectedLink.match_score > 0 ? `${selectedLink.match_score.toFixed(1)}%` : 'not scored'}
                />
                <Field label="Distance" value={`${selectedLink.distance_km} km`} />
                <Field
                  label="Quantity"
                  value={
                    selectedLink.quantity_t_per_month > 0 ? `${selectedLink.quantity_t_per_month} t/month` : 'not allocated'
                  }
                />
                <Field
                  label="Est. value"
                  value={
                    selectedLink.estimated_value_inr_per_month > 0
                      ? inr(selectedLink.estimated_value_inr_per_month)
                      : '—'
                  }
                />
                <Field label="Reuse type" value={titleCase(selectedLink.reuse_type.toLowerCase())} />
              </dl>
            </div>
            <button onClick={() => setSelectedLink(null)} className="text-[11px] text-slate-500 underline hover:text-slate-300">
              close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-slate-600">{label}</dt>
      <dd className="truncate text-slate-300">{value}</dd>
    </div>
  );
}
