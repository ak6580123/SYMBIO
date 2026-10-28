-- ===========================================================================
-- Symbio — PostgreSQL / Supabase schema
--
-- The MVP does NOT need a database. It runs on:
--   * backend/data/*.json          -> materials, recipients, waste_sources
--   * backend/services/storage.py  -> analyses + matches (in process memory)
--
-- This file is the migration target. Every column maps 1:1 onto a field of the
-- Pydantic model with the same name in backend/models/schemas.py, so moving to
-- Postgres means re-implementing two modules and nothing else:
--
--   backend/knowledge_base/loader.py   -> SELECT from materials / recipients /
--                                         waste_sources / reuse_pathways /
--                                         impact_factors
--   backend/services/storage.py        -> INSERT/SELECT on analyses / matches
--
-- No Supabase auth is required or assumed. If you later add it, put RLS
-- policies on `analyses` and `matches` only.
--
-- Run with:
--   psql "$DATABASE_URL" -f database/schema.sql
-- or paste into the Supabase SQL editor.
-- ===========================================================================

create extension if not exists "pgcrypto";  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Enumerations (kept in sync with models/schemas.py)
-- ---------------------------------------------------------------------------

do $$ begin
    create type source_sector as enum ('industry', 'household', 'sme', 'agriculture', 'other');
exception when duplicate_object then null; end $$;

do $$ begin
    create type frequency as enum ('one_time', 'daily', 'weekly', 'monthly', 'continuous');
exception when duplicate_object then null; end $$;

do $$ begin
    create type reuse_type as enum (
        'DIRECT_REUSE', 'REQUIRES_PROCESSING', 'INDUSTRIAL_ONLY', 'RESTRICTED', 'UNKNOWN'
    );
exception when duplicate_object then null; end $$;

do $$ begin
    create type safety_level as enum ('low', 'moderate', 'high', 'hazardous', 'unknown');
exception when duplicate_object then null; end $$;


-- ---------------------------------------------------------------------------
-- 1. materials — the knowledge base. Source of truth for every material fact.
--    The LLM may name a material; it may never add a row here.
-- ---------------------------------------------------------------------------

create table if not exists materials (
    id                          text primary key,           -- 'fly_ash'
    name                        text not null unique,       -- 'Fly Ash'
    category                    text not null,              -- 'coal_combustion_residue'
    description                 text not null default '',
    properties                  text[] not null default '{}',
    reuse_categories            text[] not null default '{}',   -- ordered: first = primary route
    compatible_sectors          text[] not null default '{}',
    safety_level                safety_level not null default 'unknown',
    requires_processing         boolean not null default true,
    default_reuse_type          reuse_type not null default 'UNKNOWN',
    keywords                    text[] not null default '{}',   -- used by the fallback classifier
    notes                       text not null default '',
    created_at                  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 2. impact_factors — demo economic + environmental factors, split out from
--    `materials` so they can be replaced with validated LCA values (and versioned)
--    without touching material identity.
--
--    These are the ONLY numbers behind the "estimated value" and "CO2e avoided"
--    figures in the UI. They are demo values, not certified.
-- ---------------------------------------------------------------------------

create table if not exists impact_factors (
    material_id                 text primary key references materials(id) on delete cascade,
    typical_price_inr_per_tonne numeric(12,2) not null default 0,
    co2e_avoided_t_per_tonne    numeric(8,4)  not null default 0,
    is_certified                boolean not null default false,  -- false => UI shows "demo"
    source                      text not null default 'seeded demo value',
    updated_at                  timestamptz not null default now()
);


-- ---------------------------------------------------------------------------
-- 3. recipients — potential users of a waste stream (DEMO DATA in the MVP).
-- ---------------------------------------------------------------------------

create table if not exists recipients (
    id                          text primary key,           -- 'rec_cement_01'
    company_name                text not null,
    sector                      text not null,
    location                    text not null,
    latitude                    double precision not null,
    longitude                   double precision not null,
    accepted_materials          text[] not null default '{}',
    accepted_categories         text[] not null default '{}',
    min_quantity_t_per_month    numeric(12,3) not null check (min_quantity_t_per_month >= 0),
    max_quantity_t_per_month    numeric(12,3) not null,
    processing_capability       text[] not null default '{}',   -- 'licensed_handling' gates hazards
    estimated_price_inr_per_tonne numeric(12,2) not null default 0,
    reuse_type                  reuse_type not null default 'UNKNOWN',
    safety_level                safety_level not null default 'unknown',
    notes                       text not null default '',
    is_demo_data                boolean not null default true,
    created_at                  timestamptz not null default now(),
    check (max_quantity_t_per_month >= min_quantity_t_per_month)
);

create index if not exists idx_recipients_sector on recipients (sector);


-- ---------------------------------------------------------------------------
-- 4. waste_sources — where a stream comes from.
-- ---------------------------------------------------------------------------

create table if not exists waste_sources (
    id                          text primary key,           -- 'src_ind_01'
    name                        text not null,
    sector                      source_sector not null,
    location                    text not null,
    latitude                    double precision not null,
    longitude                   double precision not null,
    material_hint               text references materials(id),
    description                 text not null default '',
    is_demo_data                boolean not null default true,
    created_at                  timestamptz not null default now()
);


-- ---------------------------------------------------------------------------
-- 5. reuse_pathways — the 5-step route drawn on the match detail page.
--    Steps are stored in order; step 1 is the source sector, step 2 the material,
--    step 3 the handling requirement, step 4 the receiving sector, step 5 the product.
-- ---------------------------------------------------------------------------

create table if not exists reuse_pathways (
    id                          uuid primary key default gen_random_uuid(),
    material_id                 text not null references materials(id) on delete cascade,
    source_sector               source_sector not null,
    recipient_sector            text not null,
    reuse_category              text not null,              -- 'cement_supplementary_material'
    steps                       text[] not null,
    requires_processing         boolean not null default true,
    unique (material_id, source_sector, recipient_sector, reuse_category)
);


-- ---------------------------------------------------------------------------
-- 6. analyses — one run of the pipeline over one waste stream.
-- ---------------------------------------------------------------------------

create table if not exists analyses (
    id                          text primary key,           -- 'an_9693faef48'
    created_at                  timestamptz not null default now(),

    -- source
    source_sector               source_sector not null,
    source_location             text not null,
    source_latitude             double precision not null,
    source_longitude            double precision not null,
    quantity_t_per_month        numeric(12,3) not null check (quantity_t_per_month >= 0),
    quantity_unit               text not null default 'tonnes',
    frequency                   frequency not null default 'monthly',

    -- what the user typed
    raw_description             text not null,
    composition_raw             text,
    attached_filename           text,
    attached_text               text,

    -- what the identification stage returned (already grounded against the KB)
    material_id                 text not null references materials(id),
    confidence                  numeric(4,3) not null check (confidence between 0 and 1),
    identification_engine       text not null,              -- 'ollama:qwen2.5:3b' | 'fallback_keyword' | 'user_correction'
    identification_payload      jsonb not null,             -- full MaterialIdentification
    warnings                    text[] not null default '{}',
    -- a correction selects an existing knowledge-base material for THIS row only.
    -- Nothing in `materials` is written by it, which is how the KB stays auditable.
    user_corrected              boolean not null default false,

    -- §3 optional detail. All nullable on purpose: "we were not told" is a real
    -- answer and must not be stored as a zero or an empty string pretending to be one.
    physical_state              text,
    moisture_percent            numeric(5,2) check (moisture_percent is null or moisture_percent between 0 and 100),
    contaminants                text[] not null default '{}',
    intended_use                text,
    -- the completeness assessment, kept as returned so a past analysis can be audited
    -- after the weights in services/completeness.py move.
    completeness                jsonb,
    completeness_percent        numeric(5,1),

    -- computed totals (demo calculation)
    allocated_t_per_month       numeric(12,3) not null default 0,
    estimated_value_inr_month   numeric(14,2) not null default 0,
    estimated_co2e_t_month      numeric(12,4) not null default 0,

    is_seeded                   boolean not null default false
);

create index if not exists idx_analyses_created_at on analyses (created_at desc);
create index if not exists idx_analyses_material on analyses (material_id);


-- ---------------------------------------------------------------------------
-- 7. matches — every ranked opportunity produced by an analysis.
--    What-if scenarios are deliberately absent from this schema: they re-run the
--    engine on a temporary record and are never persisted.
--    The six components are stored individually so a score can be audited or
--    recomputed without re-running the engine.
-- ---------------------------------------------------------------------------

create table if not exists matches (
    id                          text primary key,           -- 'an_xxx:rec_yyy'
    analysis_id                 text not null references analyses(id) on delete cascade,
    recipient_id                text not null references recipients(id),

    overall_score               numeric(5,2) not null check (overall_score between 0 and 100),
    score_compatibility         numeric(5,4) not null,      -- weighted 0.30
    score_quantity              numeric(5,4) not null,      -- weighted 0.20
    score_location              numeric(5,4) not null,      -- weighted 0.15
    score_sector                numeric(5,4) not null,      -- weighted 0.15
    score_value                 numeric(5,4) not null,      -- weighted 0.10
    score_environmental         numeric(5,4) not null,      -- weighted 0.10

    reuse_type                  reuse_type not null,
    safety_level                safety_level not null,
    reasons                     text[] not null default '{}',
    cautions                    text[] not null default '{}',

    distance_km                 numeric(10,2) not null,
    matched_quantity_t_month    numeric(12,3) not null default 0,  -- standalone route volume
    allocated_t_month           numeric(12,3) not null default 0,  -- share of the source budget
    required_min_t_month        numeric(12,3) not null,
    required_max_t_month        numeric(12,3) not null,
    available_quantity_t_month  numeric(12,3) not null,

    estimated_value_inr_month   numeric(14,2) not null default 0,
    estimated_co2e_t_month      numeric(12,4) not null default 0,

    pathway_steps               text[] not null default '{}',

    is_demo_data                boolean not null default true,

    unique (analysis_id, recipient_id)
);

create index if not exists idx_matches_analysis on matches (analysis_id, overall_score desc);
create index if not exists idx_matches_recipient on matches (recipient_id);
create index if not exists idx_matches_score on matches (overall_score desc);


-- ---------------------------------------------------------------------------
-- 8. sector_profiles — what each kind of industry makes, needs and discards (§5).
--    Mirrors backend/data/sector_profiles.json. Templates describe a *sector*; the
--    recipient rows above remain the only record of a *company*. `services/profiles.py`
--    merges the two and labels which line came from which, so a template can never be
--    mistaken for a partner's own declaration.
-- ---------------------------------------------------------------------------

create table if not exists sector_profiles (
    sector              text primary key,
    label               text not null,
    products            text[] not null default '{}',
    materials_required  jsonb not null default '[]',   -- [{material_id, name, note}]
    byproducts          jsonb not null default '[]',   -- [{material_id, name, note}]
    certifications      text[] not null default '{}',
    intake_note         text,
    capability_summary  text,
    is_demo_data        boolean not null default true
);


-- ---------------------------------------------------------------------------
-- 9. listings — the demand / supply marketplace (§6).
--    Mirrors backend/data/listings.json and services/listings.py's in-memory store;
--    `to_row()` produces exactly these columns. `price_inr_per_tonne` is one column
--    for both sides, with `kind` saying who set it - a demand row's price is the
--    buyer's offer, a supply row's is the seller's ask. Nothing here is generated by
--    a model: `origin` records whether a row was seeded or published by a person.
-- ---------------------------------------------------------------------------

create table if not exists listings (
    id                      text primary key,           -- 'lst_dem_001'
    kind                    text not null check (kind in ('demand', 'supply')),
    party_recipient_id      text references recipients(id),
    party_source_id         text references waste_sources(id),
    party_name              text not null,
    location                text not null,
    latitude                double precision not null,
    longitude               double precision not null,
    material_ids            text[] not null check (cardinality(material_ids) > 0),
    quantity_t_per_month    numeric(12,3) not null check (quantity_t_per_month > 0),
    price_inr_per_tonne     numeric(12,2) not null default 0 check (price_inr_per_tonne >= 0),
    max_distance_km         numeric(6,1) check (max_distance_km is null or (max_distance_km > 0 and max_distance_km <= 500)),
    requirements            jsonb not null default '{}',
    notes                   text not null default '',
    status                  text not null default 'open'
                            check (status in ('open', 'matched', 'closed', 'expired')),
    origin                  text not null default 'seed',   -- 'seed' | 'published in this session' | user id later
    created_on              date not null default current_date,
    is_demo_data            boolean not null default true,

    check ((kind = 'demand' and party_recipient_id is not null)
           or (kind = 'supply' and party_source_id is not null))
);

create index if not exists idx_listings_kind on listings (kind, status);
create index if not exists idx_listings_material on listings using gin (material_ids);

-- A material_ids array is only queryable with an operator class; the MVP needs the
-- extension noted rather than assumed.
create extension if not exists pg_trgm;


-- ===========================================================================
-- Seeding
--
-- backend/data/generate_seed_data.py already produces the JSON the MVP loads.
-- To load the same rows into Postgres, add a small script that reads those
-- files and INSERTs them - the field names match deliberately.
--
--   materials      <- knowledge_base/materials.py  (MATERIALS)
--   impact_factors <- knowledge_base/materials.py  (typical_price_inr_per_tonne,
--                                                   co2e_avoided_t_per_tonne)
--   recipients      <- data/recipients.json
--   waste_sources   <- data/sources.json
--   sector_profiles <- data/sector_profiles.json  (data/generate_seed_data.py does not
--                     write this one; it is authored, and the listings generator reads it)
--   listings        <- data/listings.json, produced by data/generate_listings.py, which
--                     copies prices and quantity windows from the recipient and source
--                     rows above rather than stating new ones
-- ===========================================================================
