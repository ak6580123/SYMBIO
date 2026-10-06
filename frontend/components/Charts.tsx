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

export const CHART_COLORS = ['#34D399', '#38BDF8', '#A3E635', '#FCD34D', '#F472B6', '#818CF8', '#FB923C', '#94A3B8'];

const AXIS = { fill: '#64748B', fontSize: 10 };
const TOOLTIP_STYLE = {
  background: '#10161D',
  border: '1px solid #2B3846',
  borderRadius: 6,
  fontSize: 11,
} as const;

export function CategoryBarChart({
  data,
}: {
  data: { name: string; tonnes: number; value: number }[];
}) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
          <CartesianGrid stroke="#1E2833" vertical={false} />
          <XAxis dataKey="name" tick={AXIS} interval={0} angle={-18} height={54} />
          <YAxis tick={AXIS} />
          <Tooltip
            cursor={{ fill: 'rgba(52,211,153,0.06)' }}
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
          <CartesianGrid stroke="#1E2833" horizontal={false} />
          <XAxis type="number" tick={AXIS} />
          <YAxis type="category" dataKey="label" tick={AXIS} width={140} />
          <Tooltip
            cursor={{ fill: 'rgba(52,211,153,0.06)' }}
            contentStyle={TOOLTIP_STYLE}
            formatter={(value) => [`${value} ${unit}`, dataKey]}
          />
          <Bar dataKey={dataKey} fill="#34D399" fillOpacity={0.8} radius={[0, 3, 3, 0]} />
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
          <CartesianGrid stroke="#1E2833" vertical={false} />
          <XAxis dataKey="label" tick={AXIS} interval={0} height={40} />
          <YAxis tick={AXIS} />
          <Tooltip cursor={{ fill: 'rgba(52,211,153,0.06)' }} contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: 11, color: '#94A3B8' }} />
          <Bar dataKey="analysed_t" name="Analysed (t/mo)" fill="#3D4C5C" radius={[3, 3, 0, 0]} />
          <Bar dataKey="diverted_t" name="Diverted (t/mo)" fill="#34D399" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
