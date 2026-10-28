"""Where Symbio's persistent data lives, and how it is configured (§1, §13).

Three kinds of data, deliberately kept apart:

* **Platform reference data** - the material knowledge base, the seeded partner
  network, the sector profiles. Ships as JSON under `backend/data/` and is *read
  only at runtime*. Nothing writes to it; that is what makes the seeded demo
  reproducible on any machine (§12).
* **Organization-owned persistent data** - accounts, profiles, listings,
  analyses. Lives in PostgreSQL (or Supabase, which is PostgreSQL) and is what
  this package exists to serve.
* **Session/runtime data** - an anonymous visitor's analysis, a what-if scenario.
  Lives in process memory, is lost on restart, and is never presented as saved.

Configuration is environment only, and no secret is ever required to run the app
locally:

    DATABASE_URL          postgres://user:pass@host:5432/db   (production, Supabase)
    SYMBIO_DB_MODE        auto | postgres | sqlite | off      (default: auto)
    SYMBIO_SQLITE_PATH    local development database file
                          (default: ~/.local/share/symbio/symbio.db)

`auto` means: use Postgres when `DATABASE_URL` is set, otherwise a local file so
development still persists across restarts, and if neither works the application
still runs on seeded data with persistence reported as unavailable. The mode is
reported to the reader in plain words by `describe()`; nothing here invents a
fallback silently.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Mode = Literal["postgres", "sqlite", "off"]

POSTGRES_SCHEMES = ("postgres://", "postgresql://", "postgres+psycopg2://")


@dataclass(frozen=True)
class DatabaseSettings:
    """Resolved, connection-free configuration. Safe to put in a status payload."""

    mode: Mode
    url: str | None = None
    sqlite_path: str | None = None
    note: str | None = None

    @property
    def configured(self) -> bool:
        return self.mode != "off"

    def target(self) -> str:
        """Where the data lives, in a form that is safe to show a developer."""
        if self.mode == "postgres":
            return _mask(self.url or "")
        if self.mode == "sqlite":
            return f"local file {self.sqlite_path}"
        return "not configured"

    def __repr__(self) -> str:
        """What lands in a log line if somebody logs the settings.

        The password is in the object - it has to be, it is how the connection is made -
        and this is the one place that decides whether an accidental `log.info(settings)`
        writes a credential into whoever's log aggregator.
        """
        return (
            f"{type(self).__name__}(mode={self.mode!r}, target={self.target()!r}, "
            f"sqlite_path={self.sqlite_path!r}, note={self.note!r})"
        )

    def public_target(self) -> str:
        """What an unauthenticated response may say about where the data lives.

        `target()` keeps the host, because it is written for a log line a developer reads.
        `/api/status` and `/api/health` are read by anybody, and which internal machine a
        database listens on is not something a browser needs in order to understand what it
        is looking at - it is also the kind of detail a reconnaissance pass hopes for.
        """
        if self.mode == "postgres":
            return "PostgreSQL"
        if self.mode == "sqlite":
            name = os.path.basename(self.sqlite_path or "")
            return f"local file ({name})" if name else "local file"
        return "not configured"

    def describe(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "configured": self.configured,
            "target": self.public_target(),
            **({"note": self.note} if self.note else {}),
        }


def _mask(url: str) -> str:
    """Strip a password from a connection string. Never return one to a caller."""
    if "@" not in url or "//" not in url:
        return url
    scheme, rest = url.split("//", 1)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}//{user}:***@{host}"


def _sqlite_path(values: dict[str, str]) -> str:
    return (values.get("SYMBIO_SQLITE_PATH") or "").strip() or _default_sqlite_path()


def _default_sqlite_path() -> str:
    base = os.environ.get("SYMBIO_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".local", "share", "symbio")
    return os.path.join(base, "symbio.db")


def resolve(env: dict[str, str] | None = None) -> DatabaseSettings:
    """Read the environment and decide where data should go. Performs no I/O."""
    values = dict(os.environ if env is None else env)
    url = (values.get("DATABASE_URL") or "").strip()
    requested = (values.get("SYMBIO_DB_MODE") or "auto").strip().lower()
    if requested not in ("auto", "postgres", "sqlite", "off"):
        requested = "auto"

    if requested == "off":
        return DatabaseSettings(mode="off")
    if requested == "sqlite":
        return DatabaseSettings(mode="sqlite", sqlite_path=_sqlite_path(values))
    if requested == "postgres":
        # Explicitly asked for and not given: report it as unconfigured rather than
        # quietly writing production-shaped data into a file nobody meant to use.
        if not url:
            return DatabaseSettings(mode="off")
        return DatabaseSettings(mode="postgres", url=url)

    if url.startswith(POSTGRES_SCHEMES):
        return DatabaseSettings(mode="postgres", url=url)
    if url:
        # A DATABASE_URL that is not Postgres is a misconfiguration, not a licence to
        # guess. The local file is used so development keeps working, and the fact is
        # reported rather than hidden.
        return DatabaseSettings(
            mode="sqlite",
            sqlite_path=_sqlite_path(values),
            note="DATABASE_URL is set but is not a postgresql:// URL - using the local development file instead",
        )
    return DatabaseSettings(mode="sqlite", sqlite_path=_sqlite_path(values))


def migrations_dir() -> str:
    """`database/migrations`, resolved from this file so the CWD never matters."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("SYMBIO_MIGRATIONS_DIR") or os.path.normpath(
        os.path.join(here, "..", "..", "database", "migrations")
    )
