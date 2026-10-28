"""Migration runner (§1).

`database/migrations/*.sql` is the whole story: numbered files, applied in order,
each recorded in `schema_migrations` with a checksum. Applied files are never
re-run and never edited in place - if the checksum of an applied file changes, this
refuses to continue rather than letting a schema and its migrations disagree about
what the truth is.

Run it:

    python -m db.migrate status
    python -m db.migrate apply

or let the application do it at startup (the default; see `SYMBIO_MIGRATE_ON_START`).
Because the files stick to the portable subset, the same command works against
`psql`, against Supabase, and against a developer's local SQLite file.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from typing import Any

from db import config
from db.engine import Database, DatabaseUnavailable

TABLE = "schema_migrations"


def files() -> list[str]:
    directory = config.migrations_dir()
    if not os.path.isdir(directory):
        return []
    names = sorted(
        name for name in os.listdir(directory) if valid_name(name)
    )
    return [os.path.join(directory, name) for name in names]


def valid_name(name: str) -> bool:
    return bool(re.match(r"^\d{4}_[a-z0-9_]+\.sql$", name))


def strip_comments(line: str) -> str:
    """Remove a `--` comment from one line, without touching a `--` inside a string.

    This has to happen before splitting on semicolons: a comment is allowed to contain
    one ("as typed; null means nobody said"), and splitting first would cut a
    statement in half. Quoted text is skipped so a literal like '--' survives.
    """
    out: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            out.append(char)
        elif char == "-" and line[index : index + 2] == "--":
            break
        else:
            out.append(char)
        index += 1
    return "".join(out)


def read(path: str) -> tuple[str, list[str]]:
    """Return the file's checksum and its statements, comments stripped."""
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()
    lines = [strip_comments(line) for line in raw.splitlines()]
    statements = [part.strip() for part in "\n".join(lines).split(";")]
    return hashlib.sha256(raw.encode()).hexdigest()[:16], [s for s in statements if s]


def ensure_table(db: Database) -> None:
    db.execute(
        f"""create table if not exists {TABLE} (
                name        text primary key,
                checksum    text not null,
                applied_at  timestamptz not null default current_timestamp
            )"""
    )


def applied(db: Database) -> dict[str, str]:
    ensure_table(db)
    return {row["name"]: str(row["checksum"]) for row in db.query(f"select name, checksum from {TABLE}")}


def status(db: Database | None = None) -> dict[str, Any]:
    """What has run, what has not, and whether anything drifted."""
    db = db or Database()
    rows = applied(db)
    pending: list[str] = []
    drift: list[str] = []
    for path in files():
        name = os.path.basename(path)
        checksum, _ = read(path)
        if name not in rows:
            pending.append(name)
        elif rows[name] != checksum:
            drift.append(name)
    return {"applied": sorted(rows), "pending": pending, "checksum_drift": drift, "target": db.settings.target()}


def apply(db: Database | None = None) -> list[str]:
    """Apply every pending migration. Returns the names applied, in order."""
    db = db or Database()
    if not db.settings.configured:
        raise DatabaseUnavailable(
            "No database is configured, so there is nothing to migrate. Set DATABASE_URL, "
            "or let Symbio use its local development file."
        )
    rows = applied(db)
    done: list[str] = []
    for path in files():
        name = os.path.basename(path)
        checksum, statements = read(path)
        if name in rows:
            if rows[name] != checksum:
                raise DatabaseUnavailable(
                    f"{name} has changed since it was applied. Migrations are append-only: add a new "
                    "file for the change instead of editing one that has already run."
                )
            continue
        with db.transaction():
            for statement in statements:
                db.execute(statement, commit=False)
            db.execute(f"insert into {TABLE} (name, checksum) values (?, ?)", [name, checksum], commit=False)
        done.append(name)
    return done


def main(argv: list[str]) -> int:
    action = argv[1] if len(argv) > 1 else "apply"
    db = Database()
    try:
        if action == "status":
            report = status(db)
            for key in ("applied", "pending", "checksum_drift"):
                print(f"{key}: {', '.join(report[key]) if report[key] else 'none'}")
            print(f"target: {report['target']}")
            return 1 if report["checksum_drift"] else 0
        if action == "apply":
            names = apply(db)
            print(f"applied: {', '.join(names) if names else 'nothing - already up to date'}")
            print(f"target: {db.settings.target()}")
            return 0
        print(f"unknown action '{action}' (expected apply or status)")
        return 2
    except DatabaseUnavailable as exc:
        print(f"migration refused: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
