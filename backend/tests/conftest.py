"""Shared pytest fixtures.

`sys.path` points at the backend directory so `import main` resolves exactly the
way it does under `uvicorn main:app`.

Two things the production-capable build adds here:

* **No test reaches the network.** The geography providers are switched off for the
  suite unless a test asks for them, because a test that depends on a public
  geocoder is a test that fails on a plane and passes in a way that means nothing.
  Tests that exercise provider behaviour inject a stub transport instead.
* **No test touches a developer's data.** The suite never inherits `DATABASE_URL`
  from the environment; a persistence test asks for one explicitly with
  `--symbio-postgres-url`, so `pytest -q` stays a local, disposable run.
"""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--symbio-postgres-url",
        default="",
        help="A PostgreSQL (or Supabase) database to run the persistence tests against as well.",
    )


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    """The suite runs offline, without a database, and without its own guards.

    * providers off - a test that depends on a public geocoder fails on a plane, so
      provider behaviour is tested against an injected transport instead;
    * no inherited `DATABASE_URL` - persistence tests ask for one explicitly, so
      `pytest -q` cannot write into whoever's Supabase project happens to be configured;
    * rate limiting off - a full suite is hundreds of requests from one "client"
      (the test transport), and the limiter is correct to stop that. The tests in
      `test_security_baseline.py` turn it back on and exercise it on purpose.
    """
    monkeypatch.setenv("GEOCODING_PROVIDER", "off")
    monkeypatch.setenv("ROUTING_PROVIDER", "off")
    monkeypatch.setenv("SYMBIO_RATE_LIMIT", "off")
    monkeypatch.setenv("ARGON2_TEST_MODE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SYMBIO_DB_MODE", raising=False)
    monkeypatch.delenv("SYMBIO_SQLITE_PATH", raising=False)
    from db import engine as db_engine

    db_engine.replace(db_engine.Database(db_engine.config.DatabaseSettings(mode="off")))
    yield


@pytest.fixture(autouse=True)
def _clean_caches():
    """No GEO memo, no session bucket, no seeded listings leaking between modules."""
    from services import geo
    from api import security

    geo.reset_for_tests()
    security._windows.reset()
    yield


FLY_ASH_REQUEST = {
    "source_type": "industry",
    "material_description": (
        "Pulverised coal fly ash collected from the electrostatic precipitator of our "
        "thermal power station. Dry, fine grey powder, consistent quality."
    ),
    "quantity": 5.0,
    "unit": "tonnes",
    "location": "Manali, Chennai",
    "frequency": "monthly",
    "composition": "SiO2: 55%, Al2O3: 25%, CaO: 8%, Fe2O3: 6%",
}


@pytest.fixture
def fly_ash_analysis():
    from services import analysis as analysis_service

    return analysis_service.build_analysis(dict(FLY_ASH_REQUEST))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def temp_sqlite(tmp_path):
    """A migrated, disposable database, wired into the application's accessor."""
    from db import migrate
    from db.config import DatabaseSettings
    from db.engine import Database, replace

    settings = DatabaseSettings(mode="sqlite", sqlite_path=str(tmp_path / "symbio.db"))
    database = Database(settings)
    migrate.apply(database)
    replace(database)
    yield database
    replace(Database(DatabaseSettings(mode="off")))


@pytest.fixture
def postgres_url(request):
    """The Postgres half of the parametrization, when the operator asked for one."""
    url = (request.config.getoption("--symbio-postgres-url", default="") or "").strip()
    if not url:
        pytest.skip("pass --symbio-postgres-url to run the persistence tests against PostgreSQL too")
    return url


# --------------------------------------------------------------------------------------
# Persistence fixtures - a real SQLite file with the real migrations on it.
#
# `temp_sqlite` puts the store in place, and the app is started after it (it reads the
# database from the application state at startup). Sign-up goes through the API rather
# than writing rows behind it, so these tests exercise the same code paths a browser
# does. `second_client` is a second browser on the same server: needed for tenant
# isolation, because two signed-in users cannot share one cookie jar.
# --------------------------------------------------------------------------------------

TEST_PASSWORD = "Str0ng-Passw0rd!2026"


def sign_up(client, email: str, name: str, organization: str, sector: str = "building_materials"):
    """Create an account and its organisation through the public route."""
    response = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "display_name": name,
            "organization_name": organization,
            "sector": sector,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def second_client(temp_sqlite):
    """Another browser against the same application and the same database."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def tenant(temp_sqlite, client):
    """One signed-in organisation; `client` carries its session cookie."""
    return _signin(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")


@pytest.fixture
def other_tenant(temp_sqlite, second_client):
    """A second, unrelated organisation on the same database."""
    return _signin(second_client, "vikram@greenbrick.test", "Vikram S", "GreenBrick Clay")


def _signin(client, email: str, name: str, organization: str):
    sign_up(client, email, name, organization)
    return client
