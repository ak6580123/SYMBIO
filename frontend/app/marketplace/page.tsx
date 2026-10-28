import Marketplace from '@/components/Listings';
import { ErrorState, PageHeader } from '@/components/ui';
import { api } from '@/lib/api';

export const dynamic = 'force-dynamic';

/**
 * The marketplace.
 *
 * The page holds no matching logic and no invented inventory: listings come from
 * `GET /api/listings`, which is built from the same partner records the matcher
 * reads, so a card only ever shows a party's own stated number. The README covers
 * how those records are produced and why nothing here is persisted between
 * sessions.
 */
export default async function MarketplacePage() {
  let listings;
  let materials: { id: string; name: string }[] = [];
  let partners: { id: string; name: string; kind: 'demand' | 'supply' }[] = [];
  let error: string | null = null;

  try {
    const [payload, materialRecords, recipients, sources] = await Promise.all([
      api.listings({}),
      api.materials(),
      api.recipients(),
      api.sources(),
    ]);
    listings = payload;
    materials = materialRecords.materials.map((material) => ({ id: material.id, name: material.name }));
    partners = [
      ...recipients.recipients.map((recipient) => ({
        id: recipient.id,
        name: recipient.company_name,
        kind: 'demand' as const,
      })),
      ...sources.sources.map((source) => ({ id: source.id, name: source.name, kind: 'supply' as const })),
    ];
  } catch (err) {
    error = err instanceof Error ? err.message : null;
  }

  if (!listings) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Marketplace" title="Open listings" subtitle="What the network needs, and what it has available." />
        <ErrorState
          title="Something went wrong while loading the listings."
          hint={error ?? 'The listings are read from the analysis service, which is not answering.'}
          retryHref="/marketplace"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Marketplace"
        title="Open listings"
        subtitle="Demand is what a partner says it needs; supply is what a source says it has. Both are statements by a party, and neither is a score - the deterministic matcher stays the authority on whether a stream and a partner fit."
      />
      <Marketplace initial={listings} materials={materials} partners={partners} />
    </div>
  );
}
