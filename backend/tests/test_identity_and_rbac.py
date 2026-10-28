"""Accounts, sessions and the three roles (§2, §3).

Every test here goes through the public routes - sign up with a password, get a cookie,
use it. Writing a session row directly would prove the schema is fine and nothing about
whether anybody can actually sign in, which is the part that has to work.
"""

from __future__ import annotations

import pytest

from conftest import TEST_PASSWORD, sign_up


def signup_body(**changes):
    base = {
        "email": "anitha@aashirwad.test",
        "password": TEST_PASSWORD,
        "display_name": "Anitha R",
        "organization_name": "Aashirwad Blocks",
        "sector": "building_materials",
    }
    return {**base, **changes}


# ---------------------------------------------------------------------------- sign up


def test_signup_sets_one_cookie_and_hands_no_token_to_the_page(temp_sqlite, client):
    response = client.post("/api/auth/signup", json=signup_body())
    assert response.status_code == 201, response.text

    cookie = response.headers.get("set-cookie", "").lower()
    assert "symbio_session=" in cookie
    assert "httponly" in cookie, "the app reads the session through the API, never from JavaScript"
    assert "samesite=lax" in cookie
    assert "path=/" in cookie

    body = response.json()
    assert TEST_PASSWORD not in response.text
    for leaked in ("token", "password", "hash", "session_id"):
        assert leaked not in body, f"{leaked} must not appear in a response body"

    session = body["session"]
    assert session["role"] == "organization_admin"
    assert session["role_label"] == "Administrator"
    assert session["organization"]["verification_status"] == "unverified"
    assert session["can_write"] is True
    assert session["can_manage_members"] is True
    assert body["persistence"]["mode"] == "sqlite"


def test_the_cookie_is_only_marked_secure_when_the_app_is_served_over_https(
    temp_sqlite, client, monkeypatch
):
    monkeypatch.delenv("APP_URL", raising=False)
    plain = client.post("/api/auth/signup", json=signup_body())
    assert "secure" not in plain.headers.get("set-cookie", "").lower()

    monkeypatch.setenv("APP_URL", "https://symbio.example")
    other = client.post("/api/auth/signup", json=signup_body(email="vikram@greenbrick.test"))
    assert other.status_code == 201, other.text
    assert "secure" in other.headers.get("set-cookie", "").lower()


def test_a_password_below_the_rule_is_refused_before_anything_is_written(temp_sqlite, client):
    # Nine characters is below the floor in `services/identity.py`. The request model's
    # own `min_length` is looser on purpose: the service holds the rule, so the sentence
    # a reader sees has to come from the service and not from a schema.
    response = client.post("/api/auth/signup", json=signup_body(password="123456789"))
    assert response.status_code == 422, response.text
    assert "at least 10 characters" in response.json()["detail"]
    assert client.get("/api/auth/me").json()["signed_in"] is False


def test_a_second_account_on_the_same_email_says_no_more_than_a_wrong_password_does(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    taken = client.post("/api/auth/signup", json=signup_body(organization_name="Second Attempt"))
    assert taken.status_code == 422, taken.text
    refused = client.post("/api/auth/login", json={"email": "anitha@aashirwad.test", "password": "not-the-password"})
    assert refused.status_code == 401
    # The sign-up answer is deliberately as vague as the sign-in answer: neither may
    # confirm that an address already has an account.
    assert "already" not in taken.json()["detail"].lower()
    assert "exist" not in taken.json()["detail"].lower()


def test_a_duplicate_email_still_leaves_the_first_account_working(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    assert client.post("/api/auth/signup", json=signup_body(organization_name="Second Attempt")).status_code == 422
    again = client.post("/api/auth/login", json={"email": "anitha@aashirwad.test", "password": TEST_PASSWORD})
    assert again.status_code == 200, again.text


# ---------------------------------------------------------------------------- the session


def test_being_signed_out_is_an_answer_and_not_an_error(client):
    body = client.get("/api/auth/me").json()
    assert body["signed_in"] is False
    assert "session" not in body
    assert body["persistence"]["mode"] == "off"


def test_sign_in_sign_out_and_in_again(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    assert client.get("/api/auth/me").json()["signed_in"] is True

    signed_out = client.post("/api/auth/logout")
    assert signed_out.status_code == 200
    assert signed_out.json()["session_revoked"] is True
    assert signed_out.json()["signed_in"] is False

    assert client.get("/api/auth/me").json()["signed_in"] is False
    assert client.get("/api/org").status_code == 401

    again = client.post("/api/auth/login", json={"email": "anitha@aashirwad.test", "password": TEST_PASSWORD})
    assert again.status_code == 200
    assert again.json()["session"]["organization"]["name"] == "Aashirwad Blocks"
    assert client.get("/api/org").status_code == 200


def test_a_stolen_cookie_is_useless_once_the_session_is_revoked(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    token = client.cookies.get("symbio_session")
    assert token
    client.post("/api/auth/logout")

    replayed = client.get("/api/auth/me", headers={"Cookie": f"symbio_session={token}"})
    assert replayed.json()["signed_in"] is False
    assert client.get("/api/org", headers={"Cookie": f"symbio_session={token}"}).status_code == 401


def test_forged_tokens_are_refused_without_a_500(temp_sqlite, client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    for forged in ("symbio_session=" + "0" * 32, "symbio_session=not-a-token", "session=1"):
        response = client.get("/api/org", headers={"Cookie": forged})
        assert response.status_code == 401, (forged, response.status_code)


def test_the_private_routes_refuse_anonymous_callers(client):
    calls = [
        ("get", "/api/org"),
        ("put", "/api/org/profile"),
        ("get", "/api/org/history"),
        ("get", "/api/org/members"),
        ("get", "/api/org/listings/mine"),
        ("patch", "/api/org/listings/lst_deadbeef"),
        ("post", "/api/org/listings/lst_deadbeef/status"),
        ("post", "/api/auth/organizations/select"),
    ]
    for method, path in calls:
        response = getattr(client, method)(path, json={}) if method != "get" else client.get(path)
        assert response.status_code == 401, (method, path, response.status_code)
        assert "Traceback" not in response.text


def test_organizations_are_switched_only_when_the_membership_says_so(temp_sqlite, client, second_client):
    sign_up(client, "anitha@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    sign_up(second_client, "vikram@greenbrick.test", "Vikram S", "GreenBrick Clay")
    other_org = second_client.get("/api/auth/me").json()["session"]["organization"]["id"]

    refused = client.post("/api/auth/organizations/select", json={"organization_id": other_org})
    assert refused.status_code == 200
    assert refused.json()["changed"] is False
    assert client.get("/api/org").json()["organization"]["name"] == "Aashirwad Blocks"

    # Making that person a member is the only thing that changes the answer.
    own = client.get("/api/org").json()
    assert own["organization"]["name"] == "Aashirwad Blocks"
    client.post("/api/org/members", json={"email": "vikram@greenbrick.test", "role": "operator"})
    switched = second_client.post("/api/auth/organizations/select", json={"organization_id": own["organization"]["id"]})
    assert switched.json()["changed"] is True
    assert switched.json()["session"]["organization"]["name"] == "Aashirwad Blocks"
    assert switched.json()["session"]["role"] == "operator"
    # ... and GreenBrick is still reachable, because both memberships are listed.
    listing = second_client.get("/api/auth/organizations").json()
    assert {row["name"] for row in listing["organizations"]} == {"Aashirwad Blocks", "GreenBrick Clay"}


# ---------------------------------------------------------------------------- the roles


def _add_member_with_role(admin_client, client_for_member, email, name, organization, role):
    """A second account, an invitation into the first organisation, and a switch to it.

    The switch is not decoration: signing up leaves the session pointing at the
    organisation that person created for themselves, and a test that forgot it would
    quietly check the wrong tenant's permissions.
    """
    sign_up(client_for_member, email, name, organization)
    added = admin_client.post("/api/org/members", json={"email": email, "role": role})
    assert added.status_code == 201, added.text
    org_id = admin_client.get("/api/org").json()["organization"]["id"]
    switched = client_for_member.post("/api/auth/organizations/select", json={"organization_id": org_id})
    assert switched.json()["changed"] is True
    return client_for_member


SUPPLY = {
    "kind": "supply",
    "material_ids": ["fly_ash"],
    "quantity_t_per_month": 20.0,
    "asking_price_inr_per_tonne": 900,
    "location": "Coimbatore, Tamil Nadu",
    "max_distance_km": 60,
    "frequency": "monthly",
}


@pytest.fixture
def staff(temp_sqlite, client, second_client, request):
    """Two signed-in clients: `client` is the administrator, `second_client` has `role`."""
    role = request.param
    sign_up(client, "admin@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    _add_member_with_role(client, second_client, "staff@aashirwad.test", "Field Staff", "Own Firm", role)
    return client, second_client


@pytest.mark.parametrize(
    "staff,expected",
    [
        ("viewer", {"/api/org/members": 403, "/api/org/profile": 403, "publish": 403}),
        ("operator", {"/api/org/members": 403, "/api/org/profile": 403, "publish": 201}),
        ("organization_admin", {"/api/org/members": 422, "/api/org/profile": 200, "publish": 201}),
    ],
    indirect=["staff"],
)
def test_a_role_decides_the_write_and_nobody_decides_the_read(staff, expected):
    admin, member = staff

    # An email that is already in the organisation: the administrator reaches the
    # repository and is told "already a member" (422), while the two lesser roles are
    # turned away at the door (403) without the repository being consulted at all.
    forbidden = member.post("/api/org/members", json={"email": "staff@aashirwad.test", "role": "viewer"})
    assert forbidden.status_code == expected["/api/org/members"], forbidden.text

    profile = member.put("/api/org/profile", json={"products_produced": ["Fly ash blocks"]})
    assert profile.status_code == expected["/api/org/profile"]

    published = member.post("/api/listings", json=SUPPLY)
    assert published.status_code == expected["publish"], published.text

    # Reading is scoped by tenant, not by role: all three see the same organisation.
    assert member.get("/api/org").status_code == 200
    assert member.get("/api/org/history").status_code == 200
    assert admin.get("/api/org").status_code == 200


def test_a_viewer_reading_the_organisation_is_told_why_they_cannot_change_it(temp_sqlite, client, second_client):
    sign_up(client, "admin@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    _add_member_with_role(client, second_client, "reader@aashirwad.test", "Auditor", "Own Firm", "viewer")

    refused = second_client.post("/api/listings", json=SUPPLY)
    assert refused.status_code == 403
    detail = refused.json()["detail"].lower()
    assert "viewer" in detail and "operator" in detail
    assert "traceback" not in detail and "http://" not in detail

    # and the administrator can publish the very same payload
    assert client.post("/api/listings", json=SUPPLY).status_code == 201


def test_the_only_administrator_cannot_be_removed(temp_sqlite, client):
    sign_up(client, "admin@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    me = client.get("/api/auth/me").json()["session"]["user"]
    refused = client.delete(f"/api/org/members/{me['id']}")
    assert refused.status_code == 422
    assert "only administrator" in refused.json()["detail"].lower()
    assert client.get("/api/org").status_code == 200


def test_an_invitation_for_somebody_with_no_account_is_explained(temp_sqlite, client):
    sign_up(client, "admin@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    response = client.post("/api/org/members", json={"email": "stranger@nowhere.test", "role": "operator"})
    assert response.status_code == 404
    assert "no symbio account" in response.json()["detail"].lower()
    assert "sign up" in response.json()["detail"].lower() or "yet" in response.json()["detail"].lower()


def test_the_permission_table_is_public_so_the_ui_cannot_invent_one(client):
    body = client.get("/api/org/permissions").json()
    assert set(body["roles"]) == {"organization_admin", "operator", "viewer"}
    table = {row["action"]: set(row["roles"]) for row in body["permissions"]}
    assert table["manage_members"] == {"organization_admin"}
    assert table["edit_listing"] == {"operator", "organization_admin"}
    assert "view_analyses" in table and len(table["view_analyses"]) == 3
    # No role can do any of these, from any screen.
    for guarded in ("verify_organization", "override_safety", "change_score"):
        assert guarded not in table


def test_an_account_cannot_promote_itself(temp_sqlite, client):
    sign_up(client, "admin@aashirwad.test", "Anitha R", "Aashirwad Blocks")
    for payload in (
        {"role": "superadmin"},
        {"verification_status": "verified"},
        {"is_admin": True},
        {"id": "org_someone_elses"},
    ):
        response = client.patch("/api/org", json=payload)
        assert response.status_code == 200, response.text  # extra fields are not fields
        assert response.json()["organization"]["verification"]["status"] == "unverified"
    assert client.get("/api/org").json()["organization"]["verification"]["status"] == "unverified"
