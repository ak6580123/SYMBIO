"""The protection layer: request scope, headers, rate limiting, cookie hygiene (§11).

One middleware, four jobs, in this order:

1. **Scope.** Resolve the session cookie to an actor and put it on the request, so no
   endpoint has to parse cookies and no service has to be handed a `Request`.
2. **Rate limiting.** Fixed-window counters per client, tighter on authentication and
   writes than on reads. In-process by design: a second process gets its own counters,
   which is honest for a single-node deployment and insufficient for a fleet, and
   `README` says so rather than pretending otherwise.
3. **Cross-site request checks.** A state-changing request that arrives carrying a
   session cookie must be same-origin. That is what makes the cookie usable without a
   CSRF token, and it only applies where a cookie exists, so ordinary API clients are
   untouched.
4. **Response headers.** Anti-sniffing, frame denial, referrer and feature policy on
   every response, and `no-store` on API responses so a shared machine's cache does not
   hold someone's analysis.

Failures are turned into one clean sentence each. A stack trace never leaves the
process, and the log line that does carry one is keyed by a correlation id the response
names - so an operator can find it and a visitor cannot read it.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.types import ASGIApp

from db.engine import DatabaseUnavailable
from services import identity
from services import persistence

log = logging.getLogger("symbio.http")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SECURE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=(), usb=()",
}


def _flag(name: str, default: str = "on") -> bool:
    return (os.environ.get(name) or default).strip().lower() not in ("0", "off", "false", "no")


def _limit(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name) or default))
    except ValueError:
        return default


class RateWindow:
    """A sliding window of request timestamps per client, per class of route."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], Deque[float]] = defaultdict(deque)

    def allow(self, bucket: str, client: str, limit: int, window: float = 60.0) -> tuple[bool, float]:
        now = time.monotonic()
        events = self._events[(bucket, client)]
        while events and now - events[0] > window:
            events.popleft()
        if len(events) >= limit:
            retry = max(1.0, window - (now - events[0]))
            return False, retry
        events.append(now)
        return True, 0.0

    def reset(self) -> None:
        self._events.clear()


_windows = RateWindow()


def bucket_for(path: str, method: str) -> str:
    if path.startswith("/api/auth/"):
        return "auth"
    if method not in SAFE_METHODS:
        return "write"
    return "read"


def client_address(request: StarletteRequest) -> str:
    """The requester as far as this process can tell.

    `X-Forwarded-For` is honoured only when `TRUST_PROXY=1` says there is a proxy in
    front worth believing: trusting it by default would let any client pick the bucket
    it is rate-limited in.
    """
    if _flag("TRUST_PROXY", "off"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def enforce(request: StarletteRequest) -> JSONResponse | None:
    """Rate limit + cross-site check. Returns a response to send, or None to continue."""
    origin = request.headers.get("origin") or ""
    has_cookie = bool(request.cookies.get(identity.COOKIE_NAME))

    if (
        request.method not in SAFE_METHODS
        and has_cookie
        and not _same_site(request, origin)
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "That request did not come from this application, so it was not carried out.",
                "correlation": _correlation(request),
            },
        )

    if not _flag("SYMBIO_RATE_LIMIT", "on"):
        return None
    bucket = bucket_for(request.url.path, request.method)
    limits = {
        "auth": _limit("RATE_LIMIT_AUTH_PER_MINUTE", 10),
        "write": _limit("RATE_LIMIT_WRITE_PER_MINUTE", 60),
        "read": _limit("RATE_LIMIT_READ_PER_MINUTE", 600),
    }
    allowed, retry = _windows.allow(bucket, client_address(request), limits[bucket])
    if not allowed:
        log.info("rate limited %s for %s (%s/min)", bucket, client_address(request), limits[bucket])
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Symbio is receiving a lot of requests from here right now. Please wait a moment.",
                "retry_after_seconds": round(retry),
            },
            headers={"Retry-After": str(int(retry) + 1)},
        )
    return None


def _same_site(request: StarletteRequest, origin: str) -> bool:
    """Accept a browser request that is same-origin, or a non-browser client that
    sends no origin at all. Reject an origin that is not this host or `APP_URL`."""
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site in ("same-origin", "same-site", "none"):
        return True
    if not origin:
        return True
    allowed = {request.url.netloc.lower()}
    app_url = (os.environ.get("APP_URL") or "").strip()
    if app_url:
        allowed.add(_host_of(app_url))
    for extra in (os.environ.get("ALLOWED_ORIGINS") or "").split(","):
        if extra.strip():
            allowed.add(_host_of(extra.strip()))
    return _host_of(origin) in allowed


def _host_of(value: str) -> str:
    text = value.strip().lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0]


def _correlation(request: StarletteRequest) -> str:
    value = request.scope.get("symbio_correlation") or uuid.uuid4().hex[:8]
    request.scope["symbio_correlation"] = value
    return str(value)


class ProtectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request.scope["symbio_correlation"] = uuid.uuid4().hex[:8]

        blocked = enforce(request)
        if blocked is not None:
            for key, value in SECURE_HEADERS.items():
                blocked.headers.setdefault(key, value)
            return blocked

        token = identity.token_from_request(request)
        actor = None
        if token:
            actor = resolve_actor(request, token)
        request.scope["symbio_actor"] = actor

        from services import request_scope  # noqa: PLC0415 - per-request context

        scope_token = request_scope.set_actor(actor)
        info_token = request_scope.set_request_info(
            {
                "client": client_address(request),
                "agent": (request.headers.get("user-agent") or "")[:200],
                "correlation": request.scope["symbio_correlation"],
            }
        )
        try:
            response = await call_next(request)
        finally:
            request_scope.reset_actor(scope_token)
            request_scope.reset_request_info(info_token)

        for key, value in SECURE_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("X-Symbio-Correlation", str(request.scope["symbio_correlation"]))
        if _strict_transport():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


def _strict_transport() -> bool:
    return (os.environ.get("APP_URL") or "").strip().lower().startswith("https://")


def resolve_actor(request: Request, token: str) -> Any:
    """Cookie to actor. A database that is down is an unauthenticated request here:
    private endpoints then answer 401 with their own explanation, and nothing is
    served on the strength of a session nobody could verify."""
    try:
        db = request.app.state.database
        if not db.settings.configured:
            return None
        hint = None
        session = None
        from db import repositories as repo  # noqa: PLC0415

        session = repo.get_session(db, token)
        if session is not None:
            hint = session.get("active_organization_id")
        return identity.actor_for_token(db, token, hint)
    except Exception as exc:
        log.warning("session could not be verified: %s", exc.__class__.__name__)
        return None


def set_active_organization(db: Any, session_id: str, organization_id: str | None) -> None:
    db.execute(
        "update auth_sessions set active_organization_id = ? where id = ?",
        [organization_id, session_id],
    )


def install(app: FastAPI) -> None:
    """Add the middleware and the error translators. Called once from `main`."""

    app.add_middleware(ProtectionMiddleware)

    @app.exception_handler(identity.IdentityUnavailable)
    async def _identity_down(request: Request, exc: identity.IdentityUnavailable):  # noqa: ARG001
        return JSONResponse(status_code=503, content={"detail": str(exc), "service": "authentication"})

    @app.exception_handler(persistence.PersistenceUnavailable)
    async def _storage_down(request: Request, exc: persistence.PersistenceUnavailable):  # noqa: ARG001
        return JSONResponse(status_code=503, content={"detail": str(exc), "service": "storage"})

    @app.exception_handler(DatabaseUnavailable)
    async def _database_down(request: Request, exc: DatabaseUnavailable):  # noqa: ARG001
        """A connection that could not be made, said once, without the connection details.

        The exception's own message carries what the driver reported, and drivers like to
        quote the target they tried. That belongs in the log line this handler writes, and
        not in a response body.
        """
        logging.getLogger("symbio").warning("database unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Symbio's database is not answering, so nothing that belongs to an organisation can be read or "
                    "written right now. Analysis and the seeded network keep working."
                ),
                "service": "database",
            },
        )

    @app.exception_handler(LookupError)
    async def _not_found(request: Request, exc: LookupError):  # noqa: ARG001
        return JSONResponse(status_code=404, content={"detail": str(exc) or "Not found."})

    @app.exception_handler(PermissionError)
    async def _forbidden(request: Request, exc: PermissionError):  # noqa: ARG001
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _invalid(request: Request, exc: ValueError):  # noqa: ARG001
        # The services raise ValueError for "a reader asked for something we will not
        # do". It stays a 422 with their sentence, which is written for a person.
        return JSONResponse(status_code=422, content={"detail": str(exc) or "The request could not be accepted."})
