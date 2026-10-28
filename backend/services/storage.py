"""In-memory analysis store.

This is deliberately the ONLY place that knows how analyses are persisted.
Moving to Supabase later means re-implementing this module against a Postgres
client - the service layer and the API do not change.

For the MVP, analyses live in process memory and are lost on restart. That is
fine for a demo and avoids adding a database dependency to the install steps.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Any

MAX_ANALYSES = 200

_lock = Lock()
_analyses: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def save(analysis: dict[str, Any], owner: str | None = None) -> None:
    """Keep an analysis for later reads, and record whose it is.

    `owner` is an organisation id when someone was signed in, and None for the public
    demo data and for a visitor with no account. That distinction is what visibility is
    decided on below: without it, "we only persist what belongs to a tenant" would be
    true of the database and false of the process, and another visitor who happened to
    guess an id could read a private analysis for as long as the server stayed up.
    """
    with _lock:
        _analyses[analysis["id"]] = {"analysis": analysis, "owner": owner}
        _analyses.move_to_end(analysis["id"])
        while len(_analyses) > MAX_ANALYSES:
            _analyses.popitem(last=False)


def _visible(entry: dict[str, Any]) -> bool:
    """Is this row for the caller? Public rows always are; a tenant's rows are."""
    owner = entry.get("owner")
    if owner is None:
        return True
    from services import request_scope  # noqa: PLC0415 - optional, and per-request

    return str(owner) == (request_scope.organization_id() or "")


def get(analysis_id: str) -> dict[str, Any] | None:
    """One analysis by id: this process' copy first, then the tenant's saved record.

    The second half is what makes a history row openable after a restart, and it is
    scoped to whoever the request belongs to - an anonymous caller gets None, so a
    saved analysis cannot be read by guessing its id (§3, §6). The id lookup by
    reference (`SYM-2026-…`) is handled in the same place, so a reader can paste either.
    """
    with _lock:
        entry = _analyses.get(analysis_id)
    if entry is not None:
        # A row belonging to another tenant is not merely unreadable, it is not
        # acknowledged: the caller sees "no such analysis", exactly as if it had never
        # been run.
        return entry["analysis"] if _visible(entry) else None
    try:
        from services import persistence  # noqa: PLC0415 - the store must work with no database at all

        stored = persistence.stored_analysis(analysis_id)
    except Exception:
        return None
    if stored is None:
        return None
    with _lock:
        # Cached for the rest of the session so re-opening one page does not re-read
        # every card it already has. It is cached *with its owner*, so this shortcut
        # cannot turn a tenant's analysis into a public one.
        _analyses[stored["id"]] = {"analysis": stored, "owner": stored.get("organization_id")}
    return stored


def all_newest_first() -> list[dict[str, Any]]:
    """Everything the caller may see, newest first."""
    with _lock:
        entries = list(reversed(_analyses.values()))
    return [entry["analysis"] for entry in entries if _visible(entry)]


def owner_of(analysis_id: str) -> str | None:
    with _lock:
        entry = _analyses.get(analysis_id)
    return entry.get("owner") if entry else None


def count() -> int:
    with _lock:
        return len(_analyses)


def clear() -> None:
    with _lock:
        _analyses.clear()
