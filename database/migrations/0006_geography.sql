-- 0006_geography.sql — the external geography layer (§8).
--
-- Two things this table exists to make true:
--
--   * a repeat lookup does not re-bill or re-hammer a free provider, and
--   * "when was this last updated" has an answer, so the provenance panel can say
--     when external data was fetched rather than implying it is timeless.
--
-- `resolved` records a *negative* result too. A place the provider could not find is
-- remembered as not-found, so an unresolvable location is not retried on every page
-- view - and is never, anywhere, replaced by coordinates for a different city.

create table if not exists geo_cache (
    id          text primary key,
    kind        text not null check (kind in ('geocode', 'route')),
    query_hash  text not null unique,
    query_text  text not null default '',
    provider    text not null default '',
    resolved    boolean not null default true,
    payload     text not null default '{}',           -- json, exactly what the provider gave
    fetched_at  timestamptz not null default current_timestamp,
    expires_at  timestamptz not null,
    hit_count   integer not null default 0 check (hit_count >= 0)
);

create index if not exists idx_geo_cache_expiry on geo_cache (expires_at);
create index if not exists idx_geo_cache_kind on geo_cache (kind, query_hash);
