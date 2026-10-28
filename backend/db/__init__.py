"""Symbio's persistence boundary.

    config        what the environment says, with no I/O
    engine        one connection, two engines, one error type
    migrate       the numbered files in database/migrations
    repositories  every SQL statement the application runs

Nothing outside this package writes SQL, and nothing inside it decides a score, a
distance, a safety gate or a verification state. Services hand finished records down;
repositories put them on disk and bring them back.
"""

from __future__ import annotations

from db.config import DatabaseSettings, resolve
from db.engine import Database, DatabaseUnavailable, get, replace, utcnow

__all__ = [
    "Database",
    "DatabaseSettings",
    "DatabaseUnavailable",
    "get",
    "resolve",
    "replace",
    "utcnow",
]
