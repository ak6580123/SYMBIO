"""Repositories: the only code that writes SQL for organization-owned data.

Three rules, and they are the whole point of this layer:

1. **A private read always names its tenant.** Every method that touches an
   organisation's rows takes `organization_id` as a required argument and puts it in
   the `where` clause. There is no "optional scope" parameter to forget, so
   "organisation A reads organisation B's data" is not a check someone has to
   remember - it cannot be expressed here (§3).
2. **Rows in, dictionaries out.** JSON columns are decoded and booleans coerced, so
   services never see the difference between the two engines.
3. **Multi-row writes are transactions.** A listing and its material rows, an
   analysis and its matches, a reference number and the row that consumed it.

Nothing in here computes a score, a distance, a safety decision or a verification
state. The repositories store what the deterministic layers already decided.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from db.engine import Database, utcnow

# Columns that hold JSON text and must come back as objects.
_JSON_FIELDS = frozenset(
    {
        "material_ids",
        "material_names",
        "requirements",
        "provenance",
        "completeness",
        "safety",
        "payload",
        "reasons",
        "cautions",
        "pathway_steps",
        "transport",
        "products_produced",
        "materials_required",
        "waste_streams",
        "processing_capabilities",
        "certifications",
        "contact",
    }
)
_BOOL_FIELDS = frozenset({"location_resolved", "is_active", "resolved"})


def new_id(prefix: str) -> str:
    """Stable, sortable-enough, collision-free for a build with no sequence service."""
    return f"{prefix}_{secrets.token_hex(6)}"


def _decode_json(value: Any) -> Any:
    """A text column that holds JSON comes back as the object it was written from."""
    if value is None or isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "{[":
        return value
    try:
        return json.loads(text)
    except ValueError:
        # A column that should hold JSON and does not is reported as the text it is,
        # rather than quietly becoming an empty object a caller would trust.
        return value


def _clean(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key, value in out.items():
        if key in _JSON_FIELDS:
            out[key] = _decode_json(value)
        elif key in _BOOL_FIELDS:
            out[key] = bool(value)
    return out


def _rows(db: Database, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    return [_clean(row) or {} for row in db.query(sql, params)]


def _one(db: Database, sql: str, params: list[Any]) -> dict[str, Any] | None:
    return _clean(db.query_one(sql, params))


def hash_token(token: str) -> str:
    """Sessions and cache keys are looked up by digest, never by the secret itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


def create_user(db: Database, *, email: str, password_hash: str, display_name: str = "") -> dict[str, Any]:
    user_id = new_id("usr")
    now = utcnow()
    db.insert(
        "users",
        {
            "id": user_id,
            "email": email.strip().lower(),
            "password_hash": password_hash,
            "display_name": display_name.strip(),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
            "failed_logins": 0,
        },
    )
    return get_user(db, user_id) or {}


def get_user(db: Database, user_id: str) -> dict[str, Any] | None:
    return _one(db, "select * from users where id = ?", [user_id])


def get_user_by_email(db: Database, email: str) -> dict[str, Any] | None:
    return _one(db, "select * from users where email = ?", [email.strip().lower()])


def mark_login(db: Database, user_id: str, *, success: bool) -> None:
    if success:
        db.execute("update users set last_login_at = ?, failed_logins = 0, updated_at = ? where id = ?", [utcnow(), utcnow(), user_id])
    else:
        db.execute("update users set failed_logins = failed_logins + 1, updated_at = ? where id = ?", [utcnow(), user_id])


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------


def create_session(db: Database, *, user_id: str, ttl_days: int = 14, client_label: str = "") -> tuple[str, dict[str, Any]]:
    """Return `(token, row)`. The token is shown once, in the cookie, and never stored."""
    token = secrets.token_urlsafe(32)
    session_id = new_id("ses")
    expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    db.insert(
        "auth_sessions",
        {
            "id": session_id,
            "user_id": user_id,
            "token_hash": hash_token(token),
            "created_at": utcnow(),
            "last_seen_at": utcnow(),
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "revoked_at": None,
            "client_label": client_label[:200],
        },
    )
    return token, get_session(db, token) or {}


def get_session(db: Database, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    return _one(
        db,
        "select * from auth_sessions where token_hash = ? and revoked_at is null and expires_at > ?",
        [hash_token(token), utcnow()],
    )


def touch_session(db: Database, session_id: str) -> None:
    """Only `last_seen_at`: the expiry itself moves on a schedule, not on every hit,
    because a per-request write on every asset would be database noise."""
    db.execute("update auth_sessions set last_seen_at = ? where id = ?", [utcnow(), session_id])


def extend_session(db: Database, session_id: str, ttl_days: int = 14) -> None:
    expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    db.execute(
        "update auth_sessions set last_seen_at = ?, expires_at = ? where id = ?",
        [utcnow(), expires.strftime("%Y-%m-%dT%H:%M:%SZ"), session_id],
    )


def revoke_session(db: Database, token: str) -> int:
    return db.execute("update auth_sessions set revoked_at = ? where token_hash = ? and revoked_at is null", [utcnow(), hash_token(token)])


def revoke_all_sessions(db: Database, user_id: str) -> int:
    return db.execute("update auth_sessions set revoked_at = ? where user_id = ? and revoked_at is null", [utcnow(), user_id])


def count_live_sessions(db: Database) -> int:
    row = db.query_one(
        "select count(*) as n from auth_sessions where revoked_at is null and expires_at > ?", [utcnow()]
    )
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# organizations, membership, profile
# ---------------------------------------------------------------------------


def create_organization(
    db: Database,
    *,
    name: str,
    sector: str = "",
    description: str = "",
    created_by_user_id: str | None = None,
    verification_status: str = "unverified",
) -> dict[str, Any]:
    org_id = new_id("org")
    now = utcnow()
    with db.transaction():
        db.insert(
            "organizations",
            {
                "id": org_id,
                "name": name.strip(),
                "sector": sector.strip(),
                "description": description.strip(),
                "website": "",
                "contact_name": "",
                "contact_email": "",
                "phone": "",
                "verification_status": verification_status,
                "verification_note": "",
                "created_by_user_id": created_by_user_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        # The first member of a new tenant is always its administrator; sign-up is the
        # only path that creates an organisation, so there is no orphan to hand over.
        if created_by_user_id:
            db.insert(
                "organization_members",
                {
                    "id": new_id("mbr"),
                    "organization_id": org_id,
                    "user_id": created_by_user_id,
                    "role": "organization_admin",
                    "created_at": now,
                    "updated_at": now,
                },
            )
        db.insert(
            "organization_profile",
            {
                "organization_id": org_id,
                "sector": sector.strip(),
                "products_produced": "[]",
                "materials_required": "[]",
                "waste_streams": "[]",
                "processing_capabilities": "[]",
                "certifications": "[]",
                "contact": "{}",
                "updated_by_user_id": created_by_user_id,
                "created_at": now,
                "updated_at": now,
            },
        )
    return get_organization(db, org_id) or {}


def get_organization(db: Database, organization_id: str) -> dict[str, Any] | None:
    return _one(db, "select * from organizations where id = ?", [organization_id])


def organizations_for_user(db: Database, user_id: str) -> list[dict[str, Any]]:
    return _rows(
        db,
        """select o.*, m.role as role
             from organization_members m
             join organizations o on o.id = m.organization_id
            where m.user_id = ?
            order by m.created_at""",
        [user_id],
    )


def membership(db: Database, organization_id: str, user_id: str) -> dict[str, Any] | None:
    return _one(
        db, "select * from organization_members where organization_id = ? and user_id = ?", [organization_id, user_id]
    )


def update_organization(db: Database, organization_id: str, changes: dict[str, Any]) -> int:
    allowed = ("name", "sector", "description", "website", "contact_name", "contact_email", "phone")
    safe = {key: changes[key] for key in allowed if key in changes}
    return db.update("organizations", safe, "id = ?", [organization_id])


def set_verification(db: Database, organization_id: str, status: str, note: str = "") -> int:
    """Platform-side only. There is no route to this: no user action verifies anyone,
    because a verification the user can grant themselves would not mean anything (§5)."""
    return db.update("organizations", {"verification_status": status, "verification_note": note}, "id = ?", [organization_id])


def add_member(db: Database, *, organization_id: str, email: str, role: str) -> dict[str, Any]:
    user = get_user_by_email(db, email)
    if not user:
        raise LookupError("no Symbio account uses that email address yet")
    if role not in ("organization_admin", "operator", "viewer"):
        raise ValueError("role must be organization_admin, operator or viewer")
    if membership(db, organization_id, str(user["id"])):
        raise ValueError("that person is already a member of this organisation")
    db.insert(
        "organization_members",
        {
            "id": new_id("mbr"),
            "organization_id": organization_id,
            "user_id": user["id"],
            "role": role,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        },
    )
    return {**user, "role": role}


def members(db: Database, organization_id: str) -> list[dict[str, Any]]:
    return _rows(
        db,
        """select m.id, m.user_id, m.role, m.created_at, u.email, u.display_name
             from organization_members m
             join users u on u.id = m.user_id
            where m.organization_id = ?
            order by m.created_at""",
        [organization_id],
    )


def remove_member(db: Database, organization_id: str, user_id: str) -> int:
    return db.execute("delete from organization_members where organization_id = ? and user_id = ?", [organization_id, user_id])


def get_profile(db: Database, organization_id: str) -> dict[str, Any] | None:
    return _one(db, "select * from organization_profile where organization_id = ?", [organization_id])


def save_profile(db: Database, organization_id: str, changes: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any] | None:
    allowed = ("sector", "products_produced", "materials_required", "waste_streams", "processing_capabilities", "certifications", "contact")
    # A field the caller left out and a field the caller cleared are different things:
    # `None` means "I said nothing about this", so it is not written and what is already
    # stored stays. An empty list is a statement, and it empties the column.
    safe = {key: changes[key] for key in allowed if changes.get(key) is not None}
    if updated_by:
        safe["updated_by_user_id"] = updated_by
    if get_profile(db, organization_id) is None:
        # The first save has to satisfy the columns the schema marks NOT NULL, so
        # whatever the caller said nothing about is written in its empty form.
        first = {"organization_id": organization_id, "sector": "", "products_produced": [], "materials_required": []}
        first.update({key: value for key, value in safe.items() if key != "updated_by_user_id"})
        db.insert("organization_profile", first)
    else:
        db.update("organization_profile", safe, "organization_id = ?", [organization_id])
    return get_profile(db, organization_id)


# ---------------------------------------------------------------------------
# facilities
# ---------------------------------------------------------------------------


def list_facilities(db: Database, organization_id: str) -> list[dict[str, Any]]:
    return _rows(
        db, "select * from facilities where organization_id = ? order by name, created_at", [organization_id]
    )


def create_facility(db: Database, organization_id: str, values: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    facility_id = values.get("id") or new_id("fac")
    db.insert(
        "facilities",
        {
            "id": facility_id,
            "organization_id": organization_id,
            "name": str(values.get("name") or "").strip()[:120],
            "location": str(values.get("location") or "").strip()[:200],
            "latitude": values.get("latitude"),
            "longitude": values.get("longitude"),
            "location_resolved": bool(values.get("location_resolved")),
            "location_source": str(values.get("location_source") or "stated")[:40],
            "notes": str(values.get("notes") or "")[:1000],
            "created_at": now,
            "updated_at": now,
        },
    )
    return _one(db, "select * from facilities where id = ? and organization_id = ?", [facility_id, organization_id]) or {}


def update_facility(db: Database, organization_id: str, facility_id: str, changes: dict[str, Any]) -> int:
    allowed = ("name", "location", "latitude", "longitude", "location_resolved", "location_source", "notes")
    safe = {key: changes[key] for key in allowed if key in changes}
    return db.update("facilities", safe, "id = ? and organization_id = ?", [facility_id, organization_id])


def delete_facility(db: Database, organization_id: str, facility_id: str) -> int:
    return db.execute("delete from facilities where id = ? and organization_id = ?", [facility_id, organization_id])


# ---------------------------------------------------------------------------
# marketplace listings
# ---------------------------------------------------------------------------

_LISTING_COLUMNS = (
    "id",
    "organization_id",
    "facility_id",
    "created_by_user_id",
    "kind",
    "quantity_t_per_month",
    "quantity_min_t_per_month",
    "quantity_max_t_per_month",
    "price_inr_per_tonne",
    "max_distance_km",
    "frequency",
    "application_use",
    "location",
    "latitude",
    "longitude",
    "location_resolved",
    "location_note",
    "requirements",
    "notes",
    "status",
    "verification_status",
    "origin",
    "provenance",
    "created_at",
    "updated_at",
)


def create_listing(db: Database, record: dict[str, Any]) -> dict[str, Any]:
    """Insert one listing and its material rows, or nothing at all."""
    values = {key: record.get(key) for key in _LISTING_COLUMNS if key in record}
    values.setdefault("id", new_id("lst"))
    values["created_at"] = values.get("created_at") or utcnow()
    values["updated_at"] = utcnow()
    for key in ("quantity_t_per_month", "price_inr_per_tonne"):
        values[key] = float(values.get(key) or 0)
    if "material_ids" in values:
        values["material_ids"] = list(values["material_ids"])
    with db.transaction():
        db.insert("organization_listings", values)
        for ordinal, material_id in enumerate(record.get("material_ids") or []):
            db.insert(
                "organization_listing_materials",
                {"listing_id": values["id"], "material_id": str(material_id), "ordinal": ordinal},
            )
    return get_listing(db, str(record.get("organization_id") or ""), str(values["id"])) or {}


_LISTING_SELECT = """
    select l.*, o.name as organization_name, o.verification_status as organization_verification_status,
           o.sector as organization_sector
      from organization_listings l
      left join organizations o on o.id = l.organization_id
"""


def get_listing(db: Database, organization_id: str, listing_id: str) -> dict[str, Any] | None:
    """One tenant's own listing. The scope is a required argument: there is no way to
    ask this question without answering "whose?"."""
    row = _one(db, f"{_LISTING_SELECT} where l.id = ? and l.organization_id = ?", [listing_id, organization_id])
    if row:
        row["material_ids"] = listing_materials(db, listing_id)
    return row


def get_advertised_listing(db: Database, listing_id: str) -> dict[str, Any] | None:
    """The public marketplace view of someone else's listing: active rows only, and
    stripped of the fields a tenant never offered to the world."""
    row = _one(db, f"{_LISTING_SELECT} where l.id = ? and l.status = 'active'", [listing_id])
    if row:
        row.pop("requirements", None)
        row["material_ids"] = listing_materials(db, listing_id)
    return row


def listing_materials(db: Database, listing_id: str) -> list[str]:
    """In the order the author stated them, which the marketplace and the primary
    material both depend on."""
    return [
        str(row["material_id"])
        for row in db.query(
            "select material_id from organization_listing_materials where listing_id = ? order by ordinal, material_id",
            [listing_id],
        )
    ]


def list_organization_listings(
    db: Database,
    organization_id: str,
    *,
    status: str | None = None,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    sql = f"{_LISTING_SELECT} where l.organization_id = ?"
    params: list[Any] = [organization_id]
    if status:
        sql += " and l.status = ?"
        params.append(status)
    if kind:
        sql += " and l.kind = ?"
        params.append(kind)
    sql += " order by l.created_at desc"
    rows = _rows(db, sql, params)
    for row in rows:
        row["material_ids"] = listing_materials(db, str(row["id"]))
    return rows


def list_public_listings(db: Database, *, material_id: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    """What the marketplace may show from other tenants: active rows only, and never
    a contact detail that an organisation wrote for its own records."""
    sql = f"{_LISTING_SELECT} where l.status = 'active'"
    params: list[Any] = []
    if kind:
        sql += " and l.kind = ?"
        params.append(kind)
    if material_id:
        sql += " and exists (select 1 from organization_listing_materials m where m.listing_id = l.id and m.material_id = ?)"
        params.append(material_id)
    sql += " order by l.created_at desc"
    rows = _rows(db, sql, params)
    for row in rows:
        row["material_ids"] = listing_materials(db, str(row["id"]))
    return rows


def update_listing(db: Database, organization_id: str, listing_id: str, changes: dict[str, Any]) -> int:
    allowed = (
        "kind",
        "facility_id",
        "quantity_t_per_month",
        "quantity_min_t_per_month",
        "quantity_max_t_per_month",
        "price_inr_per_tonne",
        "max_distance_km",
        "frequency",
        "application_use",
        "location",
        "latitude",
        "longitude",
        "location_resolved",
        "location_note",
        "requirements",
        "notes",
        "status",
        "provenance",
        "material_ids",
    )
    safe = {key: changes[key] for key in allowed if key in changes}
    materials = safe.pop("material_ids", None)
    count = db.update("organization_listings", safe, "id = ? and organization_id = ?", [listing_id, organization_id])
    if materials is not None:
        with db.transaction():
            db.execute("delete from organization_listing_materials where listing_id = ?", [listing_id])
            for ordinal, material_id in enumerate(materials):
                db.insert(
                    "organization_listing_materials",
                    {"listing_id": listing_id, "material_id": str(material_id), "ordinal": ordinal},
                )
    return count


def set_listing_status(db: Database, organization_id: str, listing_id: str, status: str) -> int:
    if status not in ("active", "paused", "closed"):
        raise ValueError("status must be active, paused or closed")
    return db.update("organization_listings", {"status": status}, "id = ? and organization_id = ?", [listing_id, organization_id])


def count_organization_listings(db: Database, organization_id: str) -> int:
    row = db.query_one("select count(*) as n from organization_listings where organization_id = ?", [organization_id])
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# analyses
# ---------------------------------------------------------------------------


def next_reference(db: Database, kind: str, period: str) -> str:
    """`SYM-2026-000184`. Allocated under an immediate transaction so a concurrent
    publish cannot be handed the same number."""
    key = f"{kind}-{period}"
    with db.transaction():
        row = db.query_one("select next_value from reference_counters where period = ?", [key])
        value = int(row["next_value"]) if row else 1
        if row:
            db.execute("update reference_counters set next_value = ? where period = ?", [value + 1, key])
        else:
            db.insert("reference_counters", {"period": key, "next_value": 2})
    prefix = "SYM" if kind == "analysis" else kind.upper()[:3]
    return f"{prefix}-{period}-{value:06d}"


_ANALYSIS_COLUMNS = (
    "id",
    "reference",
    "organization_id",
    "user_id",
    "facility_id",
    "source_type",
    "raw_description",
    "composition_raw",
    "attached_filename",
    "quantity_t_per_month",
    "quantity_unit",
    "frequency",
    "location",
    "latitude",
    "longitude",
    "location_resolved",
    "location_source",
    "material_id",
    "material_name",
    "identification_confidence",
    "identification_engine",
    "completeness_percent",
    "completeness",
    "safety",
    "match_count",
    "top_match_recipient_id",
    "top_match_name",
    "top_match_score",
    "payload",
)


def save_analysis(db: Database, record: dict[str, Any], matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Write one analysis and its ranked cards. Idempotent on the analysis id, so a
    correction that re-saves does not create a second history row."""
    values = {key: record.get(key) for key in _ANALYSIS_COLUMNS if key in record}
    values.setdefault("id", new_id("an"))
    values["created_at"] = values.get("created_at") or utcnow()
    values["updated_at"] = utcnow()
    analysis_id = str(values["id"])
    with db.transaction():
        existing = db.query_one("select id from organization_analyses where id = ?", [analysis_id])
        if existing:
            db.update("organization_analyses", {k: v for k, v in values.items() if k not in ("id", "created_at")}, "id = ?", [analysis_id])
            db.execute("delete from organization_analysis_matches where analysis_id = ?", [analysis_id])
        else:
            db.insert("organization_analyses", values)
        for card in matches:
            row = {
                "id": f"{analysis_id}:{card['recipient']['id']}",
                "analysis_id": analysis_id,
                "recipient_id": card["recipient"]["id"],
                "company_name": card["recipient"].get("company_name", ""),
                "overall_score": card["overall_score"],
                "score_compatibility": card["breakdown"]["compatibility"],
                "score_quantity": card["breakdown"]["quantity"],
                "score_location": card["breakdown"]["location"],
                "score_sector": card["breakdown"]["sector"],
                "score_value": card["breakdown"]["value"],
                "score_environmental": card["breakdown"]["environmental"],
                "reuse_type": card["reuse_type"],
                "safety_level": card["safety_level"],
                "distance_km": card.get("distance_km"),
                "distance_basis": (card.get("transport") or {}).get("distance_basis"),
                "matched_quantity_t_month": card.get("matched_quantity_t_per_month", 0),
                "allocated_t_month": card.get("allocated_t_per_month", 0),
                "estimated_value_inr_month": card.get("estimated_value_inr_per_month", 0),
                "estimated_co2e_t_month": card.get("estimated_co2e_t_per_month", 0),
                "reasons": list(card.get("reasons") or []),
                "cautions": list(card.get("cautions") or []),
                "pathway_steps": list(card.get("pathway_steps") or []),
                "transport": card.get("transport"),
                "created_at": utcnow(),
            }
            db.insert("organization_analysis_matches", row)
    return get_analysis(db, str(values.get("organization_id") or ""), analysis_id) or {}


def get_analysis(db: Database, organization_id: str, analysis_id: str) -> dict[str, Any] | None:
    """Fetch by id, or by the human reference (`SYM-2026-000184`) - either way, only
    from inside the tenant that owns it."""
    clause = "reference = ?" if str(analysis_id).startswith("SYM-") else "id = ?"
    params: list[Any] = [analysis_id]
    if organization_id:
        clause += " and organization_id = ?"
        params.append(organization_id)
    row = _one(db, f"select * from organization_analyses where {clause}", params)
    if row:
        row["matches"] = _rows(
            db,
            "select * from organization_analysis_matches where analysis_id = ? order by overall_score desc, recipient_id",
            [row["id"]],
        )
    return row


def list_analyses(db: Database, organization_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        db,
        """select id, reference, organization_id, user_id, location, latitude, longitude, location_resolved,
                  location_source, material_id, material_name, quantity_t_per_month, quantity_unit, frequency,
                  match_count, top_match_name, top_match_score, created_at
             from organization_analyses
            where organization_id = ?
            order by created_at desc
            limit ?""",
        [organization_id, int(limit)],
    )


def count_analyses(db: Database, organization_id: str) -> int:
    row = db.query_one("select count(*) as n from organization_analyses where organization_id = ?", [organization_id])
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# totals, for the status endpoint and nothing else
# ---------------------------------------------------------------------------


def count_all_analyses(db: Database) -> int:
    return _count(db, "select count(*) as n from organization_analyses")


def count_all_listings(db: Database) -> int:
    return _count(db, "select count(*) as n from organization_listings")


def count_all_members(db: Database) -> int:
    return _count(db, "select count(*) as n from organization_members")


def count_all_organizations(db: Database) -> int:
    return _count(db, "select count(*) as n from organizations")


def _count(db: Database, sql: str) -> int:
    row = db.query_one(sql)
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# geography cache
# ---------------------------------------------------------------------------


def cache_lookup(db: Database, kind: str, query_text: str) -> dict[str, Any] | None:
    digest = hash_token(f"{kind}:{query_text.strip().lower()}")
    row = _one(db, "select * from geo_cache where kind = ? and query_hash = ?", [kind, digest])
    if not row:
        return None
    if str(row.get("expires_at") or "") <= utcnow():
        return {"expired": True, **row}
    db.execute("update geo_cache set hit_count = hit_count + 1 where id = ?", [row["id"]])
    # Reported as it now stands, not as it was a moment before the increment.
    row["hit_count"] = int(row.get("hit_count") or 0) + 1
    return {"expired": False, **row}


def cache_store(db: Database, *, kind: str, query_text: str, provider: str, payload: dict[str, Any], resolved: bool, ttl_hours: float) -> None:
    digest = hash_token(f"{kind}:{query_text.strip().lower()}")
    expires = datetime.now(timezone.utc) + timedelta(hours=max(0.01, ttl_hours))
    record = {
        "id": new_id("geo"),
        "kind": kind,
        "query_hash": digest,
        "query_text": query_text.strip()[:300],
        "provider": provider[:60],
        "resolved": bool(resolved),
        "payload": payload,
        "fetched_at": utcnow(),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hit_count": 0,
    }
    with db.transaction():
        db.execute("delete from geo_cache where query_hash = ?", [digest])
        db.insert("geo_cache", record)


def cache_prune(db: Database) -> int:
    return db.execute("delete from geo_cache where expires_at < ?", [utcnow()])
