"""Editing a listing an organisation owns (§5).

Publishing itself stays where it was (`POST /api/listings`, because it is the same
validation whether or not anyone is signed in). What lives here is the part that only
makes sense with a tenant: change it, pause it, close it, reopen it - and see the rows
nobody else can see, including the ones you took off the marketplace.

Deactivating is a status change, never a delete. A listing that led somewhere is part of
the record; and `closed` is what keeps it from being matched while leaving the audit
trail intact.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api.deps import require_actor, require_database, require_permission
from db import repositories as repo
from models.schemas import ListingPatch, ListingStatusRequest
from services import analysis as analysis_service
from services import listings as listings_service
from services import persistence
from knowledge_base.materials import MATERIALS_BY_ID

# Mounted under /api/org/listings: these routes only make sense for a tenant, and the
# URL says so. Publishing stays on the existing `POST /api/listings`, which serves a
# visitor and a signed-in organisation through the same validation.
router = APIRouter(prefix="/api/org/listings", tags=["marketplace"])

EDITABLE_STATUS = ("active", "paused", "closed")


def _row_view(row: dict[str, Any]) -> dict[str, Any]:
    return persistence.advertised(row, own=True)


@router.get("/mine")
def my_listings(request: Request, status: str | None = None, kind: str | None = None, actor=Depends(require_actor)) -> dict[str, Any]:
    db = require_database(request)
    rows = repo.list_organization_listings(db, actor.organization_id, status=status, kind=kind)
    return {
        "listings": [_row_view(row) for row in rows],
        "count": len(rows),
        "statuses": list(EDITABLE_STATUS),
        "persistence": persistence.describe(),
    }


@router.patch("/{listing_id}")
def edit(
    listing_id: str, payload: ListingPatch, request: Request, actor=Depends(require_permission("edit_listing"))
) -> dict[str, Any]:
    """Change what the organisation stated. The kind of listing is not one of them."""
    db = require_database(request)
    existing = repo.get_listing(db, actor.organization_id, listing_id)
    if not existing:
        raise HTTPException(status_code=404, detail="That listing is not one of yours, so it cannot be changed.")
    changes = payload.model_dump(exclude_none=True)
    # Any of the three price names means the one stored column; more than one at a
    # time is a contradiction, not something to pick a winner from.
    prices = [key for key in ("price_inr_per_tonne", "asking_price_inr_per_tonne", "offer_price_inr_per_tonne") if key in changes]
    if len(prices) > 1:
        raise HTTPException(
            status_code=422,
            detail="Send one price, not several: a supply listing has an asking price and a demand listing an offer.",
        )
    if prices:
        for key in prices[1:] or []:
            del changes[key]
        changes["price_inr_per_tonne"] = changes.pop(prices[0])
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to change - send at least one field.")

    materials = changes.get("material_ids")
    if materials is not None:
        unknown = [m for m in materials if m not in MATERIALS_BY_ID]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{', '.join(unknown)} is not a material in the Symbio knowledge base. A listing can only "
                    "offer or request a material the knowledge base describes."
                ),
            )
        if not materials:
            raise HTTPException(status_code=422, detail="A listing has to name at least one material.")
    if "price_inr_per_tonne" in changes:
        ceiling = listings_service.price_ceiling_inr()
        if float(changes["price_inr_per_tonne"]) > ceiling:
            raise HTTPException(
                status_code=422,
                detail=f"price must stay at or below the knowledge base ceiling of ₹{ceiling:,.0f}/tonne",
            )
    if "location" in changes:
        changes.update(analysis_service.place_fields(str(changes.get("location") or "")))

    # The row's own status is not edited through this route: pausing is an action with a
    # button on it, so it has an endpoint of its own and its own permission.
    changes.pop("status", None)
    repo.update_listing(db, actor.organization_id, listing_id, changes)
    updated = repo.get_listing(db, actor.organization_id, listing_id)
    return {"listing": _row_view(updated or {}), "saved": True, "changed": sorted(changes)}


@router.post("/{listing_id}/status")
def set_status(
    listing_id: str,
    payload: ListingStatusRequest,
    request: Request,
    actor=Depends(require_permission("deactivate_listing")),
) -> dict[str, Any]:
    """ACTIVE, PAUSED or CLOSED. Closing one takes it out of the marketplace and leaves
    it in the organisation's history."""
    db = require_database(request)
    if payload.status not in EDITABLE_STATUS:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {', '.join(EDITABLE_STATUS)}",
        )
    existing = repo.get_listing(db, actor.organization_id, listing_id)
    if not existing:
        raise HTTPException(status_code=404, detail="That listing is not one of yours, so it cannot be changed.")
    note = {
        "active": "Back on the marketplace. Anything matched while it was paused will be offered again on the next look.",
        "paused": "Hidden from the marketplace and from matching. Nothing about the listing itself was changed.",
        "closed": "Withdrawn. It stays in your organisation's records and stops being shown to anyone else.",
    }[payload.status]
    repo.set_listing_status(db, actor.organization_id, listing_id, payload.status)
    updated = repo.get_listing(db, actor.organization_id, listing_id)
    return {"listing": _row_view(updated or {}), "status": payload.status, "saved": True, "note": note}
