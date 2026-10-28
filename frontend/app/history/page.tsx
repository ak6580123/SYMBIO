'use client';

/**
 * §6 - Analysis History.
 *
 * A row here is a run that was stored against this organisation: its reference, what was
 * typed, where, when, and the best match the engine reached at the time. Opening a row
 * reopens the stored analysis rather than recomputing anything, so a score never changes
 * because the seed data or a weight moved afterwards.
 *
 * With no database there is nothing to list, and this page says so. A session's analyses
 * are readable while the tab is open; they are not history.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

import { Empty, ErrorState, Notice, PageHeader, Section, Spinner, StatusBadge } from '@/components/ui';
import { ApiError, api } from '@/lib/api';
import { useSession } from '@/lib/session';
import type { HistoryResponse } from '@/lib/types';

export default function HistoryPage() {
  const { status } = useSession();
  const [payload, setPayload] = useState<HistoryResponse | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    try {
      setPayload(await api.history(50));
    } catch (err) {
      setPayload(null);
      setFailure(err instanceof ApiError ? err.message : 'The history could not be read.');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (status === 'signed_in') void load();
    if (status !== 'checking') setBusy(false);
  }, [status, load]);

  if (status === 'checking' || (status === 'signed_in' && busy && !payload)) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Organisation" title="Analysis history" />
        <Spinner label="Reading the stored runs…" />
      </div>
    );
  }

  if (status !== 'signed_in') {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Organisation" title="Analysis history" subtitle="Every analysis stored against your organisation." />
        <Notice tone="info">
          History belongs to an account.{' '}
          <Link href="/login?next=/history" className="link">
            Sign in
          </Link>{' '}
          to see the runs your organisation saved.
        </Notice>
      </div>
    );
  }

  if (failure || !payload) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Organisation" title="Analysis history" />
        <ErrorState title="The history could not be read." hint={failure ?? 'No answer came back.'} onRetry={load} />
      </div>
    );
  }

  return (
    <div className="space-y-9">
      <PageHeader
        eyebrow="Organisation"
        title="Analysis history"
        subtitle="A stored run keeps its own numbers. Opening it shows what the engine decided then."
        meta={
          <p className="text-[12px] text-text-faint">
            {payload.count} analys{payload.count === 1 ? 'is' : 'es'} on record
          </p>
        }
      />

      <Section title="Saved analyses">
        {payload.analyses.length === 0 ? (
          <Empty
            title="Nothing saved yet."
            hint="An analysis is stored when a signed-in operator runs one and the database accepts it. Until then the result stays with this browser session."
            action={
              <Link href="/analyze" className="link text-[12.5px]">
                Run an analysis
              </Link>
            }
          />
        ) : (
          <div className="space-y-2.5">
            {payload.analyses.map((row) => (
              <article key={row.id} className="panel px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[12px] text-text-muted">{row.reference}</span>
                      <span className="text-sm font-semibold text-text-strong">{row.material}</span>
                      {!row.location_resolved && row.location && (
                        <StatusBadge tone="amber" title="The place that was typed could not be placed, so this run carries no distance.">
                          Location not placed
                        </StatusBadge>
                      )}
                    </p>
                    <p className="mt-1 text-[12.5px] text-text-muted">
                      {row.quantity_t_per_month} {row.quantity_unit}/month · {row.location || 'no location stated'} · {row.created_on}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-4">
                    <p className="text-right text-[12.5px]">
                      <span className="label block">Best match</span>
                      <span className="text-text">
                        {row.best_match || 'nothing in range'}
                        {row.best_match_score !== null && row.best_match_score !== undefined ? (
                          <span className="tabular-nums text-text-muted"> · {row.best_match_score.toFixed(1)}</span>
                        ) : null}
                      </span>
                    </p>
                    <p className="text-right text-[12.5px]">
                      <span className="label block">Matches</span>
                      <span className="tabular-nums text-text">{row.match_count}</span>
                    </p>
                    <Link href={`/matches?analysis=${encodeURIComponent(row.id)}`} className="link text-[12.5px]">
                      Reopen
                    </Link>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </Section>

      {payload.persistence && !payload.persistence.reachable && (
        <Notice tone="warn">
          Symbio is not writing to a database right now, so this list shows whatever the running process still holds.{' '}
          {payload.persistence.note}
        </Notice>
      )}
    </div>
  );
}
