'use client';

/**
 * §12 - material similarity.
 *
 * A similarity list is a reading aid for the knowledge base: it says which other
 * materials behave alike, never which of them may be shipped to a given partner. The
 * panel prints the backend's own `score_note` for that reason and shows each
 * neighbour's safety level beside the score, so a stricter material is obvious.
 */

import { useEffect, useState } from 'react';

import { Empty, Notice, Panel, Spinner, StatusBadge, type Tone } from '@/components/ui';
import { api } from '@/lib/api';
import { inr, SAFETY_LABEL, safetyTone } from '@/lib/format';
import { scoreColor } from '@/lib/palette';
import type { SimilarityResponse } from '@/lib/types';

export default function SimilarityPanel({ materialId, materialName }: { materialId: string; materialName: string }) {
  const [data, setData] = useState<SimilarityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .similarMaterials(materialId, 6)
      .then((payload) => alive && setData(payload))
      .catch((err: Error) => alive && setError(err.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [materialId]);

  return (
    <Panel
      title="Similar materials in the knowledge base"
      subtitle={`Which of the ${data?.knowledge_base_size ?? '…'} recorded materials behave like ${materialName}`}
    >
      {loading && <Spinner label="Comparing properties, reuse routes and sectors…" />}
      {error && <Notice tone="danger">{error}</Notice>}
      {data && !loading && (
        <div className="space-y-3">
          {data.results.length === 0 ? (
            <Empty
              title="Nothing else in the knowledge base behaves like this material"
              hint="That is a real result: no shared properties, no shared reuse routes, no shared sectors."
            />
          ) : (
            <ul className="space-y-1.5">
              {data.results.map((row) => (
                <li key={row.material_id} className="border-b border-line pb-2 last:border-b-0 last:pb-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium text-text">
                      {row.name}
                      <span className="ml-2 font-normal text-text-faint">{row.category.replace(/_/g, ' ')}</span>
                    </p>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge tone={safetyTone(row.safety_level) as Tone}>{SAFETY_LABEL[row.safety_level]}</StatusBadge>
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-text-strong"
                        style={{ background: `${scoreColor(row.similarity)}33` }}
                      >
                        {row.similarity.toFixed(1)}
                      </span>
                    </div>
                  </div>

                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.min(100, row.similarity)}%`, background: scoreColor(row.similarity) }}
                    />
                  </div>

                  <p className="mt-1.5 text-[11px] leading-relaxed text-text-muted">
                    {row.shared_aspect_count} shared aspect
                    {row.shared_aspect_count === 1 ? '' : 's'}
                    {row.shared.properties?.length ? ` · properties: ${row.shared.properties.join(', ')}` : ''}
                    {row.shared.reuse_categories?.length
                      ? ` · reuse routes: ${row.shared.reuse_categories.slice(0, 3).join(', ')}`
                      : ''}
                    {row.shared.compatible_sectors?.length
                      ? ` · ${row.shared.compatible_sectors.length} overlapping sector${
                          row.shared.compatible_sectors.length === 1 ? '' : 's'
                        }`
                      : ''}
                  </p>
                  <p className="mt-1 text-[11px] tabular-nums text-text-faint">
                    {row.price_delta_inr_per_tonne === 0
                      ? 'same recorded price'
                      : `${row.price_delta_inr_per_tonne > 0 ? '+' : '−'}${inr(Math.abs(row.price_delta_inr_per_tonne))}/tonne against this material`}
                    {row.same_category ? ' · same knowledge-base category' : ''}
                  </p>
                  {row.differences.map((difference) => (
                    <p key={difference} className="mt-1 text-[11px] leading-snug text-warning">
                      {difference}
                    </p>
                  ))}
                  {row.safety_delta && (
                    <p className="mt-1 text-[11px] leading-snug text-danger">
                      Safety: {row.safety_delta}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

          <Notice tone="info">{data.score_note}</Notice>
          <p className="text-[11px] leading-relaxed text-text-faint">
            Nothing on this list changes a match, a score or a safety decision. It is a reading aid for the knowledge
            base, and each neighbour&apos;s own accepted-material rules still apply.
          </p>
        </div>
      )}
    </Panel>
  );
}
