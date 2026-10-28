"""One connection, one dialect, two engines (Postgres and the local dev file).

Why a hand-written layer instead of an ORM: the application already has a storage
boundary (`services/storage.py`, `services/listings.py`) that speaks in plain
dictionaries, and every table here maps onto one of those dictionaries. An ORM would
add a second model of the same data, and the two would be the thing that drifts. What
this module guarantees is the short list that actually matters:

* the same SQL runs on PostgreSQL (production, Supabase) and on SQLite (a developer's
  laptop, and the test suite) - see `database/migrations/README.md` for the subset used;
* placeholders are written `?` everywhere and translated for Postgres;
* JSON payloads are encoded/decoded at this boundary, so repositories hold objects;
* a database that cannot be reached raises `DatabaseUnavailable`, which the API turns
  into one clear message. It never returns partial data and never pretends to be
  running on storage it does not have.

Concurrency: a single connection guarded by a lock. That is the right amount of
machinery for a modular monolith at this scale; a deployment that outgrows it swaps
`_connection()` for a pool and changes nothing else, because no other module touches
this class's internals.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence

from db import config

log = logging.getLogger("symbio.db")


class DatabaseUnavailable(RuntimeError):
    """Storage could not be reached or used. Callers surface this, they do not swallow it."""


def utcnow() -> str:
    """Timestamps are ISO-8601 UTC strings: the one format both engines store, sort and
    compare identically, and the format the API already returns."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _encode(value: Any) -> Any:
    """Only two conversions happen here, and both are about JSON.

    Booleans are passed through as themselves: SQLite binds a Python bool as 1/0 and
    PostgreSQL binds it as a real boolean, so a `boolean` column works on either. A
    hand-rolled `int(value)` would be the one way to break that.
    """
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class Database:
    """A lazily-opened connection over the resolved configuration."""

    def __init__(self, settings: config.DatabaseSettings | None = None) -> None:
        self.settings = settings or config.resolve()
        self.dialect = {"postgres": "postgres", "sqlite": "sqlite"}.get(self.settings.mode, "none")
        self._conn: Any = None
        self._lock = threading.RLock()
        self._error: str | None = None
        # Set while `transaction()` is open, so a read inside it does not end it.
        self._in_transaction = False
        self._next_savepoint = 1

    # ---------------------------------------------------------------- wiring

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def _connect(self) -> Any:
        if self._conn is not None:
            return self._conn
        if not self.settings.configured:
            raise DatabaseUnavailable("Symbio has no database configured for this run.")
        try:
            if self.settings.mode == "postgres":
                import psycopg  # noqa: PLC0415 - optional dependency, only needed for Postgres

                from psycopg.rows import dict_row  # noqa: PLC0415 - same optional dependency

                self._conn = psycopg.connect(
                    self.settings.url or "",
                    connect_timeout=5,
                    autocommit=False,
                    row_factory=dict_row,
                )
            else:
                path = self.settings.sqlite_path or ""
                parent = path.rsplit("/", 1)[0]
                if parent:
                    import os

                    os.makedirs(parent, exist_ok=True)
                self._conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False, isolation_level=None)
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA foreign_keys = ON")
                # WAL keeps a reader (the dashboard) from blocking a writer (a publish).
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA synchronous = FULL")
        except Exception as exc:  # driver errors vary by vendor; one type leaves this file
            self._conn = None
            self._error = exc.__class__.__name__
            log.warning("database unavailable (%s): %s", self.settings.mode, exc)
            raise DatabaseUnavailable("Symbio's database could not be reached for this request.") from exc
        return self._conn

    def _translate(self, sql: str) -> str:
        if self.dialect == "postgres":
            return sql.replace("?", "%s")
        return sql

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # a dead connection is exactly what close() is for
                    pass
                self._conn = None

    def ping(self) -> bool:
        try:
            with self._lock:
                self._run("select 1", ())
            self._error = None
            return True
        except DatabaseUnavailable:
            return False

    def status(self) -> dict[str, Any]:
        """Reported by `/api/status`. Says what is real, including when it is not."""
        payload: dict[str, Any] = {"database": self.settings.describe()}
        payload["database"]["reachable"] = bool(self.settings.configured) and self.ping()
        if self._error:
            payload["database"]["last_error"] = self._error
        return payload

    # ------------------------------------------------------------ statements

    def _run(self, sql: str, params: Sequence[Any]) -> Any:
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(self._translate(sql), tuple(_encode(p) for p in params))
        except Exception as exc:
            # Outside a transaction the statement is its own unit and unwinds on its own.
            # Inside one, unwinding here would discard everything the caller had already
            # written and leave the caller believing the unit was intact: `transaction()`
            # owns that decision.
            if not self._in_transaction:
                try:
                    conn.rollback()
                except Exception:
                    pass
            log.warning("query failed: %s | %s", sql.split("\n")[0][:80], exc.__class__.__name__)
            raise DatabaseUnavailable("Symbio could not read or write the record it was asked for.") from exc
        return cursor

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        conn = self._connect()
        cursor = self._run(sql, params)
        try:
            rows = cursor.fetchall()
        finally:
            cursor.close()
        if self.dialect == "postgres" and not self._in_transaction:
            conn.commit()  # do not hold an idle-in-transaction open after a read
        return [{key: _decode(row[key]) for key in row.keys()} for row in rows]

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Sequence[Any] = (), *, commit: bool = True) -> int:
        conn = self._connect()
        cursor = self._run(sql, params)
        try:
            count = cursor.rowcount
        finally:
            cursor.close()
        if commit and not self._in_transaction:
            # Committing inside an open transaction would end it: everything after that
            # statement would be permanent on its own, and the rollback the caller is
            # relying on would have nothing left to undo.
            conn.commit()
        return count

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Use for anything that must not half-happen: a listing and its material rows,
        an analysis and its matches, a counter and the row that consumed it."""
        conn = self._connect()
        with self._lock:
            if self._in_transaction:
                # Already inside one: join it through a savepoint, so an inner step that
                # fails unwinds to its own boundary while the outer call still decides
                # whether anything becomes permanent.
                name = f"symbio_sp_{self._next_savepoint}"
                self._next_savepoint += 1
                conn.execute(f"SAVEPOINT {name}")
                try:
                    yield
                except Exception:
                    conn.execute(f"ROLLBACK TO {name}")
                    conn.execute(f"RELEASE {name}")
                    raise
                conn.execute(f"RELEASE {name}")
                return
            self._in_transaction = True
            try:
                if self.dialect == "sqlite":
                    conn.execute("BEGIN IMMEDIATE")
                yield
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
            finally:
                self._in_transaction = False

    def insert(self, table: str, values: dict[str, Any]) -> None:
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        self.execute(f"insert into {table} ({columns}) values ({marks})", list(values.values()))

    def update(self, table: str, changes: dict[str, Any], where: str, params: Sequence[Any]) -> int:
        if not changes:
            return 0
        assignments = ", ".join(f"{column} = ?" for column in changes)
        sets = "updated_at = ?" if "updated_at" not in changes else ""
        clause = f"{assignments}, {sets}" if sets else assignments
        values = list(changes.values()) + ([utcnow()] if sets else [])
        return self.execute(f"update {table} set {clause} where {where}", values + list(params))


# -------------------------------------------------------------------------- shared


_shared: Database | None = None
_shared_lock = threading.Lock()


def get() -> Database:
    """The process-wide database. Constructing it is free; connecting is not."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = Database()
        return _shared


def replace(db: Database) -> None:
    """Tests and migrations point the application at another file or engine."""
    global _shared
    with _shared_lock:
        if _shared is not None:
            _shared.close()
        _shared = db


MIGRATION_NAME = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
