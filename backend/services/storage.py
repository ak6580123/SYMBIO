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


def save(analysis: dict[str, Any]) -> None:
    with _lock:
        _analyses[analysis["id"]] = analysis
        _analyses.move_to_end(analysis["id"])
        while len(_analyses) > MAX_ANALYSES:
            _analyses.popitem(last=False)


def get(analysis_id: str) -> dict[str, Any] | None:
    with _lock:
        return _analyses.get(analysis_id)


def all_newest_first() -> list[dict[str, Any]]:
    with _lock:
        return list(reversed(_analyses.values()))


def count() -> int:
    with _lock:
        return len(_analyses)


def clear() -> None:
    with _lock:
        _analyses.clear()
