-- 0001_identity.sql — accounts, organisations, membership, sessions (§2, §3)
--
-- Portable by construction: these files run unchanged on PostgreSQL (production,
-- Supabase) and on the local SQLite development file. That means text/integer/
-- double precision/boolean, CHECK constraints instead of enum types, JSON kept in
-- text columns, ids generated in the application, and `?` placeholders. The subset
-- is written down in README.md next to this file; the migration runner also refuses
-- a statement that steps outside it.
--
-- Tenant isolation is enforced in the repository layer on every read, not by a
-- default scope an author might forget.

-- ---------------------------------------------------------------------------
-- users — a person who signs in. The password never lands here: `password_hash`
-- is an Argon2id digest produced by services/identity.py, and there is no column
-- wide enough to hold a plaintext password even by mistake.
-- ---------------------------------------------------------------------------

create table if not exists users (
    id              text primary key,               -- 'usr_3f2a…'
    email           text not null unique,
    password_hash   text not null,
    display_name    text not null default '',
    is_active       boolean not null default true,
    created_at      timestamptz not null default current_timestamp,
    updated_at      timestamptz not null default current_timestamp,
    last_login_at   timestamptz,
    -- A failed-login counter, so rate limiting survives a restart and is not
    -- per-process. Deliberately not a lockout: this build has no recovery flow.
    failed_logins   integer not null default 0 check (failed_logins >= 0)
);

create index if not exists idx_users_email on users (email);

-- ---------------------------------------------------------------------------
-- organizations — the tenant every private row belongs to.
--
-- `verification_status` is a statement about the *platform's* review of this
-- organisation, not something the organisation can set for itself. Sign-up always
-- produces 'unverified'; the seeded network parties are shown as verified because
-- the dataset that ships them is platform-owned reference data.
-- ---------------------------------------------------------------------------

create table if not exists organizations (
    id                  text primary key,           -- 'org_9c14…'
    name                text not null,
    sector              text not null default '',
    description         text not null default '',
    website             text not null default '',
    contact_name        text not null default '',
    contact_email       text not null default '',
    phone               text not null default '',
    verification_status text not null default 'unverified'
                            check (verification_status in ('unverified', 'pending_review', 'verified')),
    verification_note   text not null default '',
    created_by_user_id  text references users (id) on delete set null,
    created_at          timestamptz not null default current_timestamp,
    updated_at          timestamptz not null default current_timestamp
);

create index if not exists idx_organizations_name on organizations (name);

-- ---------------------------------------------------------------------------
-- organization_members — who belongs to which tenant, with which role (§3).
-- Three roles, no inheritance, no wildcards: organization_admin, operator, viewer.
-- ---------------------------------------------------------------------------

create table if not exists organization_members (
    id              text primary key,
    organization_id text not null references organizations (id) on delete cascade,
    user_id         text not null references users (id) on delete cascade,
    role            text not null check (role in ('organization_admin', 'operator', 'viewer')),
    created_at      timestamptz not null default current_timestamp,
    updated_at      timestamptz not null default current_timestamp,
    unique (organization_id, user_id)
);

create index if not exists idx_members_user on organization_members (user_id);
create index if not exists idx_members_organization on organization_members (organization_id);

-- ---------------------------------------------------------------------------
-- auth_sessions — server-side sessions.
--
-- Only a SHA-256 of the cookie token is stored, so a database read cannot mint a
-- session. Revocation is a timestamp, not a delete: "when did this end" is part of
-- the audit trail.
-- ---------------------------------------------------------------------------

create table if not exists auth_sessions (
    id            text primary key,
    user_id       text not null references users (id) on delete cascade,
    token_hash    text not null unique,
    created_at    timestamptz not null default current_timestamp,
    last_seen_at  timestamptz not null default current_timestamp,
    expires_at    timestamptz not null,
    revoked_at    timestamptz,
    client_label  text not null default '',
    -- Which tenant this session is currently looking at, for an account that belongs
    -- to more than one organisation. It is a *view* setting: membership still decides
    -- what any request may reach.
    active_organization_id text references organizations (id) on delete set null
);

create index if not exists idx_sessions_user on auth_sessions (user_id, expires_at);
create index if not exists idx_sessions_expiry on auth_sessions (expires_at);
