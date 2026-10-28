"""The persistence layer, exercised on every engine this build claims to support.

The same assertions run against PostgreSQL and against the local development file,
because the migrations are portable by construction and a claim that is only true on
one of them is not worth making. When `DATABASE_URL` points at a reachable Postgres
(or Supabase) that engine joins the parametrization automatically; when it does not,
the run says so in the skip reason rather than quietly testing one thing and reporting
another.
"""

from __future__ import annotations

import pytest

from db import migrate, repositories as repo
from db.engine import Database, DatabaseUnavailable
from db.config import DatabaseSettings

# The Postgres run puts its tables in a throwaway schema (see the fixture). A test
# that deliberately opens a *second* connection has to point it at the same schema, so
# the fixture records the name here and `connect_again()` applies it. For the SQLite
# run this is a no-op: the file is the scope.
_TEST_SCHEMA: str | None = None


def connect_again(settings: DatabaseSettings) -> Database:
    database = Database(settings)
    if _TEST_SCHEMA:
        database.execute(f'set search_path to "{_TEST_SCHEMA}", public')
    return database


@pytest.fixture(params=["sqlite", "postgres"])
def db(request, tmp_path):
    """One fixture, two engines. Postgres joins when it was asked for.

    The Postgres run gets its own throwaway schema rather than the shared `public`
    one, so a test suite can never leave rows behind in a database someone is using
    for the application, and the isolation assertions are testing the query rather
    than an empty table.
    """
    import uuid

    from db.config import DatabaseSettings
    from db.engine import Database

    url = (request.config.getoption("--symbio-postgres-url", default="") or "").strip()
    if request.param == "postgres":
        if not url:
            pytest.skip("pass --symbio-postgres-url to run the persistence tests against PostgreSQL too")
        global _TEST_SCHEMA
        database = Database(DatabaseSettings(mode="postgres", url=url))
        schema = "t_" + uuid.uuid4().hex[:8]
        database.execute(f'create schema "{schema}"')
        database.execute(f'set search_path to "{schema}", public')
        _TEST_SCHEMA = schema
        migrate.apply(database)
        yield database
        _TEST_SCHEMA = None
        database.execute(f'drop schema "{schema}" cascade')
        database.close()
        return

    settings = DatabaseSettings(mode="sqlite", sqlite_path=str(tmp_path / "symbio-test.db"))
    database = Database(settings)
    migrate.apply(database)
    yield database
    database.close()


def test_migrations_are_idempotent_and_recorded(db):
    assert migrate.status(db)["pending"] == []
    assert migrate.apply(db) == []  # nothing left to do
    applied = migrate.status(db)["applied"]
    assert len(applied) == 6
    assert migrate.status(db)["checksum_drift"] == []


def test_an_account_a_tenant_and_a_profile_survive_a_reconnect(db):
    user = repo.create_user(db, email="plant@coromandel.example", password_hash="argon2$fake", display_name="Asha R")
    assert user["email"] == "plant@coromandel.example"
    assert user["is_active"] is True  # decoded as a bool, not as 1

    org = repo.create_organization(db, name="Coromandel Materials", sector="cement_manufacturing", created_by_user_id=user["id"])
    assert repo.membership(db, org["id"], user["id"])["role"] == "organization_admin"
    assert repo.organizations_for_user(db, user["id"])[0]["name"] == "Coromandel Materials"
    assert repo.get_profile(db, org["id"])["waste_streams"] == []  # seeded empty, not missing

    repo.save_profile(db, org["id"], {"sector": "cement_manufacturing", "waste_streams": [{"material_id": "fly_ash", "quantity_t_per_month": 20}]})
    repo.create_facility(db, org["id"], {"name": "Vedarsani yard", "location": "Perungudi, Chennai"})
    org2 = repo.create_organization(db, name="Second Plant", created_by_user_id=user["id"])
    repo.update_organization(db, org2["id"], {"description": "a second site"})

    db.close()  # a real restart: same file or same server, new connection
    again = connect_again(db.settings)
    assert repo.get_user(again, user["id"])["display_name"] == "Asha R"
    assert repo.get_organization(again, org["id"])["sector"] == "cement_manufacturing"
    assert repo.get_profile(again, org["id"])["waste_streams"][0]["material_id"] == "fly_ash"
    assert repo.list_facilities(again, org["id"])[0]["location"] == "Perungudi, Chennai"
    # An unplaced facility stays unplaced; nothing here defaults to a city.
    assert repo.list_facilities(again, org["id"])[0]["latitude"] is None
    assert repo.list_facilities(again, org["id"])[0]["location_resolved"] is False
    assert repo.get_organization(again, org2["id"])["description"] == "a second site"
    again.close()


def test_sign_up_cannot_take_a_second_account_on_the_same_email(db):
    repo.create_user(db, email="dup@x.example", password_hash="h")
    with pytest.raises(Exception) as excinfo:
        repo.create_user(db, email="dup@x.example", password_hash="h2")
    assert "users" in str(excinfo.value).lower() or isinstance(excinfo.value, DatabaseUnavailable)


def test_a_session_is_valid_until_it_is_revoked_or_expires(db):
    user = repo.create_user(db, email="s@x.example", password_hash="h")
    token, row = repo.create_session(db, user_id=user["id"], ttl_days=1)
    assert repo.get_session(db, token)["user_id"] == user["id"]
    assert row["token_hash"] != token and len(row["token_hash"]) == 64  # the secret is not stored

    assert repo.revoke_session(db, token) == 1
    assert repo.get_session(db, token) is None

    stale = repo.create_session(db, user_id=user["id"], ttl_days=1)[0]
    db.execute("update auth_sessions set expires_at = ? where token_hash = ?", ["2020-01-01T00:00:00Z", repo.hash_token(stale)])
    assert repo.get_session(db, stale) is None  # expired, not merely old


def test_listings_are_written_read_and_reopened_scoped_to_their_tenant(db):
    org = repo.create_organization(db, name="Alpha Cement")
    other = repo.create_organization(db, name="Beta Traders")
    record = {
        "id": "lst_alpha_1",
        "organization_id": org["id"],
        "kind": "supply",
        "quantity_t_per_month": 20.0,
        "price_inr_per_tonne": 1400.0,
        "material_ids": ["fly_ash", "bottom_ash"],
        "location": "Coimbatore, Tamil Nadu",
        "latitude": None,
        "longitude": None,
        "location_resolved": False,
        "location_note": "no coordinates recorded for this location",
        "requirements": {"moisture_below_percent": 25},
        "notes": "baled weekly",
        "status": "active",
        "verification_status": "unverified",
        "origin": "organization",
        "provenance": [{"field": "quantity_t_per_month", "value": 20, "source": "organization", "at": "today"}],
    }
    created = repo.create_listing(db, record)
    assert created["material_ids"] == ["fly_ash", "bottom_ash"]
    assert created["requirements"]["moisture_below_percent"] == 25
    assert created["location"] == "Coimbatore, Tamil Nadu"  # §9: shown as typed

    # Tenant isolation at the data layer, not only in the API.
    assert repo.get_listing(db, other["id"], "lst_alpha_1") is None
    assert repo.list_organization_listings(db, other["id"]) == []
    assert len(repo.list_organization_listings(db, org["id"])) == 1
    assert [row["id"] for row in repo.list_public_listings(db, material_id="fly_ash")] == ["lst_alpha_1"]

    assert repo.update_listing(db, other["id"], "lst_alpha_1", {"notes": "not ours to edit"}) == 0
    assert repo.update_listing(db, org["id"], "lst_alpha_1", {"notes": "now two trucks a week", "material_ids": ["fly_ash"]}) == 1
    assert repo.get_listing(db, org["id"], "lst_alpha_1")["notes"] == "now two trucks a week"
    assert repo.get_listing(db, org["id"], "lst_alpha_1")["material_ids"] == ["fly_ash"]

    assert repo.set_listing_status(db, org["id"], "lst_alpha_1", "paused") == 1
    assert repo.list_public_listings(db) == []  # a paused listing leaves the marketplace
    assert [row["id"] for row in repo.list_organization_listings(db, org["id"], status="paused")] == ["lst_alpha_1"]
    with pytest.raises(ValueError):
        repo.set_listing_status(db, org["id"], "lst_alpha_1", "withdrawn")
    with pytest.raises(Exception):
        repo.create_listing(db, {**record, "id": "lst_bad", "quantity_t_per_month": 0})


def test_an_analysis_and_its_ranked_cards_are_retrievable_and_referenceable(db):
    org = repo.create_organization(db, name="Gamma Power")
    first = repo.save_analysis(
        db,
        {
            "id": "an_abc123",
            "reference": repo.next_reference(db, "analysis", "2026"),
            "organization_id": org["id"],
            "user_id": None,
            "location": "Bengaluru, Karnataka",
            "latitude": None,
            "longitude": None,
            "location_resolved": False,
            "material_id": "fly_ash",
            "material_name": "Fly Ash",
            "quantity_t_per_month": 5.0,
            "completeness": {"percent": 64},
            "safety": {"level": "moderate"},
            "match_count": 2,
            "top_match_recipient_id": "rec_cement_01",
            "top_match_name": "Coromandel Cement Materials",
            "top_match_score": 77.5,
            "payload": {"id": "an_abc123", "matches": []},
        },
        [
            {
                "recipient": {"id": "rec_cement_01", "company_name": "Coromandel Cement Materials"},
                "overall_score": 77.5,
                "breakdown": {
                    "compatibility": 0.3,
                    "quantity": 0.15,
                    "location": 0.075,
                    "sector": 0.15,
                    "value": 0.075,
                    "environmental": 0.045,
                },
                "reuse_type": "REQUIRES_PROCESSING",
                "safety_level": "moderate",
                "distance_km": None,  # unmeasurable: stored as null, never as 0
                "matched_quantity_t_per_month": 5.0,
                "allocated_t_per_month": 5.0,
                "estimated_value_inr_per_month": 9750.0,
                "estimated_co2e_t_per_month": 3.11,
                "reasons": ["Takes fly ash"],
                "cautions": [],
                "pathway_steps": ["a", "b"],
                "transport": None,
            },
            {
                "recipient": {"id": "rec_adsorb_01", "company_name": "Adsorbent Manufacturer"},
                "overall_score": 61.0,
                "breakdown": {k: 0.1 for k in ("compatibility", "quantity", "location", "sector", "value", "environmental")},
                "reuse_type": "DIRECT_REUSE",
                "safety_level": "low",
                "distance_km": 12.4,
                "matched_quantity_t_per_month": 5.0,
                "allocated_t_per_month": 5.0,
                "estimated_value_inr_per_month": 4000.0,
                "estimated_co2e_t_per_month": 1.2,
                "reasons": [],
                "cautions": [],
                "pathway_steps": [],
                "transport": {"status": "viable", "distance_basis": "straight_line"},
            },
        ],
    )
    assert first["reference"].startswith("SYM-2026-")
    assert first["matches"][0]["distance_km"] is None
    assert first["matches"][0]["company_name"] == "Coromandel Cement Materials"
    assert first["completeness"] == {"percent": 64}
    assert first["location_resolved"] is False
    assert repo.count_analyses(db, org["id"]) == 1

    # The next reference in the same period is the next number, not a repeat.
    assert repo.next_reference(db, "analysis", "2026") != first["reference"]

    # Re-opening by reference is what the history view does.
    by_reference = repo.get_analysis(db, org["id"], first["reference"])
    assert by_reference["id"] == "an_abc123"
    assert repo.list_analyses(db, org["id"])[0]["reference"] == first["reference"]

    # Another tenant cannot read it, by id or by reference.
    stranger = repo.create_organization(db, name="Someone Else")
    assert repo.get_analysis(db, stranger["id"], "an_abc123") is None
    assert repo.get_analysis(db, stranger["id"], first["reference"]) is None
    assert repo.list_analyses(db, stranger["id"]) == []

    # Re-saving the same analysis updates it in place rather than duplicating history.
    repo.save_analysis(db, {**first, "top_match_score": 80.0}, [])
    assert repo.count_analyses(db, org["id"]) == 1
    assert repo.get_analysis(db, org["id"], "an_abc123")["top_match_score"] == 80.0
    assert repo.get_analysis(db, org["id"], "an_abc123")["matches"] == []


def test_the_geography_cache_remembers_failure_as_well_as_success(db):
    repo.cache_store(db, kind="geocode", query_text="Coimbatore, Tamil Nadu", provider="test", payload={"latitude": 11.0, "longitude": 76.96}, resolved=True, ttl_hours=6)
    hit = repo.cache_lookup(db, "geocode", "coimbatore, tamil nadu")  # case and spacing do not matter
    assert hit is not None and hit["expired"] is False
    assert hit["payload"]["latitude"] == 11.0
    assert hit["hit_count"] == 1

    repo.cache_store(db, kind="geocode", query_text="Nowhere Village", provider="test", payload={"reason": "not found"}, resolved=False, ttl_hours=6)
    miss = repo.cache_lookup(db, "geocode", "Nowhere Village")
    assert miss["resolved"] is False  # a negative answer is still a cached answer

    db.execute("update geo_cache set expires_at = ? where kind = 'route' or 1=1", ["2020-01-01T00:00:00Z"])
    assert repo.cache_lookup(db, "geocode", "Coimbatore, Tamil Nadu")["expired"] is True
    assert repo.cache_prune(db) == 2


def test_a_query_on_an_unreachable_database_reports_one_clean_error():
    # A path inside a path that cannot exist: `os.makedirs` fails, and the error that
    # reaches the caller is the reader-facing one, with no filesystem detail in it.
    database = Database(DatabaseSettings(mode="sqlite", sqlite_path="/dev/null/nope/x.db"))
    with pytest.raises(DatabaseUnavailable) as excinfo:
        database.query("select 1")
    assert "nope" not in str(excinfo.value)
    assert database.ping() is False
    assert database.status()["database"]["reachable"] is False
