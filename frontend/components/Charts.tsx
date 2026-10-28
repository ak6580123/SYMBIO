'use client';

// Recharts (like Leaflet) calls React.createContext, which only exists in the
// client bundle. Keeping it behind 'use client' lets the dashboard stay a
// server component that fetches its own data.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { inr } from '@/lib/format';
import {
  AXIS_TEXT,
  GRID,
  HOVER_BAND,
  SERIES,
  SLATE_DEEP,
  TEAL_STRONG,
  TOOLTIP_STYLE as PALETTE_TOOLTIP,
} from '@/lib/palette';

// Every colour below comes from lib/palette.ts: that is what keeps a chart on the
// same five colours as the rest of the app.
export const CHART_COLORS = [...SERIES];

const AXIS = { fill: AXIS_TEXT, fontSize: 10 };
const TOOLTIP_STYLE = { ...PALETTE_TOOLTIP, fontSize: 11 } as const;
const CURSOR = { fill: HOVER_BAND };

export function CategoryBarChart({
  data,
}: {
  data: { name: string; tonnes: number; value: number }[];
}) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="name" tick={AXIS} interval={0} angle={-18} height={54} />
          <YAxis tick={AXIS} />
          <Tooltip
            cursor={CURSOR}
            contentStyle={TOOLTIP_STYLE}
            formatter={(value, name) => [
              name === 'tonnes' ? `${value} t/mo` : inr(Number(value)),
              name === 'tonnes' ? 'Volume' : 'Est. value',
            ]}
          />
          <Bar dataKey="tonnes" radius={[3, 3, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SectorBarChart({
  data,
  dataKey,
  unit,
}: {
  data: { label: string; value: number }[];
  dataKey: string;
  unit: string;
}) {
  const rows = data.map((row) => ({ label: row.label, [dataKey]: row.value }));
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" tick={AXIS} />
          <YAxis type="category" dataKey="label" tick={AXIS} width={140} />
          <Tooltip
            cursor={CURSOR}
            contentStyle={TOOLTIP_STYLE}
            formatter={(value) => [`${value} ${unit}`, dataKey]}
          />
          <Bar dataKey={dataKey} fill={TEAL_STRONG} fillOpacity={0.8} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SourceStackedChart({
  data,
}: {
  data: { label: string; analysed_t: number; diverted_t: number }[];
}) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: -18 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AXIS} interval={0} height={40} />
          <YAxis tick={AXIS} />
          <Tooltip cursor={CURSOR} contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: 11, color: AXIS_TEXT }} />
          <Bar dataKey="analysed_t" name="Analysed (t/mo)" fill={SLATE_DEEP} radius={[3, 3, 0, 0]} />
          <Bar dataKey="diverted_t" name="Diverted (t/mo)" fill={TEAL_STRONG} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
