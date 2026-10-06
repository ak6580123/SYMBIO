import { titleCase } from '@/lib/format';

export interface FlowLink {
  material: string;
  sector: string;
  tonnes: number;
}

/**
 * Circular-flow visualisation.
 *
 * A true Sankey needs a layout library; this is the same information drawn with
 * proportional ribbons and plain CSS, which keeps the dependency count at zero
 * and stays readable at demo scale. Ribbon width is proportional to tonnes.
 */
export default function FlowDiagram({
  links,
  sourceLabel = 'Waste sources',
}: {
  links: FlowLink[];
  sourceLabel?: string;
}) {
  if (links.length === 0) {
    return <p className="py-6 text-center text-sm text-slate-500">No allocated routes yet — analyze a waste stream.</p>;
  }

  const total = links.reduce((sum, link) => sum + link.tonnes, 0);
  const max = Math.max(...links.map((link) => link.tonnes));
  const shown = [...links].sort((a, b) => b.tonnes - a.tonnes).slice(0, 7);

  return (
    <div className="grid grid-cols-[minmax(110px,0.8fr)_44px_minmax(0,1.6fr)] items-stretch gap-2 sm:grid-cols-[150px_56px_1fr]">
      {/* Source column */}
      <div className="flex flex-col justify-center gap-1.5">
        <div className="rounded-md border border-accent/30 bg-accent/10 px-3 py-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-accent/80">Source</p>
          <p className="mt-0.5 text-xs font-medium text-slate-100">{sourceLabel}</p>
          <p className="mt-0.5 text-[11px] tabular-nums text-slate-400">{total.toFixed(2)} t/mo</p>
        </div>
      </div>

      {/* Ribbons */}
      <div className="flex flex-col justify-center gap-1.5">
        {shown.map((link) => (
          <div key={`${link.material}-${link.sector}`} className="flex h-full items-center">
            <div
              className="w-full rounded-sm bg-gradient-to-r from-accent/50 to-accent/15"
              style={{ height: `${Math.max(14, (link.tonnes / max) * 34)}px` }}
              title={`${link.tonnes.toFixed(2)} t/month`}
            />
          </div>
        ))}
      </div>

      {/* Destination column */}
      <div className="flex flex-col justify-center gap-1.5">
        {shown.map((link) => (
          <div
            key={`${link.material}-${link.sector}`}
            className="flex items-center justify-between gap-2 rounded-md border border-ink-700 bg-ink-900 px-3 py-2"
            style={{ minHeight: 34 }}
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-slate-200">{titleCase(link.sector)}</p>
              <p className="truncate text-[10px] text-slate-500">{link.material}</p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-[11px] tabular-nums text-accent">{link.tonnes.toFixed(2)} t</p>
              <p className="text-[10px] tabular-nums text-slate-600">
                {((link.tonnes / total) * 100).toFixed(0)}%
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
