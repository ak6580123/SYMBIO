import { Suspense } from 'react';

import MapShell from './shell';

export const dynamic = 'force-dynamic';

export default function MapPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold tracking-tight text-slate-100">Network Map</h1>
        <p className="mt-1 text-sm text-slate-500">
          Waste sources, potential recipients and the connections between them. Click a node for details, click a
          connection for the match.
        </p>
      </header>
      <Suspense
        fallback={<div className="panel panel-pad text-sm text-slate-500">Loading map…</div>}
      >
        <MapShell />
      </Suspense>
    </div>
  );
}
