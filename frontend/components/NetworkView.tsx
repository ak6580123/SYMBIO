'use client';

/**
 * Network view of the same result set the map shows.
 *
 * The map answers "where"; this answers "who is connected to whom, through which
 * material, at what volume". Both are rendered from one `/api/map` payload, which
 * is built from the same filtered, sorted matches as the list - so a route that is
 * missing here is missing there too, and the safety layer has already been applied
 * before either is drawn. Pure SVG, no mapping library, no tile provider.
 */

import { distanceShort, inr, REUSE_TYPE_LABEL } from '@/lib/format';
import { BRAND, INK, REUSE_TYPE_COLOR } from '@/lib/palette';
import type { MapPayload, ReuseType } from '@/lib/types';

const TYPE_COLOR: Record<ReuseType, string> = {
  DIRECT_REUSE: REUSE_TYPE_COLOR.DIRECT_REUSE,
  REQUIRES_PROCESSING: REUSE_TYPE_COLOR.REQUIRES_PROCESSING,
  INDUSTRIAL_ONLY: REUSE_TYPE_COLOR.INDUSTRIAL_ONLY,
  RESTRICTED: REUSE_TYPE_COLOR.RESTRICTED,
  UNKNOWN: REUSE_TYPE_COLOR.UNKNOWN,
};

type Node = MapPayload['nodes'][number];
type Link = MapPayload['links'][number];

const ROW = 34;
const PAD = 26;

/**
 * Recipients are capped so the diagram stays readable: the payload arrives in the
 * order the engine ranked it, so this draws the strongest connections and says
 * how many it left out. The map and the list still show all of them.
 */
const MAX_RECIPIENTS = 12;

export default function NetworkView({ payload }: { payload: MapPayload }) {
  const sources = payload.nodes.filter((node) => node.kind === 'source');
  const allRecipients = payload.nodes.filter((node) => node.kind === 'recipient');
  const recipients = allRecipients.slice(0, MAX_RECIPIENTS);
  const kept = new Set(recipients.map((node) => node.id));
  const links = payload.links.filter((link) => kept.has(link.target));
  const materials = Array.from(new Set(links.map((link) => link.material)));

  if (payload.links.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-500">
        No connections to draw for this result set. The map has nothing to plot either - that is the same answer, not a
        rendering problem.
      </p>
    );
  }

  const rows = Math.max(sources.length, recipients.length, materials.length);
  const width = 960;
  const height = rows * ROW + PAD * 2 + 26;
  const x = { source: 150, material: width / 2, recipient: width - 150 };

  // Column positions are derived from the payload order, which is the order the
  // engine ranked these routes in. Sorting here would hide the effect of the
  // optimisation mode the list is using.
  const position = (list: Node[]) => {
    const step = (height - PAD * 2) / Math.max(1, list.length - 1 || 1);
    const centre = (index: number) => (list.length === 1 ? height / 2 : PAD + index * step);
    return new Map(list.map((node, index) => [node.id, centre(index)] as const));
  };
  const sourceY = position(sources);
  const recipientY = position(recipients);
  const materialStep = (height - PAD * 2) / Math.max(1, materials.length - 1 || 1);
  const materialY = new Map(
    materials.map((name, index) => [
      name,
      materials.length === 1 ? height / 2 : PAD + index * materialStep,
    ]),
  );

  const maxTonnes = Math.max(...links.map((link) => link.quantity_t_per_month), 0.1);
  const byId = new Map(payload.nodes.map((node) => [node.id, node] as const));
  const bestScore = new Map<string, number>();
  for (const link of payload.links) {
    bestScore.set(link.target, Math.max(bestScore.get(link.target) ?? 0, link.match_score));
  }

  const label = (node: Node, suffix: string) => (
    <text x={x[node.kind]} y={(node.kind === 'source' ? sourceY : recipientY).get(node.id) ?? 0} className="fill-slate-300" fontSize={11}>
      <tspan x={x[node.kind]} textAnchor={node.kind === 'source' ? 'end' : 'start'} dx={node.kind === 'source' ? -12 : 12}>
        {node.name.length > 26 ? `${node.name.slice(0, 25)}…` : node.name}
      </tspan>
      <tspan x={x[node.kind]} dy={12} fontSize={9} className="fill-slate-500" textAnchor={node.kind === 'source' ? 'end' : 'start'} dx={node.kind === 'source' ? -12 : 12}>
        {suffix}
      </tspan>
    </text>
  );

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-[680px]" role="img" aria-label="Source to material to recipient network">
          {/* links, source -> material -> recipient */}
          {links.map((link) => {
            const from = sourceY.get(link.source);
            const to = recipientY.get(link.target);
            const through = materialY.get(link.material);
            if (from === undefined || to === undefined || through === undefined) return null;
            const stroke = TYPE_COLOR[link.reuse_type] ?? REUSE_TYPE_COLOR.UNKNOWN;
            const weight = 0.8 + (link.quantity_t_per_month / maxTonnes) * 4.2;
            const note = (
              <title>{`${link.material} · ${byId.get(link.source)?.name} → ${byId.get(link.target)?.name} · ${
                link.quantity_t_per_month
              } t/mo · ${link.match_score}% · ${distanceShort(link.distance_km)} · ${inr(link.estimated_value_inr_per_month)}/mo (estimate)`}</title>
            );
            return (
              <g key={link.id} opacity={0.55}>
                {note}
                <path
                  d={`M ${x.source} ${from} C ${(x.source + x.material) / 2} ${from}, ${(x.source + x.material) / 2} ${through}, ${x.material} ${through}`}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={weight}
                />
                <path
                  d={`M ${x.material} ${through} C ${(x.material + x.recipient) / 2} ${through}, ${(x.material + x.recipient) / 2} ${to}, ${x.recipient} ${to}`}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={weight}
                />
              </g>
            );
          })}

          {/* nodes */}
          {sources.map((node) => (
            <g key={node.id}>
              <circle cx={x.source} cy={sourceY.get(node.id)} r={5} fill={INK.strong} />
              {label(node, `${linkCount(payload.links, node.id, 'source')} route(s)`)}
            </g>
          ))}
          {materials.map((name) => (
            <g key={name}>
              <circle cx={x.material} cy={materialY.get(name)} r={4} fill={BRAND.teal} />
              <text x={x.material} y={(materialY.get(name) ?? 0) - 10} textAnchor="middle" fontSize={10} className="fill-emerald-300/80">
                {name}
              </text>
            </g>
          ))}
          {recipients.map((node) => (
            <g key={node.id}>
              <circle cx={x.recipient} cy={recipientY.get(node.id)} r={4} fill={BRAND.slate} />
              {label(node, `best ${bestScore.get(node.id)?.toFixed(0) ?? '–'}% · ${node.sector.replace(/_/g, ' ')}`)}
            </g>
          ))}

          <text x={x.source} y={14} textAnchor="end" fontSize={9} className="fill-slate-500 uppercase">
            Waste source
          </text>
          <text x={x.material} y={14} textAnchor="middle" fontSize={9} className="fill-slate-500 uppercase">
            Material
          </text>
          <text x={x.recipient} y={14} fontSize={9} className="fill-slate-500 uppercase">
            Recipient
          </text>
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
        {Object.entries(REUSE_TYPE_LABEL).map(([type, text]) => (
          <span key={type} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded" style={{ background: TYPE_COLOR[type as ReuseType] }} />
            {text}
          </span>
        ))}
        <span className="text-slate-600">line width = tonnes per month · hover a line for the numbers</span>
        {allRecipients.length > recipients.length && (
          <span className="text-amber-300/80">
            showing the top {recipients.length} of {allRecipients.length} recipients, in engine order
          </span>
        )}
      </div>
    </div>
  );
}

function linkCount(links: Link[], nodeId: string, side: 'source' | 'target') {
  return links.filter((link) => link[side] === nodeId).length;
}
