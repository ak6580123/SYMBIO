-- 0005_analyses.sql — completed analyses, kept so they can be reopened (§6).
--
-- One row carries the input, the resolved geography, what the identification stage
-- concluded, the completeness and safety results, and a `payload` snapshot of the
-- ranked matches. The snapshot is what lets a past analysis be displayed exactly as
-- it was seen, and it is the reason the numbers in it can be re-derived: the six
-- score components are columns too, so an audit does not depend on the payload and
-- the payload never becomes the only record of a decision.
--
-- `reference` is the human label (SYM-2026-000184). It is allocated from
-- `reference_counters` in the same transaction as the insert, which is why it is
-- unique rather than derived from the id.

create table if not exists organization_analyses (
    id                        text primary key,           -- 'an_…' (unchanged from the runtime id)
    reference                 text not null unique,       -- 'SYM-2026-000184'
    organization_id           text not null references organizations (id) on delete cascade,
    user_id                   text references users (id) on delete set null,
    facility_id               text references facilities (id) on delete set null,
    source_type               text not null default 'industry',
    raw_description           text not null default '',
    composition_raw           text,
    attached_filename         text,
    quantity_t_per_month      double precision not null check (quantity_t_per_month >= 0),
    quantity_unit             text not null default 'tonnes',
    frequency                 text not null default 'monthly',
    location                  text not null,               -- exactly what the user typed
    latitude                  double precision,
    longitude                 double precision,
    location_resolved         boolean not null default false,
    location_source           text not null default '',
    material_id               text not null,
    material_name             text not null,
    identification_confidence double precision not null default 0,
    identification_engine     text not null default '',
    completeness_percent      double precision,
    completeness              text not null default '{}', -- json
    safety                    text not null default '{}',  -- json: level, gates, exclusions
    match_count               integer not null default 0,
    top_match_recipient_id    text,
    top_match_name            text not null default '',
    top_match_score           double precision,
    payload                   text not null default '{}',  -- json: the analysis as returned
    created_at                timestamptz not null default current_timestamp,
    updated_at                timestamptz not null default current_timestamp
);

create index if not exists idx_analyses_org_created on organization_analyses (organization_id, created_at);
create index if not exists idx_analyses_user on organization_analyses (user_id, created_at);
create index if not exists idx_analyses_material on organization_analyses (material_id);

create table if not exists organization_analysis_matches (
    id                        text primary key,           -- 'an_…:rec_…'
    analysis_id               text not null references organization_analyses (id) on delete cascade,
    recipient_id              text not null,
    company_name              text not null default '',
    overall_score             double precision not null,
    score_compatibility       double precision not null default 0,
    score_quantity            double precision not null default 0,
    score_location            double precision not null default 0,
    score_sector              double precision not null default 0,
    score_value               double precision not null default 0,
    score_environmental       double precision not null default 0,
    reuse_type                text not null default 'UNKNOWN',
    safety_level              text not null default 'unknown',
    distance_km               double precision,           -- null: not measurable, never 0
    distance_basis            text,                       -- 'straight_line' | 'external_route' | null
    matched_quantity_t_month  double precision not null default 0,
    allocated_t_month         double precision not null default 0,
    estimated_value_inr_month double precision not null default 0,
    estimated_co2e_t_month    double precision not null default 0,
    reasons                   text not null default '[]',  -- json
    cautions                  text not null default '[]',  -- json
    pathway_steps             text not null default '[]',  -- json
    transport                 text,                        -- json estimate, or null when unpriced
    created_at                timestamptz not null default current_timestamp,
    unique (analysis_id, recipient_id)
);

create index if not exists idx_analysis_matches_rank on organization_analysis_matches (analysis_id, overall_score);

-- Per-year counters. `next_value` is incremented under a transaction, so two
-- analyses published in the same request cycle cannot be given the same reference.
create table if not exists reference_counters (
    period      text primary key,      -- 'analysis-2026'
    next_value  integer not null default 1 check (next_value > 0)
);
