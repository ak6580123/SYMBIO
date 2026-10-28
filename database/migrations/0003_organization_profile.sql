-- 0003_organization_profile.sql — the persistent profile behind §4.
--
-- One row per organisation. The list-shaped fields are JSON in a text column: a
-- profile line is read whole and written whole, and both engines store a text
-- column the same way, which is worth more here than a queryable array. The
-- queries that matter (by organisation, by sector) are indexed below.
--
-- The seeded sector templates in `backend/data/sector_profiles.json` stay where
-- they are. They describe an *industry*; this table records what one organisation
-- said about itself. The profile view labels which of the two a line came from, so
-- a template can never be read as a declaration.

create table if not exists organization_profile (
    organization_id          text primary key references organizations (id) on delete cascade,
    sector                  text not null default '',
    products_produced        text not null default '[]',   -- json array of strings
    materials_required       text not null default '[]',   -- json array of {material_id,name,note}
    waste_streams            text not null default '[]',   -- json array of {material_id,name,quantity_t_per_month,frequency,location}
    processing_capabilities  text not null default '[]',   -- json array of strings
    certifications           text not null default '[]',   -- json array of strings, always user-stated
    contact                  text not null default '[]',   -- json object: name, email, phone
    updated_by_user_id       text references users (id) on delete set null,
    created_at               timestamptz not null default current_timestamp,
    updated_at               timestamptz not null default current_timestamp
);

create index if not exists idx_profile_sector on organization_profile (sector);
