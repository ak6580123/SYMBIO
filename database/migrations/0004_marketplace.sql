-- 0004_marketplace.sql — listings a real organisation published (§5).
--
-- The seeded marketplace stays in `backend/data/listings.json`: it is platform
-- reference data and nothing writes to it (§12). This table is the persistent half
-- of the same view, and every read of it is scoped by organization_id for private
-- access, or by `status` for what the marketplace shows publicly.
--
-- Status is the three the product talks about - active, paused, closed - and
-- `origin` keeps a row's provenance visible: 'organization' (a person published it)
-- is never the same claim as 'seed' (the shipped network).

create table if not exists organization_listings (
    id                    text primary key,               -- 'lst_2f6c…'
    organization_id       text not null references organizations (id) on delete cascade,
    facility_id           text references facilities (id) on delete set null,
    created_by_user_id    text references users (id) on delete set null,
    kind                  text not null check (kind in ('supply', 'demand')),
    quantity_t_per_month  double precision not null check (quantity_t_per_month > 0),
    quantity_min_t_per_month double precision,
    quantity_max_t_per_month double precision,
    price_inr_per_tonne   double precision not null default 0 check (price_inr_per_tonne >= 0),
    max_distance_km       double precision check (max_distance_km is null or (max_distance_km > 0 and max_distance_km <= 500)),
    frequency             text not null default 'monthly',
    application_use       text not null default '',       -- a demand listing's stated end use
    location              text,                           -- as typed; null means nobody said
    latitude              double precision,
    longitude             double precision,
    location_resolved     boolean not null default false,
    location_note         text not null default '',
    requirements          text not null default '{}',     -- json object
    notes                 text not null default '',
    status                text not null default 'active' check (status in ('active', 'paused', 'closed')),
    verification_status   text not null default 'unverified'
                              check (verification_status in ('unverified', 'pending_review', 'verified')),
    origin                text not null default 'organization',
    provenance            text not null default '[]',     -- json array of {field,value,source,at}
    created_at            timestamptz not null default current_timestamp,
    updated_at            timestamptz not null default current_timestamp
);

create index if not exists idx_listings_org_status on organization_listings (organization_id, status, kind);
create index if not exists idx_listings_marketplace on organization_listings (status, kind);
create index if not exists idx_listings_created on organization_listings (created_at);

-- The marketplace filters by material, which a JSON array in a text column cannot
-- answer. This join table is what makes that filter an index lookup instead of a
-- scan of every open listing.
create table if not exists organization_listing_materials (
    listing_id    text not null references organization_listings (id) on delete cascade,
    material_id   text not null,
    -- The order an author listed their materials in is the order the marketplace
    -- shows them, and the first one is treated as the primary material. A join table
    -- with no ordinal cannot give that back, so the number is stored rather than
    -- left to whatever index order the engine happens to read.
    ordinal       integer not null default 0,
    primary key (listing_id, material_id)
);

create index if not exists idx_listing_materials_lookup on organization_listing_materials (material_id, listing_id);
