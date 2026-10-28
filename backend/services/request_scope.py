"""Who is asking, for the code that has no `request` object.

`services/storage.py` is called from a dozen endpoints, and it has no idea who the
caller is. Rather than thread an actor through all of them - which is the kind of
change that quietly misses one - the authentication middleware puts the resolved actor
in a context variable for the duration of the request, and the storage layer reads it
back. Context variables are copied into each task by asyncio, so two concurrent
requests cannot see each other's actor.

Two things this is not:

* not a session store - `services/identity.py` owns that, and this only caches what it
  already decided for the current request;
* not a security boundary - every repository call still takes `organization_id`
  explicitly. This is how a *read path* finds the tenant, not how a write is authorised.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_current_actor: ContextVar[Any] = ContextVar("symbio_actor", default=None)
_current_request: ContextVar[dict[str, Any]] = ContextVar("symbio_request", default={})


def set_actor(actor: Any) -> Token:
    return _current_actor.set(actor)


def reset_actor(token: Token) -> None:
    _current_actor.reset(token)


def actor() -> Any:
    """The signed-in actor for this request, or None for a visitor."""
    return _current_actor.get()


def organization_id() -> str | None:
    actor_value = actor()
    return str(actor_value.organization_id) if actor_value is not None else None


def set_request_info(info: dict[str, Any]) -> Token:
    return _current_request.set(info)


def reset_request_info(token: Token) -> None:
    _current_request.reset(token)


def request_info() -> dict[str, Any]:
    """Client address and user agent, for rate limiting and audit lines only. Never
    returned to a caller."""
    return _current_request.get() or {}
