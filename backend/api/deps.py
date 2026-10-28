"""Dependencies the API routes share: who is asking, and whether storage is up.

Every private endpoint takes one of these. `require_actor` is what makes "sign in
first" a fact rather than a convention, and `require_permission` is what makes a
role's limits the same code path for every tenant.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from starlette.requests import Request as StarletteRequest

from db.engine import Database, DatabaseUnavailable


def actor_of(request: StarletteRequest) -> Any:
    """The signed-in actor for this request, or None. Set by the protection middleware."""
    return request.scope.get("symbio_actor")


def require_actor(request: StarletteRequest) -> Any:
    actor = actor_of(request)
    if actor is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "This is an organisation's own data, so it needs a signed-in account. Sign in or create one "
                "and try again."
            ),
        )
    return actor


def require_permission(action: str):
    def dependency(request: StarletteRequest) -> Any:
        actor = require_actor(request)
        try:
            actor.require(action)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return actor

    return dependency


def database_of(request: StarletteRequest) -> Database:
    return request.app.state.database


def require_database(request: StarletteRequest) -> Database:
    """For endpoints whose whole answer depends on storage being there.

    A clear service error, never an empty list dressed up as "you have nothing yet".
    """
    db = database_of(request)
    if not db.settings.configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "Symbio has no database configured for this run, so organisation data cannot be read or saved. "
                "Set DATABASE_URL, or let the app use its local development file."
            ),
        )
    try:
        if not db.ping():
            raise DatabaseUnavailable("unreachable")
    except DatabaseUnavailable:
        raise HTTPException(
            status_code=503,
            detail="Symbio's database is not answering right now. Nothing was changed - try again shortly.",
        ) from None
    return db


def scoped_organization(actor: Any) -> str:
    return str(actor.organization_id)


def public_or_none(payload: dict[str, Any]) -> dict[str, Any]:
    """Small guard used by the responses: no internal keys leave the API."""
    return {key: value for key, value in payload.items() if key not in {"token_hash", "password_hash", "failed_logins"}}


def as_dict(model: Any) -> dict[str, Any]:
    return model.model_dump(exclude_none=True)
