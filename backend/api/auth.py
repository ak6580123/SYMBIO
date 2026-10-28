"""Sign up, sign in, sign out, who am I (§2).

Four endpoints, one cookie. The choices worth stating:

* The session token is returned only in the `Set-Cookie` header. No endpoint hands a
  token to a caller in a body, so nothing can accidentally log one into a browser
  store, a proxy access log or the assistant's chat history.
* Sign-up creates the person *and* the organisation they administer, because an
  account with no tenant would make every later screen explain a half-made state.
* Failures are one sentence, and the same sentence for "no such account" and "wrong
  password". This is not a serious defence against anything determined, but it is free.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.status import HTTP_201_CREATED

from api.deps import actor_of, require_actor
from api.security import set_active_organization
from db import repositories as repo
from models.schemas import LoginRequest, OrganizationSwitch, SignupRequest
from services import identity
from services import persistence

router = APIRouter(prefix="/api/auth", tags=["accounts"])


def _secure() -> bool:
    return (os.environ.get("APP_URL") or "").strip().lower().startswith("https://")


def _issue(response: Response, token: str) -> None:
    """Set the session cookie with the attributes from one place (`identity.cookie_args`).

    HttpOnly, because the application never reads it from JavaScript - the API answers
    with the same information. SameSite=Lax, because the cookie has to survive the
    redirect back from a link but must not ride along on another site's POST.
    """
    response.set_cookie(value=token, **identity.cookie_args(secure=_secure()))


def _clear(response: Response) -> None:
    response.delete_cookie(identity.COOKIE_NAME, path="/")


@router.post("/signup", status_code=HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, response: Response) -> dict[str, Any]:
    """Create an account and the organisation it administers, then sign straight in."""
    token, actor = identity.create_account(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name or "",
        organization_name=payload.organization_name,
        sector=payload.sector or "",
        location=payload.location or "",
    )
    _issue(response, token)
    return {
        "session": actor.public(),
        "persistence": persistence.describe(),
        "note": (
            "Your organisation is unverified. Symbio does not mark an organisation verified from inside the "
            "product - the state changes only when the platform team checks something."
        ),
        "demo_data": False,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    try:
        token, actor = identity.sign_in(email=payload.email, password=payload.password)
    except ValueError as exc:
        # 401, not the 422 a rejected *request* gets: nothing was wrong with the shape
        # of what was sent, the credentials simply do not match an account.
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _issue(response, token)
    return {"session": actor.public(), "persistence": persistence.describe(), "demo_data": False}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    token = identity.token_from_request(request)
    db = request.app.state.database
    revoked = identity.sign_out(db if db.settings.configured else None, token)
    _clear(response)
    return {
        "signed_in": False,
        "session_revoked": bool(revoked),
        "note": "Signed out. Private organisation data needs a new sign-in.",
    }


@router.get("/me")
def whoami(request: Request) -> dict[str, Any]:
    """What the app asks on load. Always a 200: 'not signed in' is an answer, not an error."""
    actor = actor_of(request)
    if actor is None:
        return {
            "signed_in": False,
            "persistence": persistence.describe(),
            "geography": _geography_summary(request),
        }
    return {
        "signed_in": True,
        "session": actor.public(),
        "persistence": persistence.describe(),
        "geography": _geography_summary(request),
    }


@router.get("/organizations")
def organizations(actor=Depends(require_actor)) -> dict[str, Any]:
    return {
        "organizations": [
            {"id": row["id"], "name": row["name"], "role": row.get("role"), "sector": row.get("sector") or ""}
            for row in actor.memberships
        ],
        "active": actor.organization_id,
    }


@router.post("/organizations/select")
def select_organization(payload: OrganizationSwitch, request: Request, actor=Depends(require_actor)) -> dict[str, Any]:
    """Point this session at another tenant the person really belongs to."""
    match = next((row for row in actor.memberships if row["id"] == payload.organization_id), None)
    if not match:
        # Not a 404 for someone else's organisation, and not a 200 that quietly
        # ignores the request: the membership table decides, and that is the whole rule.
        return {
            "session": actor.public(),
            "changed": False,
            "note": "You are not a member of that organisation, so this session still shows the one you are in.",
        }
    set_active_organization(request.app.state.database, str(actor.session["id"]), payload.organization_id)
    refreshed = identity.actor_for_token(request.app.state.database, identity.token_from_request(request), payload.organization_id)
    return {"session": (refreshed or actor).public(), "changed": True}


def _geography_summary(request: Request) -> dict[str, Any]:
    from services import geo  # noqa: PLC0415

    state = geo.status()
    return {
        "geocoding": state["geocoding"]["state"],
        "routing": state["routing"]["state"],
        "label": state["routing"]["label"],
    }
