'use client';

// Recharts needs the client bundle (it calls React.createContext), same as Charts.tsx.

import { Sankey } from 'recharts';

import { FLOW_STAGES, STAGE_LABEL } from '@/lib/format';
import { AXIS_TEXT, INK, TEAL_STRONG } from '@/lib/palette';

/**
 * Material flow, drawn as a Sankey.
 *
 * Five stages - Source, Material, Processing, Reuse sector, Product - because
 * that is the shape the matching engine already records for every match:
 * `match.reuse_pathway.steps`. The rows come from `/api/dashboard`, which walks
 * the stored analyses and sums `allocated_t_per_month` per route, so a ribbon
 * width is the tonnage actually allocated to that route in this view. Nothing
 * about this diagram is fixed, decorative or hand-placed: with no analyses the
 * panel says so, and with one route it draws one route.
 */
export interface FlowRow {
  source: string;
  material: string;
  processing: string;
  sector: string;
  product: string;
  tonnes: number;
}

const STAGES = FLOW_STAGES;

export default function FlowDiagram({ rows }: { rows: FlowRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-slate-500">
        No allocated routes yet — analyze a waste stream to see where its tonnage would flow.
      </p>
    );
  }

  const { nodes, links } = buildGraph(rows);
  const total = rows.reduce((sum, row) => sum + row.tonnes, 0);

  return (
    <div>
      <div className="mb-1 grid grid-cols-5 gap-1 text-[10px] uppercase tracking-wider text-slate-600">
        {STAGES.map((stage) => (
          <span key={stage}>{STAGE_LABEL[stage]}</span>
        ))}
      </div>

      <div className="overflow-x-auto">
        <Sankey
          // Explicit pixel size instead of ResponsiveContainer: the layout is
          // computed from it, and it keeps the chart server-renderable.
          width={680}
          height={280}
          data={{ nodes, links }}
          nodeWidth={10}
          nodePadding={16}
          margin={{ top: 8, right: 96, bottom: 8, left: 8 }}
          node={FlowNode}
          link={FlowLink}
          // recharts types the link value key; `value` is what we build.
          dataKey="value"
        >
        </Sankey>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
        {rows.length} allocated {rows.length === 1 ? 'route' : 'routes'} · {total.toFixed(2)} t/month diverted.
        Ribbon width is allocated tonnage, so the widths add up to what this source can actually supply — routes that
        would need more than the supply left are counted as potential instead of drawn.
      </p>
    </div>
  );
}

/**
 * Collapse the route rows into a node/link graph.
 *
 * Nodes are shared by name within a stage, so two routes ending in "Blended
 * Cement / Concrete" draw into the same product node — which is the whole point
 * of reading this as a flow and not as a table.
 */
function buildGraph(rows: FlowRow[]): {
  nodes: { name: string; tonnes: number }[];
  links: { source: number; target: number; value: number }[];
} {
  // Tonnage per node is summed here, from the same rows, rather than read back
  // out of the chart library: the number next to a label is then the number the
  // data says it is, whatever recharts decides to compute internally.
  const tonnesByNode = new Map<string, number>();
  for (const row of rows) {
    STAGES.forEach((stage, index) => {
      const key = `${index}:${row[stage as keyof FlowRow]}`;
      tonnesByNode.set(key, (tonnesByNode.get(key) ?? 0) + row.tonnes);
    });
  }

  const nodes: { name: string; tonnes: number }[] = [];
  const indexOf = new Map<string, number>();
  const linkIndex = new Map<string, { source: number; target: number; value: number }>();

  const node = (stage: number, label: string): number => {
    const key = `${stage}:${label}`;
    const existing = indexOf.get(key);
    if (existing !== undefined) return existing;
    const created = nodes.push({ name: label, tonnes: Math.round((tonnesByNode.get(key) ?? 0) * 100) / 100 }) - 1;
    indexOf.set(key, created);
    return created;
  };

  for (const row of rows) {
    const ids = STAGES.map((stage, index) => node(index, String(row[stage])));
    for (let i = 0; i < ids.length - 1; i += 1) {
      const key = `${ids[i]}->${ids[i + 1]}`;
      const current = linkIndex.get(key);
      if (current) current.value = Math.round((current.value + row.tonnes) * 100) / 100;
      else linkIndex.set(key, { source: ids[i], target: ids[i + 1], value: row.tonnes });
    }
  }

  return { nodes, links: Array.from(linkIndex.values()) };
}

type FlowNodeProps = {
  x: number;
  y: number;
  width: number;
  height: number;
  index: number;
  payload?: { name?: string; tonnes?: number };
};

function FlowNode(props: FlowNodeProps) {
  const { x, y, width, height, payload } = props;
  const name = payload?.name ?? '';
  const tonnes = payload?.tonnes;
  return (
    <g>
      <title>{tonnes === undefined ? name : `${name} — ${tonnes.toFixed(2)} t/month`}</title>
      <rect x={x} y={y} width={width} height={height} rx={2} fill={TEAL_STRONG} fillOpacity={0.85} />
      <text
        x={x + width + 6}
        y={y + height / 2 - 2}
        fill={INK.strong}
        fontSize={10}
        dominantBaseline="middle"
        style={{ paintOrder: 'stroke' }}
      >
        {name.length > 24 ? `${name.slice(0, 23)}…` : name}
      </text>
      {tonnes !== undefined && (
        <text x={x + width + 6} y={y + height / 2 + 9} fill={AXIS_TEXT} fontSize={9} dominantBaseline="middle">
          {tonnes.toFixed(2)} t/mo
        </text>
      )}
    </g>
  );
}

type FlowLinkPathProps = {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  sourceControlX: number;
  targetControlX: number;
  linkWidth: number;
  payload?: { source?: { name?: string }; target?: { name?: string }; value?: number };
};

function FlowLink(props: FlowLinkPathProps) {
  const { sourceX, sourceY, targetX, targetY, sourceControlX, targetControlX, linkWidth, payload } = props;
  const from = payload?.source?.name ?? '';
  const to = payload?.target?.name ?? '';
  const tonnes = payload?.value ?? 0;
  return (
    <path
      d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      fill="none"
      stroke={TEAL_STRONG}
      strokeOpacity={0.28}
      strokeWidth={Math.max(1, linkWidth)}
    >
      <title>{`${from} → ${to} — ${tonnes.toFixed(2)} t/month allocated`}</title>
    </path>
  );
}
