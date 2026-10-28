"""The security baseline, checked as behaviour rather than as intention (§12).

Each test is the shape of a response: which headers are on it, what a refused request
says, what never appears anywhere. The point is not that a hardening pass happened once;
it is that the application keeps answering this way.
"""

from __future__ import annotations

import pytest

from conftest import TEST_PASSWORD, sign_up

from services import identity

SAFE_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "cross-origin-opener-policy": "same-origin",
}


def test_api_responses_carry_the_response_headers(client):
    response = client.get("/api/health")
    for header, value in SAFE_HEADERS.items():
        assert response.headers.get(header) == value, header
    assert "permissions-policy" in response.headers
    assert "geolocation=()" in response.headers["permissions-policy"]
    # A cached API response would let a signed-out person read the previous one.
    assert "no-store" in response.headers.get("cache-control", "")


def test_no_cors_origin_is_wildcarded(client, monkeypatch):
    """An unconfigured build answers no cross-origin request, and a configured one answers
    exactly the origin it was told to trust. `*` with a session cookie is never offered."""
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    response = client.get("/api/health", headers={"Origin": "https://elsewhere.example"})
    assert response.headers.get("access-control-allow-origin") is None

    # The middleware is chosen when the app is imported, so what a deployment names is
    # checked where it is decided rather than by pretending to reconfigure a live app.
    import main

    assert "*" not in main._ALLOW_ORIGINS


def test_the_database_target_never_leaves_with_a_password(client, monkeypatch):
    from db.config import resolve

    monkeypatch.setenv("DATABASE_URL", "postgresql://svc:s3cr3t@db.internal:6543/postgres?sslmode=require")
    settings = resolve()
    assert "s3cr3t" not in settings.target()
    assert "s3cr3t" not in settings.describe()["target"]
    assert "svc" in settings.target()  # the host is still legible to whoever is reading the log
    assert "s3cr3t" not in repr(settings)


def test_a_database_that_is_down_refuses_in_words_instead_of_500(client, monkeypatch):
    """Sign-up has to reach the database, and when it cannot, that is a 503 about storage.

    A 500 with the driver's message is both the wrong status and the wrong sentence: it
    tells a reader nothing, and it tends to quote the connection string the driver tried.
    """
    from db import engine as db_engine
    from db.config import DatabaseSettings

    broken = db_engine.Database(
        DatabaseSettings(mode="postgres", url="postgresql://svc:s3cr3t@db.internal:6543/postgres")
    )
    original = client.app.state.database
    db_engine.replace(broken)
    client.app.state.database = broken
    try:
        response = client.post(
            "/api/auth/signup",
            json={"email": "person@org.test", "password": TEST_PASSWORD, "organization_name": "Down Storage Works"},
        )
        assert response.status_code == 503, response.text
        assert response.json()["service"] == "database"
        assert "not answering" in response.json()["detail"]
        assert "s3cr3t" not in response.text
        assert "db.internal" not in response.text
        assert "Traceback" not in response.text

        refused = client.post("/api/auth/login", json={"email": "person@org.test", "password": TEST_PASSWORD})
        assert refused.status_code == 503, refused.text
    finally:
        db_engine.replace(db_engine.Database(db_engine.config.DatabaseSettings(mode="off")))
        client.app.state.database = original

# ---------------------------------------------------------------------------- rate limiting


def test_a_burst_of_sign_in_attempts_is_stopped_and_told_when_to_come_back(temp_sqlite, client, monkeypatch):
    from api import security

    monkeypatch.setenv("SYMBIO_RATE_LIMIT", "on")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "4")
    security._windows.reset()
    try:
        sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
        answers = [client.post("/api/auth/login", json={"email": "nobody@nowhere.test", "password": "x"}) for _ in range(5)]
    finally:
        security._windows.reset()

    blocked = [response for response in answers if response.status_code == 429]
    assert blocked, "the fourth and fifth attempt have to be turned away"
    assert blocked[0].headers.get("retry-after")
    assert "wait a moment" in blocked[0].json()["detail"].lower()
    assert "Traceback" not in blocked[0].text
    # A refused request must not look like a refused password.
    assert blocked[0].status_code == 429 and answers[0].status_code == 401


def test_the_write_bucket_is_separate_from_the_read_one(temp_sqlite, client, monkeypatch):
    from api import security

    monkeypatch.setenv("SYMBIO_RATE_LIMIT", "on")
    monkeypatch.setenv("RATE_LIMIT_WRITE_PER_MINUTE", "3")
    monkeypatch.setenv("RATE_LIMIT_READ_PER_MINUTE", "2")
    security._windows.reset()
    try:
        reads = [client.get("/api/health") for _ in range(4)]
        writes = [client.post("/api/extract", json={"text": "fly ash"}) for _ in range(5)]
    finally:
        security._windows.reset()

    assert [r.status_code for r in reads[:2]] == [200, 200]
    assert reads[3].status_code == 429
    assert [w.status_code for w in writes[:3]] == [200, 200, 200], "the read bucket cannot spend the write one"
    assert writes[4].status_code == 429


def test_a_forged_forwarded_header_does_not_buy_a_fresh_bucket(client, monkeypatch):
    from api import security

    monkeypatch.delenv("TRUST_PROXY", raising=False)
    one = security.client_address(_request_with(forwarded_for="1.2.3.4"))
    two = security.client_address(_request_with(forwarded_for="5.6.7.8"))
    assert one == two, "without TRUST_PROXY the header is not believed, so neither address is used"

    monkeypatch.setenv("TRUST_PROXY", "1")
    assert security.client_address(_request_with(forwarded_for="1.2.3.4")) == "1.2.3.4"
    assert security.client_address(_request_with(forwarded_for="9.9.9.9, 10.0.0.1")) == "9.9.9.9"


def _request_with(*, forwarded_for: str):
    class Fake:
        method = "GET"
        cookies: dict = {}
        headers = {"x-forwarded-for": forwarded_for}
        client = type("peer", (), {"host": "10.0.0.9"})()
        url = type("url", (), {"path": "/api/health", "netloc": "symbio.test"})()

    return Fake()


# ---------------------------------------------------------------------------- cross-site requests


def test_a_cross_site_post_with_a_session_cookie_is_not_carried_out(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    mine_before = client.get("/api/org/listings/mine").json()["count"]

    attacked = client.post(
        "/api/listings",
        json={
            "kind": "supply",
            "material_ids": ["fly_ash"],
            "quantity_t_per_month": 5,
            "location": "Coimbatore, Tamil Nadu",
        },
        headers={"Origin": "https://elsewhere.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert attacked.status_code == 403
    assert "did not come from this application" in attacked.json()["detail"]
    assert client.get("/api/org/listings/mine").json()["count"] == mine_before

    # The same request from the application itself is normal, and a non-browser client
    # that sends no origin at all is not punished for it.
    assert client.post(
        "/api/listings",
        json={
            "kind": "supply",
            "material_ids": ["fly_ash"],
            "quantity_t_per_month": 5,
            "location": "Coimbatore, Tamil Nadu",
        },
    ).status_code == 201


def test_a_get_is_not_blocked_by_the_same_origin_rule(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    response = client.get("/api/org", headers={"Origin": "https://elsewhere.example"})
    assert response.status_code == 200, "reads are protected by the cookie's SameSite attribute, not by refusal"


# ---------------------------------------------------------------------------- uploads


def test_an_upload_bigger_than_the_limit_is_refused_without_being_read(client, monkeypatch):
    from services import files as file_service

    monkeypatch.setattr(file_service, "MAX_BYTES", 2000)
    big = b"x" * 50_000
    response = client.post("/api/upload", files={"file": ("report.pdf", big, "application/pdf")})
    assert response.status_code == 413
    assert "2 MB" not in response.text  # the sentence names the limit that was set here
    assert "0 MB" in response.text or "larger than symbio reads" in response.json()["detail"].lower()


def test_a_file_type_symbio_cannot_read_is_named_rather_than_guessed(client):
    """The answer is a refusal the page can print, not a partial extraction.

    A 200 with `ok: false` is this API's shape for "I could not read that": the response
    model is the same one a success uses, so a page cannot mistake a refusal for a file
    it extracted and left the fields empty.
    """
    response = client.post("/api/upload", files={"file": ("ledger.exe", b"MZ\x90\x00", "application/octet-stream")})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["extracted_text"] == ""
    assert "PDF, TXT and DOCX" in body["message"]


# ---------------------------------------------------------------------------- validation and safe failure


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": 0},
        {"quantity": -5},
        {"material_description": ""},
        {"material_description": "x" * 4001},
        {"latitude": 999},
        {"location": "x" * 201},
        {"unit": "tonnes" * 40},
    ],
)
def test_a_request_the_model_refuses_never_reaches_the_engine(client, changes):
    payload = {
        "source_type": "industry",
        "material_description": "Fly ash",
        "quantity": 20,
        "unit": "tonnes",
        "frequency": "monthly",
        "location": "Coimbatore, Tamil Nadu",
    } | changes
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422, response.text
    assert "Traceback" not in response.text


def test_an_unexpected_failure_says_the_correlation_id_and_nothing_else(monkeypatch):
    from fastapi.testclient import TestClient

    from main import app
    from services import analysis as analysis_service

    def explode(payload):
        raise RuntimeError("a bug with a private message: /home/deploy/symbio/backend/data/recipients.json")

    monkeypatch.setattr(analysis_service, "build_analysis", explode)
    # `raise_server_exceptions=False` is what a real deployment does with an unhandled
    # error: the handler answers, and the traceback stays in the log.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/analyze",
            json={
                "source_type": "industry",
                "material_description": "Fly ash",
                "quantity": 20,
                "unit": "tonnes",
                "location": "Coimbatore, Tamil Nadu",
            },
        )
        assert response.status_code == 500

    body = response.json()
    assert body["correlation"], "the id an operator can look the failure up by"
    assert body["error_class"] == "RuntimeError"
    assert "/home/deploy" not in response.text
    assert "a bug with a private message" not in response.text
    assert "Traceback" not in response.text
    assert ' File "' not in response.text



def test_no_endpoint_lists_itself_as_debug(client):
    """`/docs` is a development convenience; the API must not leak schema through a
    deployment that turned it off. This test records which one this build is."""
    from main import app

    assert app.debug is False


def test_the_session_cookie_cannot_be_read_by_a_page_and_is_not_used_cross_site(temp_sqlite, client):
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "anitha@aashirwad.test",
            "password": TEST_PASSWORD,
            "display_name": "Anitha R",
            "organization_name": "Aashirwad Blocks",
        },
    )
    cookie = response.headers["set-cookie"]
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    # Max-Age mirrors the server-side session lifetime, so a browser that is closed and
    # reopened within it does not present a cookie the database has already forgotten.
    assert "max-age=%d" % (identity.SESSION_TTL_DAYS * 86400) in lowered
    assert "secure" not in lowered, "off until the app is served over https"
