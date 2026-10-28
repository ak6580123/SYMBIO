"""Every external dependency, failing on purpose (§8, §12).

The application has three outside things it leans on: a geocoder, a router and the
database. Each is exercised here in the state a real outage puts it in - 503, 429,
garbage, nothing at all - and what is asserted each time is the same pair of facts: the
run still produces the numbers the engine computed, and the thing that could not be
measured is reported as not measured. A provider is never allowed to be survived silently.

The transports are stubbed rather than called, because a test that depends on a public
geocoder passes in a way that means nothing and fails on a plane.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def providers(monkeypatch):
    """Both providers on, and nothing on the network but the stub a test installs."""
    from services import geo

    geo.reset_for_tests()
    monkeypatch.setenv("GEOCODING_PROVIDER", "nominatim")
    monkeypatch.setenv("ROUTING_PROVIDER", "osrm")
    monkeypatch.setenv("GEO_CACHE_HOURS", "0")
    yield geo
    geo.HTTP_TRANSPORT = None
    geo.reset_for_tests()


def serve(responses):
    """A stub transport answering in order, recording what it was asked for."""
    import httpx

    asked: list[str] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        reply = queue.pop(0) if queue else responses[-1]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(request)
        status, payload = reply
        if isinstance(payload, (dict, list)):
            return httpx.Response(status, json=payload)
        return httpx.Response(status, text=str(payload))

    return httpx.MockTransport(handler), asked


PLACES = {
    "Coimbatore, Tamil Nadu": (11.001812, 76.962843),
    "Hosur, Tamil Nadu": (12.7409, 77.8253),
}


def geocoder_answers(request):
    """Answer a Nominatim search from the place table above."""
    from urllib.parse import parse_qs, unquote

    query = parse_qs(request.url.query.decode()).get("q", [""])[0]
    hit = PLACES.get(unquote(query).strip())
    if hit is None:
        return 200, []
    return 200, [{"lat": str(hit[0]), "lon": str(hit[1]), "display_name": query, "addresstype": "city"}]


# ---------------------------------------------------------------------------- geocoding


def test_a_geocoder_that_is_down_keeps_the_location_text_and_admits_no_coordinates(providers, monkeypatch):
    from services import analysis

    transport, asked = serve([(503, "service unavailable")])
    providers.HTTP_TRANSPORT = transport
    lat, lng, exact, info = analysis.resolve_coordinates_detailed("Nowhere Village", None, None)
    assert (lat, lng, exact) == (None, None, False)
    assert info["source"] == "unresolved"
    assert asked, "the geocoder was at least asked"


def test_an_unplaceable_name_is_not_invented(providers):
    from services import analysis

    transport, _ = serve([(200, [])])
    providers.HTTP_TRANSPORT = transport
    lat, lng, exact, info = analysis.resolve_coordinates_detailed("Chennaiyur", None, None)
    assert (lat, lng, exact) == (None, None, False)
    assert info["reason"] == "not found"


def test_a_place_the_geocoder_knows_becomes_a_coordinate_and_says_where_it_came_from(providers):
    from services import analysis

    transport, _ = serve([geocoder_answers])
    providers.HTTP_TRANSPORT = transport
    for place, expected in (("Coimbatore, Tamil Nadu", 11.002), ("Hosur, Tamil Nadu", 12.741)):
        lat, lng, exact, info = analysis.resolve_coordinates_detailed(place, None, None)
        assert exact is True and round(lat, 3) == expected, place
        # It says so, in the same field a reader can check: the number came from outside.
        assert info["source"] == "external geocoding"
        assert info["matched_as"] == place


def test_a_throttled_geocoder_is_set_aside_rather_than_kept_being_asked(providers):
    transport, asked = serve([(429, "slow down"), (429, "slow down"), (429, "slow down"), (200, [])])
    providers.HTTP_TRANSPORT = transport
    for _ in range(4):
        providers.geocode("Somewhere New")
    # Three refusals in a row and the provider is set aside for a minute rather than
    # asked again on every page view.
    assert len(asked) == 3
    assert providers.status()["geocoding"]["state"] == "cooling down"


def test_a_geocode_answer_that_is_not_json_is_refused_like_any_other_failure(providers):
    transport, _ = serve([(200, "<html>not json</html>")])
    providers.HTTP_TRANSPORT = transport
    result = providers.geocode("Coimbatore, Tamil Nadu")
    assert result.ok is False
    assert result.reason == "invalid response"


# ---------------------------------------------------------------------------- routing


def test_a_working_router_is_shown_as_external_data_and_does_not_move_a_score(providers, client, monkeypatch):
    transport, asked = serve([geocoder_answers, (200, {"code": "Ok", "routes": [{"distance": 118000.0, "duration": 4020.0}]})])
    providers.HTTP_TRANSPORT = transport
    monkeypatch.setenv("GEOCODING_PROVIDER", "nominatim")
    monkeypatch.setenv("ROUTING_PROVIDER", "osrm")

    run = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": "Fly ash from a 120 MW coal boiler, dry collection",
            "quantity": 20,
            "unit": "tonnes",
            "frequency": "monthly",
            "location": "Hosur, Tamil Nadu",
        },
    )
    assert run.status_code == 200, run.text
    body = run.json()
    analysis_id = body["analysis"]["id"]
    assert body["analysis"]["source"]["location"] == "Hosur, Tamil Nadu"
    assert body["analysis"]["source"]["latitude"] is not None

    top = body["matches"][0]
    straight_line = top["distance_km"]

    # The list of cards answers from cache at most; it must not start a routing call per
    # card, which is why the live call belongs to the detail page and nowhere else.
    cards = client.post("/api/matches", json={"analysis_id": analysis_id, "limit": 6}).json()
    routing_calls_before = len([url for url in asked if "/route/v1/" in url])
    assert cards["count"] == len(cards["matches"])

    detail = client.get(f"/api/matches/{analysis_id}/{top['recipient']['id']}").json()
    route = detail["route"]
    assert route is not None, detail
    assert route["distance_km"] == pytest.approx(118.0)
    assert route["duration_minutes"] == 67
    assert route["source"] == "external routing"
    assert route["fetched_at"].endswith("Z")
    assert route["straight_line_km"] == straight_line
    # The gap between the two is reported, never hidden: this stub route is deliberately
    # shorter than the straight line, and the figure says so.
    assert route["difference_percent"] == pytest.approx(round((118.0 - straight_line) / straight_line * 100, 1), abs=0.05)

    # The freight estimate and the score still come from the engine's own distance.
    assert detail["transport"]["distance_km"] == straight_line
    assert detail["transport"]["estimate"] is True
    assert detail["match"]["overall_score"] == top["overall_score"]
    assert len([url for url in asked if "/route/v1/" in url]) <= routing_calls_before + 1
    assert cards["count"] == len(cards["matches"])

    # Provenance says where the route came from, and the row exists only because a route
    # was actually fetched.
    rows = detail["provenance"]
    routing_rows = [row for row in rows if row["field"] == "Routing data"]
    assert len(routing_rows) == 1
    assert routing_rows[0]["origin"] == "external"
    assert "straight line" in routing_rows[0]["detail"]


def test_a_router_that_is_down_leaves_the_route_unavailable_and_says_so(providers, client, monkeypatch):
    transport, _ = serve([geocoder_answers, (500, "boom")])
    providers.HTTP_TRANSPORT = transport
    monkeypatch.setenv("GEOCODING_PROVIDER", "nominatim")
    monkeypatch.setenv("ROUTING_PROVIDER", "osrm")
    run = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": "Fly ash from a 120 MW coal boiler, dry collection",
            "quantity": 20,
            "unit": "tonnes",
            "frequency": "monthly",
            "location": "Hosur, Tamil Nadu",
        },
    )
    top = run.json()["matches"][0]
    analysis_id = run.json()["analysis"]["id"]
    detail = client.get(f"/api/matches/{analysis_id}/{top['recipient']['id']}").json()
    assert detail["route"] is None
    # The engine's own distance is still there, untouched: an outage removes an overlay,
    # it does not remove a number.
    assert detail["transport"]["distance_km"] == top["distance_km"]
    assert detail["transport"]["estimate"] is True, "the engine's own estimate survives a routing outage"
    assert "Traceback" not in str(detail)


def test_no_provider_means_the_route_key_is_absent_rather_than_empty(client, monkeypatch):
    monkeypatch.setenv("GEOCODING_PROVIDER", "off")
    monkeypatch.setenv("ROUTING_PROVIDER", "off")
    run = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": "Fly ash from a 120 MW coal boiler, dry collection",
            "quantity": 20,
            "unit": "tonnes",
            "frequency": "monthly",
            "location": "Manali, Chennai",
        },
    )
    top = run.json()["matches"][0]
    analysis_id = run.json()["analysis"]["id"]
    detail = client.get(f"/api/matches/{analysis_id}/{top['recipient']['id']}").json()
    assert detail["route"] is None
    assert [row["field"] for row in detail["provenance"]].count("Routing data") == 0


def test_a_keyed_routing_provider_without_its_key_is_reported_unconfigured_and_untouched(monkeypatch):
    from services import geo

    monkeypatch.setenv("ROUTING_PROVIDER", "ors")
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    monkeypatch.setenv("GEOCODING_PROVIDER", "off")
    geo.reset_for_tests()
    result = geo.route((12.9, 80.2), (13.1, 80.2))
    assert result.ok is False
    assert result.reason == "unconfigured"
    assert geo.status()["routing"]["provider"] == "unconfigured"
    geo.reset_for_tests()


# ---------------------------------------------------------------------------- the database


def test_a_database_that_is_configured_but_unreachable_is_named_and_the_demo_goes_on(client, monkeypatch):
    """The app was told where a database lives; it cannot be reached. Nothing is invented."""
    from db import engine as db_engine
    from db.config import DatabaseSettings

    unreachable = db_engine.Database(
        DatabaseSettings(mode="postgres", url="postgresql://symbio:secret@127.0.0.1:1/nosuchdb")
    )
    db_engine.replace(unreachable)
    monkeypatch.setenv("DATABASE_URL", "postgresql://symbio:secret@127.0.0.1:1/nosuchdb")
    try:
        status = client.get("/api/status").json()
        assert status["storage"]["configured"] is True
        assert status["storage"]["reachable"] is False
        assert "cannot reach" in status["storage"]["note"].lower()
        assert status["authentication"]["mode"] == "unavailable"
        # The seeded network is still there, and the page still works.
        assert status["data"]["seeded"]["recipients"] == 40

        run = client.post(
            "/api/analyze",
            json={
                "source_type": "industry",
                "material_description": "Fly ash from a 120 MW coal boiler, dry collection",
                "quantity": 20,
                "unit": "tonnes",
                "frequency": "monthly",
                "location": "Manali, Chennai",
            },
        )
        assert run.status_code == 200
        assert run.json()["saved"] is False
        assert run.json()["persistence"]["reachable"] is False

        health = client.get("/api/health").json()
        assert health["status"] == "degraded"
        assert "database" in json.dumps(health).lower()

        # And nowhere in any of that is the machine the database was supposed to be on.
        # A status route is public; "which internal host and port" is reconnaissance, not
        # an explanation of what a reader is looking at.
        for body in (json.dumps(status), json.dumps(health), run.text):
            assert "127.0.0.1" not in body
            assert "nosuchdb" not in body
            assert "secret" not in body
            assert "postgresql://" not in body
        assert status["storage"]["target"] == "PostgreSQL"
    finally:
        db_engine.replace(db_engine.Database(db_engine.config.DatabaseSettings(mode="off")))


def test_a_signed_in_request_is_refused_in_words_when_the_database_goes_away(temp_sqlite, client):
    from conftest import sign_up

    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    from db import engine as db_engine
    from db.config import DatabaseSettings

    broken = db_engine.Database(
        DatabaseSettings(mode="postgres", url="postgresql://symbio:secret@127.0.0.1:1/nosuchdb")
    )
    db_engine.replace(broken)
    client.app.state.database = broken
    try:
        response = client.get("/api/org")
        assert response.status_code in (401, 503)
        assert "Traceback" not in response.text
        assert "postgresql://" not in response.text
        assert "127.0.0.1" not in response.text
    finally:
        client.app.state.database = temp_sqlite
        db_engine.replace(temp_sqlite)


def test_a_signed_in_publish_that_cannot_be_saved_says_so_instead_of_claiming_success(monkeypatch):
    """A tenant's publish must not quietly become a session listing when the store is down.

    The actor is supplied directly, because the request that would normally carry one
    cannot be authenticated without the database either - and that is the right answer for
    the session, not for this test, which is about what the write does.
    """
    from services import persistence

    class Actor:
        organization_id = "org_aashirwad"
        user_id = "usr_anitha"
        organization = {"verification_status": "unverified"}

        def require(self, action):
            return True

    monkeypatch.setattr(persistence, "actor", lambda: Actor())
    from db import engine as db_engine
    from db.config import DatabaseSettings

    broken = db_engine.Database(
        DatabaseSettings(mode="postgres", url="postgresql://symbio:secret@127.0.0.1:1/nosuchdb")
    )
    original = db_engine.get()
    db_engine.replace(broken)
    try:
        with pytest.raises(persistence.PersistenceUnavailable) as raised:
            persistence.save_listing(
                {"kind": "supply", "material_ids": ["fly_ash"], "quantity_t_per_month": 20, "location": "Salem"}
            )
        assert "not saved" in str(raised.value)
        assert "Nothing was published" in str(raised.value)
        # The host, the port and the credentials stay inside the process.
        assert "127.0.0.1" not in str(raised.value) and "symbio:secret" not in str(raised.value)
    finally:
        db_engine.replace(original)


# ---------------------------------------------------------------------------- the AI layer


def test_a_local_model_that_is_not_running_leaves_the_identification_rule_based(client, monkeypatch):
    """Nothing here talks to Ollama; the point is that the answer stands without it."""
    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    response = client.post(
        "/api/analyze",
        json={
            "source_type": "industry",
            "material_description": "Some grey powder coming off our boiler, bags of it",
            "quantity": 4,
            "unit": "tonnes",
            "frequency": "monthly",
            "location": "Manali, Chennai",
        },
    )
    assert response.status_code == 200
    body = response.json()
    identification = body["analysis"]["identification"]
    # The name of the engine that answered is in the record, so a reader can tell a rule
    # match from a model's guess and the UI can label it.
    assert identification["engine"] == "fallback_keyword"
    assert identification["confidence"] <= 0.6
    assert body["warnings"], "an unidentified stream has to warn about being unidentified"
