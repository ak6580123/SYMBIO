-- 0002_facilities.sql — places an organisation actually operates from (§1).
--
-- A facility is the unit a listing or an analysis hangs off, because that is how
-- material is spoken about in this domain: a plant, a yard, a depot. Geography is
-- nullable on purpose (§8 of the location pass): a stated place with no coordinates
-- is a real answer, and `location_resolved` says which one this row is. No column
-- here defaults to any city.

create table if not exists facilities (
    id                text primary key,              -- 'fac_5a11…'
    organization_id   text not null references organizations (id) on delete cascade,
    name              text not null,
    location          text not null default '',      -- exactly what the user typed
    latitude          double precision,
    longitude         double precision,
    location_resolved boolean not null default false,
    location_source   text not null default '',      -- 'stated' | 'gazetteer' | 'external geocoding'
    notes             text not null default '',
    created_at        timestamptz not null default current_timestamp,
    updated_at        timestamptz not null default current_timestamp
);

create index if not exists idx_facilities_organization on facilities (organization_id, name);
