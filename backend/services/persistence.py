"""The application's side of the persistence boundary (§1, §10, §12).

`services/storage.py` and `services/listings.py` stay the only places their data is
kept; this file decides *whether* a record also belongs to a tenant on disk, and
composes the repository calls that make it so. The rules it enforces are worth stating
plainly:

**An analysis is shown even when it cannot be saved.** Running the pipeline needs no
database, and a judge on a laptop without one still gets a result. What changes is the
word: the response carries `saved: false` with the reason, and the history view is
empty rather than misleading.

**A listing is never silently lost.** Publishing is an action with a consequence, so a
database that will not take the row produces a 503 with a clear sentence - not a
success message and a listing that vanishes on restart.

**Nothing is written into the seeded files.** `backend/data/*.json` stays read-only at
runtime (§12); organisation rows live in the database, and a visitor's session data
stays in memory where it is honestly labelled.

The one decision a caller must never get wrong: `available()` means *this process is
talking to storage right now*. Everything else in the module is built on it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from db import migrate as migrate_module
from db import repositories as repo
from db.engine import Database, DatabaseUnavailable
from services import request_scope

log = logging.getLogger("symbio.persistence")

_startup_note: str = "not started"
_migrated: list[str] = []


class PersistenceUnavailable(RuntimeError):
    """The caller asked for something that has to be on disk, and it cannot be."""


def database() -> Database:
    from db import get as get_db  # noqa: PLC0415

    return get_db()


def available() -> bool:
    db = database()
    return bool(db.settings.configured) and db.ping()


def describe() -> dict[str, Any]:
    """For `/api/status`. Says what is real about storage right now."""
    db = database()
    try:
        applied = len(_migrated) if _migrated else len(migrate_module.status(db)["applied"])
    except Exception:
        # `describe()` answers a status request. A database that is configured and down
        # must produce a report saying so, not an exception on the way to one.
        applied = 0
    payload: dict[str, Any] = {
        "configured": db.settings.configured,
        "mode": db.settings.mode,
        "target": db.settings.public_target(),
        "reachable": False,
        "migrations_applied": applied if db.settings.configured else 0,
        "note": _startup_note,
    }
    if db.settings.note:
        payload["configuration_note"] = db.settings.note
    if db.settings.configured:
        payload["reachable"] = db.ping()
        if not payload["reachable"]:
            payload["note"] = (
                "Symbio is configured to store organisation data but cannot reach that database right now. "
                "Analysis and the seeded network keep working; nothing is written to an organisation until it "
                "answers."
            )
    else:
        payload["note"] = (
            "No database is configured, so organisation data is held in memory for this session only. "
            "Set DATABASE_URL, or let Symbio use its local development file."
        )
    return payload


def startup() -> dict[str, Any]:
    """Called from the application's startup hook. Never raises.

    Migrating on start is the default because a schema nobody applied is a worse
    surprise than a schema applied twice, and the migration files are idempotent by
    construction (`if not exists` plus the `schema_migrations` ledger).
    """
    global _startup_note
    import os

    db = database()
    _migrated.clear()  # what *this* start applied, not everything ever applied
    if not db.settings.configured:
        _startup_note = "running without a database: seeded network data only, session data in memory"
        return {"ok": True, "mode": "off", "applied": []}
    try:
        if (os.environ.get("SYMBIO_MIGRATE_ON_START") or "1").strip().lower() not in ("0", "false", "off"):
            applied = migrate_module.apply(db)
            _migrated.extend(applied)
            _startup_note = (
                f"applied {len(applied)} migration(s)" if applied else "schema up to date"
            )
        else:
            _startup_note = "migrations skipped (SYMBIO_MIGRATE_ON_START=off)"
        return {"ok": True, "mode": db.settings.mode, "applied": list(_migrated), "target": db.settings.target()}
    except DatabaseUnavailable as exc:
        _startup_note = str(exc)
        log.warning("database unavailable at startup: %s", exc)
        return {"ok": False, "mode": db.settings.mode, "applied": [], "error": str(exc)}


def actor() -> Any:
    return request_scope.actor()


# ---------------------------------------------------------------------------
# analyses
# ---------------------------------------------------------------------------


def persist_analysis(analysis: dict[str, Any], *, actor: Any = None) -> dict[str, Any] | None:
    """Save a completed analysis for the signed-in tenant.

    Best-effort on purpose, and honest about it: an analysis that ran but did not save
    is still an analysis the user can read, so the caller reports `saved: false` rather
    than failing. Returns the stored row, or None when there is no tenant, no storage,
    or the write was refused. The actor is passed in by the endpoint that resolved it,
    with the request scope as the fallback for callers that have no request.
    """
    current = actor if actor is not None else globals()["actor"]()
    if current is None or not available():
        return None
    try:
        return _write_analysis(current, analysis)
    except Exception as exc:  # a save failure must not lose the analysis
        log.warning("analysis could not be persisted: %s", exc.__class__.__name__)
        return None


def _safety_summary(analysis: dict[str, Any], matches: list[dict[str, Any]]) -> dict[str, Any]:
    """What the safety layer did to this run, read out of the record itself.

    The engine writes a verdict per match rather than one block for the whole analysis, so
    a stored analysis would otherwise carry an empty safety column and a history row could
    not say how many partners were gated. Nothing here is a new judgement: the levels are
    copied and counted, and the number of exclusions is the number the engine recorded.
    """
    levels: dict[str, int] = {}
    for row in matches:
        level = str(row.get("safety_level") or "unknown")
        levels[level] = levels.get(level, 0) + 1
    return {
        "levels": levels,
        "gated": len(analysis.get("excluded") or []),
        "source": "the safety layer's verdict on each match, counted",
    }


def _write_analysis(current: Any, analysis: dict[str, Any]) -> dict[str, Any]:
    db = database()
    source = analysis.get("source") or {}
    identification = analysis.get("identification") or {}
    matches = list(analysis.get("matches") or [])
    safety = analysis.get("safety") or _safety_summary(analysis, matches)
    top = matches[0] if matches else None
    year = datetime.now(timezone.utc).year
    record = {
        "id": analysis.get("id"),
        "reference": repo.next_reference(db, "analysis", str(year)),
        "organization_id": current.organization_id,
        "user_id": current.user_id,
        "source_type": source.get("source_type") or "industry",
        "raw_description": analysis.get("raw_description") or "",
        "composition_raw": analysis.get("composition_raw"),
        "attached_filename": analysis.get("attached_filename"),
        "quantity_t_per_month": source.get("quantity_t_per_month") or 0,
        "quantity_unit": source.get("unit") or "tonnes",
        "frequency": source.get("frequency") or "monthly",
        "location": source.get("location") or "",
        "latitude": source.get("latitude"),
        "longitude": source.get("longitude"),
        "location_resolved": bool(source.get("location_resolved")),
        "location_source": source.get("location_source") or "",
        "material_id": identification.get("material_id") or "unknown",
        "material_name": identification.get("material") or "Unidentified material",
        "identification_confidence": identification.get("confidence") or 0,
        "identification_engine": identification.get("engine") or "",
        "completeness_percent": (analysis.get("completeness") or {}).get("percent"),
        "completeness": analysis.get("completeness") or {},
        "safety": safety,
        "match_count": len(matches),
        "top_match_recipient_id": (top or {}).get("recipient", {}).get("id") if top else None,
        "top_match_name": (top or {}).get("recipient", {}).get("company_name", "") if top else "",
        "top_match_score": (top or {}).get("overall_score") if top else None,
        "payload": _slim(analysis),
        "created_at": _stamp(analysis.get("created_at")),
    }
    stored = repo.save_analysis(db, record, matches)
    return stored


def _slim(analysis: dict[str, Any]) -> dict[str, Any]:
    """Store what a page needs to reproduce the screen, not the process' whole memory.

    The ranked cards are already persisted as columns, so the payload carries the
    analysis without them: reopening a past analysis re-reads its match rows and hands
    back the same view.
    """
    payload = {key: value for key, value in analysis.items() if key not in ("matches",)}
    payload["matches"] = []
    return payload


def stored_analysis(analysis_id: str) -> dict[str, Any] | None:
    """The fallback the runtime store asks for when an id is not in memory (§6).

    Scoped to the caller's organisation, and to nothing else: an anonymous visitor gets
    None, which is why a private analysis from another tenant cannot be read by
    guessing its id.
    """
    current = actor()
    if current is None or not available():
        return None
    try:
        row = repo.get_analysis(database(), current.organization_id, analysis_id)
    except DatabaseUnavailable:
        return None
    if not row:
        return None
    payload = dict(row.get("payload") or {})
    payload["id"] = row["id"]
    payload["reference"] = row.get("reference")
    payload["organization_id"] = row.get("organization_id")
    payload["restored"] = True
    payload["created_at"] = str(row.get("created_at") or "")
    payload["matches"] = [_card_from_row(row_card) for row_card in row.get("matches") or []]
    totals = payload.get("totals") or {}
    totals.setdefault("potential_matches", len(payload["matches"]))
    payload["totals"] = totals
    return payload


def _card_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """A stored match row back into the shape the UI already renders.

    Nothing is recomputed here: the columns are what the engine decided at the time,
    which is the point of storing them individually (§6).
    """
    return {
        "id": row["id"],
        "analysis_id": str(row["id"]).split(":", 1)[0],
        "recipient": {"id": row["recipient_id"], "company_name": row.get("company_name") or ""},
        "overall_score": row.get("overall_score"),
        "breakdown": {
            "compatibility": row.get("score_compatibility"),
            "quantity": row.get("score_quantity"),
            "location": row.get("score_location"),
            "sector": row.get("score_sector"),
            "value": row.get("score_value"),
            "environmental": row.get("score_environmental"),
        },
        "reuse_type": row.get("reuse_type"),
        "safety_level": row.get("safety_level"),
        "distance_km": row.get("distance_km"),
        "matched_quantity_t_per_month": row.get("matched_quantity_t_month"),
        "allocated_t_per_month": row.get("allocated_t_month"),
        "estimated_value_inr_per_month": row.get("estimated_value_inr_month"),
        "estimated_co2e_t_per_month": row.get("estimated_co2e_t_month"),
        "reasons": row.get("reasons") or [],
        "cautions": row.get("cautions") or [],
        "pathway_steps": row.get("pathway_steps") or [],
        "transport": row.get("transport"),
        "restored": True,
    }


def counts() -> dict[str, Any]:
    """How much is actually on disk. Totals only - never ids, names or rows."""
    if not available():
        return {"analyses": 0, "listings": 0, "stored": False}
    db = database()
    try:
        return {
            "analyses": repo.count_all_analyses(db),
            "listings": repo.count_all_listings(db),
            "members": repo.count_all_members(db),
            "organizations": repo.count_all_organizations(db),
            "stored": True,
        }
    except Exception:
        return {"analyses": 0, "listings": 0, "stored": False}


def history(limit: int = 25) -> list[dict[str, Any]]:
    current = actor()
    if current is None or not available():
        return []
    try:
        rows = repo.list_analyses(database(), current.organization_id, limit=limit)
    except DatabaseUnavailable:
        return []
    return [
        {
            "id": row["id"],
            "reference": row.get("reference"),
            "material": row.get("material_name"),
            "quantity_t_per_month": row.get("quantity_t_per_month"),
            "quantity_unit": row.get("quantity_unit") or "tonnes",
            "location": row.get("location"),
            "location_resolved": bool(row.get("location_resolved")),
            "location_source": row.get("location_source") or "",
            "match_count": row.get("match_count"),
            "best_match": row.get("top_match_name") or "",
            "best_match_score": row.get("top_match_score"),
            "created_at": str(row.get("created_at") or ""),
            "created_on": _display_date(str(row.get("created_at") or "")),
        }
        for row in rows
    ]


def _display_date(stamp: str) -> str:
    if not stamp:
        return ""
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return stamp[:10]
    return moment.strftime("%-d %b %Y")


def _stamp(value: Any) -> str | None:
    """Store a timestamp as the ISO text both engines agree on."""
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value)
    return text


# ---------------------------------------------------------------------------
# listings
# ---------------------------------------------------------------------------


def save_listing(record: dict[str, Any]) -> dict[str, Any]:
    """Publish one listing for the signed-in tenant, or say why it cannot be done."""
    current = actor()
    if current is None:
        raise PersistenceUnavailable(
            "A listing that belongs to an organisation needs someone signed in to publish it."
        )
    if not available():
        raise PersistenceUnavailable(
            "Symbio could not reach its database, so this listing was not saved. Nothing was published."
        )
    current.require("publish_listing")
    payload = {
        "organization_id": current.organization_id,
        "created_by_user_id": current.user_id,
        "kind": record["kind"],
        "quantity_t_per_month": record["quantity_t_per_month"],
        "price_inr_per_tonne": record.get("offer_price_inr_per_tonne")
        or record.get("asking_price_inr_per_tonne")
        or 0,
        "max_distance_km": record.get("max_distance_km"),
        "frequency": record.get("frequency") or "monthly",
        # The publish form states it as a field of its own; `requirements` is where a
        # demand listing's application ends up in the response, so both are read.
        "application_use": record.get("application_use")
        or (record.get("requirements") or {}).get("application_use")
        or "",
        "location": record.get("location"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "location_resolved": bool(record.get("location_resolved", record.get("latitude") is not None)),
        "location_note": record.get("location_note") or "",
        "material_ids": record.get("material_ids") or [],
        "requirements": record.get("requirements") or {},
        "notes": record.get("notes") or "",
        "status": "active",
        # A listing's badge is the organisation's state at the moment of publication.
        # Sign-up always yields 'unverified', so a self-published row can never arrive
        # looking verified - and no user action writes this column.
        "verification_status": str(current.organization.get("verification_status") or "unverified"),
        "origin": "organization",
        "provenance": [
            {
                "field": field,
                "source": "organisation",
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for field in ("material_ids", "quantity_t_per_month", "location")
        ],
    }
    if record.get("id"):
        payload["id"] = record["id"]
    created = repo.create_listing(database(), payload)
    # Returned in the same shape the tenant's own list uses, so a page that published a
    # listing and a page that lists them read one shape, not two.
    return advertised(created, own=True)


def edit_listing(listing_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    current = actor()
    if current is None:
        raise PersistenceUnavailable("Sign in to change a listing.")
    if not available():
        raise PersistenceUnavailable("Symbio could not reach its database, so this listing was not changed.")
    current.require("edit_listing")
    scoped = {key: value for key, value in changes.items() if key != "organization_id"}
    repo.update_listing(database(), current.organization_id, listing_id, scoped)
    return repo.get_listing(database(), current.organization_id, listing_id)


def change_listing_status(listing_id: str, status: str) -> dict[str, Any] | None:
    current = actor()
    if current is None:
        raise PersistenceUnavailable("Sign in to change a listing.")
    if not available():
        raise PersistenceUnavailable("Symbio could not reach its database, so this listing was not changed.")
    current.require("deactivate_listing")
    repo.set_listing_status(database(), current.organization_id, listing_id, status)
    return repo.get_listing(database(), current.organization_id, listing_id)


def tenant_listings() -> list[dict[str, Any]]:
    """This organisation's own listings, whatever their status - the marketplace's
    "Yours" filter and nothing else may see the paused and closed ones."""
    current = actor()
    if current is None or not available():
        return []
    try:
        rows = repo.list_organization_listings(database(), current.organization_id)
    except DatabaseUnavailable:
        return []
    return [advertised(row, own=True) for row in rows]


def advertised_listings(*, kind: str | None = None, material_id: str | None = None) -> list[dict[str, Any]]:
    """What the marketplace shows from every organisation, including a visitor's view.

    Publishing is advertising, so these rows are for anybody: a visitor with no account
    sees the same offers a member of another organisation does. `advertised()` is what
    makes that safe - it hands over the offer and not the internal notes - and the person
    who published one gets their fuller row from `tenant_listings()` instead.
    """
    current = actor()
    if not available():
        return []
    try:
        rows = repo.list_public_listings(database(), kind=kind, material_id=material_id)
    except DatabaseUnavailable:
        return []
    own = str(current.organization_id) if current is not None else ""
    return [advertised(row, own=str(row.get("organization_id")) == own) for row in rows]


def advertised(row: dict[str, Any], *, own: bool = False) -> dict[str, Any]:
    """The marketplace's view of a persistent listing.

    Fields a tenant wrote for its own records - the requirements object, the
    provenance trail, who created the row - stay behind `own`. What everyone sees is
    what was offered, at what price, from where.
    """
    material_ids = list(row.get("material_ids") or [])
    from knowledge_base.materials import MATERIALS_BY_ID  # noqa: PLC0415

    out = {
        "id": row["id"],
        "kind": row["kind"],
        "party_id": None,
        "party_name": row.get("organization_name") or "An organisation on Symbio",
        "party_sector": row.get("organization_sector") or "",
        "location": row.get("location"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "material_ids": material_ids,
        "material_names": [MATERIALS_BY_ID.get(m, {}).get("name", m) for m in material_ids],
        "quantity_t_per_month": row.get("quantity_t_per_month"),
        "max_distance_km": row.get("max_distance_km"),
        "requirements": {},
        "notes": row.get("notes") or "",
        "status": "open" if row.get("status") == "active" else str(row.get("status") or "closed"),
        "lifecycle": row.get("status") or "active",
        "created_at": str(row.get("created_at") or "")[:10],
        "origin": "published by an organisation",
        "persisted": True,
        "location_resolved": bool(row.get("location_resolved")),
        "location_source": row.get("location_source") or "",
        "location_note": row.get("location_note") or "",
        "application_use": row.get("application_use") or "",
        "frequency": row.get("frequency") or "monthly",
        "organization": {
            "id": row.get("organization_id"),
            "name": row.get("organization_name") or "An organisation on Symbio",
            "verification_status": row.get("organization_verification_status") or "unverified",
        },
        "updated_at": str(row.get("updated_at") or ""),
    }
    if row["kind"] == "demand":
        out["offer_price_inr_per_tonne"] = row.get("price_inr_per_tonne")
    else:
        out["asking_price_inr_per_tonne"] = row.get("price_inr_per_tonne")
    if row.get("application_use"):
        out["requirements"] = {"application_use": row["application_use"]}
    if own:
        out["requirements"] = {**(row.get("requirements") or {}), **out.get("requirements", {})}
        out["provenance"] = row.get("provenance") or []
        out["verification_status"] = row.get("verification_status") or "unverified"
        out["created_by"] = row.get("created_by_user_id")
        out["facility_id"] = row.get("facility_id")
    return out
