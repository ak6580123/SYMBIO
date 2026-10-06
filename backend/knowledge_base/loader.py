"""Loader for the seeded demo data.

The application reads `data/recipients.json` and `data/sources.json` through
these helpers. Swapping the JSON files for Supabase queries later only means
re-implementing these functions - nothing else in the codebase touches the
files directly.
"""

from __future__ import annotations

import json
import os
from typing import Any

from knowledge_base.materials import MATERIALS_BY_ID

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _load(filename: str) -> list[dict[str, Any]]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _enrich_recipient(rec: dict[str, Any]) -> dict[str, Any]:
    """Fill accepted_categories from the KB when the seed file omits them."""
    if not rec.get("accepted_categories"):
        rec["accepted_categories"] = sorted(
            {
                MATERIALS_BY_ID[m]["category"]
                for m in rec.get("accepted_materials", [])
                if m in MATERIALS_BY_ID
            }
        )
    return rec


_RECIPIENTS: list[dict[str, Any]] | None = None
_SOURCES: list[dict[str, Any]] | None = None


def get_recipients() -> list[dict[str, Any]]:
    global _RECIPIENTS
    if _RECIPIENTS is None:
        _RECIPIENTS = [_enrich_recipient(r) for r in _load("recipients.json")]
    return _RECIPIENTS


def get_recipient(recipient_id: str) -> dict[str, Any] | None:
    for r in get_recipients():
        if r["id"] == recipient_id:
            return r
    return None


def get_sources() -> list[dict[str, Any]]:
    global _SOURCES
    if _SOURCES is None:
        _SOURCES = _load("sources.json")
    return _SOURCES


def get_source(source_id: str) -> dict[str, Any] | None:
    for s in get_sources():
        if s["id"] == source_id:
            return s
    return None
