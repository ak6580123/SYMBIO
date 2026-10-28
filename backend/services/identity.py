"""Accounts, sessions and who is asking (§2, §3).

What this module is *not*: an identity platform. There is no password reset email, no
SSO, no token endpoint, no "remember me" variants - each of those is a product surface
Symbio would have to earn and secure properly. What it is: a real password hash, a real
server-side session, and a single place where "who is asking, and for which
organisation" gets answered, so every private endpoint asks that question instead of
assuming an answer.

Passwords. Argon2id via `argon2-cffi`, with the parameters that library's own defaults
carry. Nothing here accepts a plaintext password, stores one, logs one, or falls back to
a weaker hash when the library is missing: a missing dependency is a deployment error,
and an endpoint that quietly stopped hashing would be worse than one that refuses to
start.

Sessions. A random 256-bit token in an HttpOnly, SameSite=Lax cookie; the **SHA-256 of
that token** is what the database holds. Logout revokes the row rather than deleting it,
so "when did this end" stays answerable. If the database is unreachable, sign-in fails
with a service error - it does not hand out a session that nothing will honour later.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from db import repositories as repo
from db.engine import Database, DatabaseUnavailable
from services.rbac import ROLES, can

COOKIE_NAME = "symbio_session"
SESSION_TTL_DAYS = 14
MIN_PASSWORD_LENGTH = 10
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")

_hasher_cache: Any = None


class IdentityUnavailable(RuntimeError):
    """Authentication cannot run in this build or at this moment, in reader's words."""


def _hasher():
    """Argon2id, with the library's own parameters.

    One exception: `ARGON2_TEST_MODE=1` (set by the test suite) lowers the cost
    parameters, because a few hundred sign-ups at full cost is a minute of the suite
    spent on stretching a hash that is not what those tests are about. It is still a
    real Argon2id hash, verified by the same code, and the flag has no effect unless a
    caller sets it on purpose - a production start never reads it from a file.
    """
    global _hasher_cache
    if _hasher_cache is None:
        try:
            from argon2 import PasswordHasher  # noqa: PLC0415 - declared dependency, optional at import time

            if (os.environ.get("ARGON2_TEST_MODE") or "").strip() in ("1", "true", "on"):
                _hasher_cache = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
            else:
                _hasher_cache = PasswordHasher()
        except ImportError as exc:
            raise IdentityUnavailable(
                "Symbio's password hashing needs the argon2-cffi package. Install it with "
                "`pip install argon2-cffi`, or point the app at Supabase Auth instead - it will not "
                "store passwords some other way."
            ) from exc
    return _hasher_cache


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(digest: str, password: str) -> bool:
    try:
        _hasher().verify(digest, password)
    except Exception:  # argon2 raises a family of VerificationError subclasses
        return False
    return True


# ---------------------------------------------------------------------------
# validation that belongs to the service, not the form
# ---------------------------------------------------------------------------


def check_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(value):
        raise ValueError("Enter an email address we could actually reach you at.")
    return value


def check_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Use at least {MIN_PASSWORD_LENGTH} characters for a password.")
    if password.strip() != password or not password.strip():
        raise ValueError("A password cannot be only spaces or start and end with them.")
    if len(set(password)) < 4:
        raise ValueError("Use a few different characters - not one repeated.")
    return password


# ---------------------------------------------------------------------------
# the actor: a session, a person, one organisation, one role
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Actor:
    user: dict[str, Any]
    session: dict[str, Any]
    organization: dict[str, Any]
    role: str
    # Every tenant this account belongs to, for the switcher and for `/api/auth/me`.
    memberships: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def user_id(self) -> str:
        return str(self.user["id"])

    @property
    def organization_id(self) -> str:
        return str(self.organization["id"])

    @property
    def display(self) -> str:
        return str(self.user.get("display_name") or self.user.get("email") or "Signed in")

    def can(self, action: str) -> bool:
        return can(self.role, action)

    def require(self, action: str) -> None:
        if not self.can(action):
            raise PermissionError(
                f"A {ROLES[self.role]['label'].lower()} can read this organisation's data but cannot "
                f"{action.replace('_', ' ')}."
            )

    @property
    def role_label(self) -> str:
        """The role as it is written to a person. One place, so a refusal never has to
        print `organization_admin` at somebody who is only trying to publish a listing."""
        return ROLES[self.role]["label"]

    def public(self) -> dict[str, Any]:
        """What `/api/auth/me` may say. Never a hash, never a token, never an expiry the
        client has to reason about."""
        return {
            "signed_in": True,
            "user": {
                "id": self.user_id,
                "email": self.user.get("email"),
                "display_name": self.user.get("display_name") or "",
            },
            "organization": {
                "id": self.organization["id"],
                "name": self.organization["name"],
                "sector": self.organization.get("sector") or "",
                "verification_status": self.organization.get("verification_status") or "unverified",
                "verification_note": self.organization.get("verification_note") or "",
            },
            "role": self.role,
            "role_label": ROLES[self.role]["label"],
            "can_write": self.can("edit_listing"),
            "can_manage_members": self.can("manage_members"),
            "organizations": [
                {"id": row["id"], "name": row["name"], "role": row.get("role")} for row in self.memberships
            ],
            "session": {"expires_at": str(self.session.get("expires_at") or "")},
        }


def _database() -> Database:
    from db import get as get_db  # noqa: PLC0415 - keeps this module importable without a DB

    database = get_db()
    if not database.settings.configured:
        raise IdentityUnavailable(
            "Symbio has no database configured, so accounts cannot be created or checked. Set "
            "DATABASE_URL (or let the app use its local development file) and try again."
        )
    return database


def create_account(
    *,
    email: str,
    password: str,
    display_name: str = "",
    organization_name: str,
    sector: str = "",
    location: str = "",
) -> tuple[str, Actor]:
    """Sign up: one person, one organisation they administer, one live session.

    Both rows land in the same transaction, because an account with no tenant to
    belong to is a half-made thing that every later screen would have to explain.
    """
    db = _database()
    email = check_email(email)
    check_password(password)
    name = (organization_name or "").strip()
    if len(name) < 2:
        raise ValueError("Name the organisation - it is what the marketplace will show next to a listing.")
    if repo.get_user_by_email(db, email):
        # The same message as a wrong password: this endpoint must not tell a caller
        # which addresses already have accounts.
        raise ValueError("Those details do not match an account we can create. Try signing in instead.")

    digest = hash_password(password)
    with db.transaction():
        user = repo.create_user(db, email=email, password_hash=digest, display_name=display_name)
        organization = repo.create_organization(
            db, name=name, sector=sector.strip(), created_by_user_id=str(user["id"])
        )
        if location.strip():
            repo.save_profile(
                db,
                str(organization["id"]),
                {"sector": sector.strip(), "waste_streams": []},
                updated_by=str(user["id"]),
            )
            repo.create_facility(
                db,
                str(organization["id"]),
                {"name": "Primary site", "location": location.strip(), **_resolve_place(location)},
            )
    token, row = repo.create_session(db, user_id=str(user["id"]), ttl_days=SESSION_TTL_DAYS, client_label="signup")
    return token, build_actor(db, repo.get_user(db, str(user["id"])) or {}, row)


def sign_in(*, email: str, password: str) -> tuple[str, Actor]:
    db = _database()
    email = check_email(email)
    user = repo.get_user_by_email(db, email)
    failed = ValueError("We could not match that email address and password.")
    if not user or not user.get("is_active", True):
        # Hash anyway, on a fixed dummy digest, so a missing account and a wrong
        # password take about the same time and say the same thing.
        verify_password(_DUMMY_DIGEST, password or "")
        raise failed
    if not verify_password(str(user["password_hash"]), password or ""):
        repo.mark_login(db, str(user["id"]), success=False)
        raise failed
    repo.mark_login(db, str(user["id"]), success=True)
    token, row = repo.create_session(db, user_id=str(user["id"]), ttl_days=SESSION_TTL_DAYS, client_label="password")
    return token, build_actor(db, repo.get_user(db, str(user["id"])) or user, row)


# bcrypt/argon2 comparisons on a non-existent account still cost something
_DUMMY_DIGEST = "$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$3s0LM5C1ha2H1l1EMT0nC0RgYUq0Y1r1x1Q1k0nC1k0"


def sign_out(db: Database | None, token: str) -> int:
    if not token:
        return 0
    database = db or _database()
    try:
        return repo.revoke_session(database, token)
    except DatabaseUnavailable:
        # The cookie is dropped regardless; a session that cannot be revoked because
        # the database is down is not a session the next request will accept either.
        return 0


def actor_for_token(db: Database, token: str, organization_hint: str | None = None) -> Actor | None:
    session = repo.get_session(db, token)
    if not session:
        return None
    user = repo.get_user(db, str(session["user_id"]))
    if not user or not user.get("is_active", True):
        return None
    # Sliding expiry, at most once an hour: a session that is used stays alive, and a
    # page that polls the API every 15 seconds does not write a row every time.
    seen = str(session.get("last_seen_at") or "")
    if _older_than_hour(seen):
        repo.extend_session(db, str(session["id"]), ttl_days=SESSION_TTL_DAYS)
    return build_actor(db, user, session, organization_hint)


def build_actor(
    db: Database, user: dict[str, Any], session: dict[str, Any], organization_hint: str | None = None
) -> Actor | None:
    memberships = tuple(repo.organizations_for_user(db, str(user["id"])))
    if not memberships:
        return None
    chosen = memberships[0]
    if organization_hint:
        match = next((row for row in memberships if row["id"] == organization_hint), None)
        # A hint naming a tenant the person is not in is ignored rather than
        # trusted: the membership table is the only thing that decides scope.
        if match:
            chosen = match
    organization = repo.get_organization(db, str(chosen["id"])) or dict(chosen)
    return Actor(
        user=user,
        session=session,
        organization=organization,
        role=str(chosen.get("role") or "viewer"),
        memberships=memberships,
    )


def _older_than_hour(stamp: str) -> bool:
    if not stamp:
        return True
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() > 3600


def _resolve_place(location: str) -> dict[str, Any]:
    """Coordinates for a stated place, or none at all - the same rule `place_fields`
    implements for facilities and listings, so "where did this point come from" has one
    answer in the codebase rather than three."""
    from services.analysis import place_fields  # noqa: PLC0415 - avoids a cycle at import

    fields = place_fields(location)
    return {
        "latitude": fields["latitude"],
        "longitude": fields["longitude"],
        "location_resolved": fields["location_resolved"],
        "location_source": fields["location_source"],
    }


def token_from_request(request: Any) -> str:
    return request.cookies.get(COOKIE_NAME, "") if hasattr(request, "cookies") else ""


def new_token() -> str:
    return secrets.token_urlsafe(32)


def cookie_args(secure: bool = False) -> dict[str, Any]:
    """The attributes every auth response sets on the cookie, in one place."""
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
        "max_age": SESSION_TTL_DAYS * 86400,
    }


def digest_of(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
