"""The tenant's own data: profile, facilities, members, history (§3, §4, §6).

Every route here is scoped to the caller's organisation by the dependency, and every
repository call underneath it repeats that scope in its `where` clause. The redundancy
is the point: if this file ever grew a route that forgot, the data layer still would not
answer for another tenant.

Two things you will not find here:

* **A way to verify yourself.** `verification_status` is never read from a request
  body on any route in Symbio. An organisation that can mark itself verified has a
  field, not a credential.
* **A way to reach another organisation.** `X-Symbio-Organization`-style switching
  exists only as `POST /api/auth/organizations/select`, and even that is filtered
  through the membership table.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from api.deps import require_actor, require_database, require_permission
from db import repositories as repo
from models.schemas import (
    FacilityRequest,
    MemberRequest,
    OrganizationPatch,
    ProfileRequest,
)
from knowledge_base.materials import MATERIALS_BY_ID
from services import persistence
from services import analysis as analysis_service
from services import profiles as profiles_service
from services.rbac import ROLES, describe as describe_permissions

router = APIRouter(prefix="/api/org", tags=["organisation"])

LIST_FIELDS = (
    "products_produced",
    "processing_capabilities",
    "certifications",
)
MATERIAL_FIELDS = ("materials_required", "waste_streams")


def _bundle(request: Request, actor) -> dict[str, Any]:
    """Organisation, profile, facilities and the counts that make them useful."""
    db = require_database(request)
    organization = repo.get_organization(db, actor.organization_id) or dict(actor.organization)
    profile = repo.get_profile(db, actor.organization_id) or {}
    facilities = repo.list_facilities(db, actor.organization_id)
    return {
        "organization": {
            "id": organization.get("id"),
            "name": organization.get("name"),
            "sector": organization.get("sector") or "",
            "description": organization.get("description") or "",
            "website": organization.get("website") or "",
            "contact": {
                "name": organization.get("contact_name") or "",
                "email": organization.get("contact_email") or "",
                "phone": organization.get("phone") or "",
            },
            "verification": {
                "status": organization.get("verification_status") or "unverified",
                "note": organization.get("verification_note") or "",
                "meaning": "How Symbio's own team has assessed this organisation. Nobody can set it from here.",
            },
            "created_at": str(organization.get("created_at") or ""),
        },
        "profile": {
            "sector": profile.get("sector") or "",
            "products_produced": profile.get("products_produced") or [],
            "materials_required": profile.get("materials_required") or [],
            "waste_streams": profile.get("waste_streams") or [],
            "processing_capabilities": profile.get("processing_capabilities") or [],
            "certifications": profile.get("certifications") or [],
            "contact": profile.get("contact") or {},
            "updated_at": str(profile.get("updated_at") or ""),
        },
        "facilities": [
            {
                "id": row["id"],
                "name": row["name"],
                "location": row.get("location") or "",
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "location_resolved": bool(row.get("location_resolved")),
                "location_source": row.get("location_source") or "",
                "notes": row.get("notes") or "",
            }
            for row in facilities
        ],
        "members": [
            {
                "user_id": row["user_id"],
                "email": row.get("email"),
                "display_name": row.get("display_name") or "",
                "role": row["role"],
                "role_label": ROLES.get(str(row["role"]), {}).get("label", row["role"]),
            }
            for row in repo.members(db, actor.organization_id)
        ],
        "counts": {
            "listings": repo.count_organization_listings(db, actor.organization_id),
            "analyses": repo.count_analyses(db, actor.organization_id),
            "facilities": len(facilities),
        },
        "you": {"role": actor.role, "role_label": ROLES[actor.role]["label"], "can_write": actor.can("edit_listing")},
        "persistence": persistence.describe(),
    }


@router.get("")
def read_organization(request: Request, actor=Depends(require_actor)) -> dict[str, Any]:
    return _bundle(request, actor)


@router.patch("")
def edit_organization(
    payload: OrganizationPatch, request: Request, actor=Depends(require_permission("edit_organization"))
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_none=True)
    db = require_database(request)
    repo.update_organization(db, actor.organization_id, changes)
    return {**_bundle(request, actor), "saved": True}


@router.put("/profile")
def save_profile(
    payload: ProfileRequest, request: Request, actor=Depends(require_permission("edit_profile"))
) -> dict[str, Any]:
    """Save the profile. Material ids are checked; nothing here is scored.

    The profile is a declaration by the organisation, so it is validated the way a
    listing is: a material the knowledge base does not have is refused, because it would
    otherwise show up beside real ones and be read as real.
    """
    db = require_database(request)
    # Only what the caller actually sent is written, so a screen that saves one section
    # of a profile does not empty the others. An empty list *was* sent, and does clear.
    record = payload.model_dump(include=payload.model_fields_set or None)
    _check_materials(record)
    # Only the fields that arrived are normalised and written: filling in an empty list
    # for something the caller left out would clear a line somebody else typed.
    for field in LIST_FIELDS:
        if field in record:
            record[field] = [str(item).strip()[:200] for item in record.get(field) or [] if str(item).strip()][:40]
    for field in MATERIAL_FIELDS:
        if field in record:
            record[field] = _trim_material_lines(record.get(field) or [])
    saved = repo.save_profile(db, actor.organization_id, record, updated_by=actor.user_id)
    sector = str((saved or {}).get("sector") or "")
    template = profiles_service.sector_profile(sector) if sector else None
    return {
        "profile": saved or {},
        "saved": True,
        "template_available": bool(template),
        "note": (
            "Saved against your organisation. Symbio stores what you stated; the sector template that describes "
            "your industry stays separate, and the profile page labels which line came from which."
        ),
    }


@router.get("/facilities")
def facilities(request: Request, actor=Depends(require_actor)) -> dict[str, Any]:
    db = require_database(request)
    return {"facilities": repo.list_facilities(db, actor.organization_id), "persistence": persistence.describe()}


@router.post("/facilities", status_code=201)
def create_facility(
    payload: FacilityRequest, request: Request, actor=Depends(require_permission("edit_facility"))
) -> dict[str, Any]:
    db = require_database(request)
    values = payload.model_dump(exclude_none=True)
    # A stated place is placed if and only if something can actually place it: the
    # recorded network first, then the geocoder if one is configured. Never a default.
    values.update(analysis_service.place_fields(str(values.get("location") or "")))
    created = repo.create_facility(db, actor.organization_id, values)
    return {"facility": created, "saved": True}


@router.patch("/facilities/{facility_id}")
def edit_facility(
    facility_id: str, payload: FacilityRequest, request: Request, actor=Depends(require_permission("edit_facility"))
) -> dict[str, Any]:
    db = require_database(request)
    changes = payload.model_dump(exclude_none=True)
    changes.update(analysis_service.place_fields(str(changes.get("location") or "")))
    repo.update_facility(db, actor.organization_id, facility_id, changes)
    row = _facility_or_404(db, actor.organization_id, facility_id)
    return {"facility": row, "saved": True}


@router.delete("/facilities/{facility_id}")
def remove_facility(facility_id: str, request: Request, actor=Depends(require_permission("edit_facility"))) -> dict[str, Any]:
    db = require_database(request)
    _facility_or_404(db, actor.organization_id, facility_id)
    removed = repo.delete_facility(db, actor.organization_id, facility_id)
    return {"removed": bool(removed), "note": "Listings and analyses keep their rows; they stop pointing here."}


@router.get("/members")
def members(request: Request, actor=Depends(require_actor)) -> dict[str, Any]:
    db = require_database(request)
    rows = repo.members(db, actor.organization_id)
    return {
        "members": [
            {
                "user_id": row["user_id"],
                "email": row.get("email"),
                "role": row["role"],
                "role_label": ROLES.get(str(row["role"]), {}).get("label", row["role"]),
                "since": str(row.get("created_at") or "")[:10],
            }
            for row in rows
        ],
        "roles": {key: dict(value) for key, value in ROLES.items()},
    }


@router.post("/members", status_code=201)
def add_member(payload: MemberRequest, request: Request, actor=Depends(require_permission("manage_members"))) -> dict[str, Any]:
    db = require_database(request)
    # A `LookupError` from the repository means "that address has no account yet". The
    # application-level handler turns it into a 404 with that sentence, which is the
    # truth of it: nothing is missing from what you already have, the invitation just
    # cannot land until that person signs up.
    added = repo.add_member(db, organization_id=actor.organization_id, email=payload.email.strip(), role=payload.role)
    return {
        "member": {"user_id": added["id"], "email": added.get("email"), "role": added["role"]},
        "note": "They see this organisation the moment they sign in - there is nothing to accept.",
    }


@router.delete("/members/{user_id}")
def remove_member(user_id: str, request: Request, actor=Depends(require_permission("manage_members"))) -> dict[str, Any]:
    db = require_database(request)
    rows = repo.members(db, actor.organization_id)
    admins = [row for row in rows if row["role"] == "organization_admin"]
    if len(admins) <= 1 and any(row["user_id"] == user_id and row["role"] == "organization_admin" for row in rows):
        raise ValueError(
            "This is the only administrator left in the organisation, so it cannot be removed. "
            "Add another administrator first."
        )
    removed = repo.remove_member(db, actor.organization_id, user_id)
    if removed:
        repo.revoke_all_sessions(db, user_id)
    return {"removed": bool(removed), "note": "Their sessions for this organisation end now."}


@router.get("/permissions")
def permissions() -> dict[str, Any]:
    """Published so the UI can be honest about a role, and so the table is testable."""
    return {"roles": {key: dict(value) for key, value in ROLES.items()}, "permissions": describe_permissions()}


@router.get("/history")
def history(request: Request, limit: int = 25, actor=Depends(require_actor)) -> dict[str, Any]:
    """The analysis list §6 asks for. Ordered newest first, scoped to this tenant."""
    rows = persistence.history(limit=max(1, min(limit, 100)))
    return {
        "analyses": rows,
        "count": len(rows),
        "persistence": persistence.describe(),
        "note": (
            "Each row is the analysis as it was finished. Opening one shows the stored ranking rather than a "
            "fresh run, so a number here always matches the one someone saw at the time."
        ) if rows else None,
    }


def _check_materials(record: dict[str, Any]) -> None:
    for field in MATERIAL_FIELDS:
        rows = record.get(field) or []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{field} entry {index + 1} has to state a material and, optionally, a note.")
            material_id = str(row.get("material_id") or "").strip()
            if not material_id:
                raise ValueError(f"Every {field.replace('_', ' ')} line has to name a material Symbio knows.")
            if material_id not in MATERIALS_BY_ID:
                raise ValueError(
                    f"'{material_id}' is not a material in the Symbio knowledge base, so it cannot be listed as "
                    "one of yours."
                )
            quantity = row.get("quantity_t_per_month")
            if quantity is not None:
                try:
                    value = float(quantity)
                except (TypeError, ValueError):
                    raise ValueError("A waste stream's quantity has to be a number of tonnes per month.") from None
                if value < 0:
                    raise ValueError("A waste stream's quantity cannot be negative.")


def _trim_material_lines(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:40]:
        entry: dict[str, Any] = {
            "material_id": str(row.get("material_id")),
            "name": MATERIALS_BY_ID[str(row.get("material_id"))]["name"],
        }
        if row.get("note"):
            entry["note"] = str(row["note"])[:300]
        for key in ("quantity_t_per_month", "moisture_percent"):
            if row.get(key) is not None:
                entry[key] = float(row[key])
        for key in ("frequency", "location"):
            if row.get(key):
                entry[key] = str(row[key])[:80]
        out.append(entry)
    return out


def _facility_or_404(db: Any, organization_id: str, facility_id: str) -> dict[str, Any]:
    for row in repo.list_facilities(db, organization_id):
        if row["id"] == facility_id:
            return row
    raise LookupError("That facility is not part of your organisation.")
