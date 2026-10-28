"""Scenario rules and summaries (§11).

A scenario is the same analysis re-run through the same engine with different inputs,
so the only thing this module is allowed to do is *filter and describe* the result. It
never re-scores, never re-ranks, and never lets a rule rescue a route the safety layer
refused - safety and the quantity window have already run by the time a card gets here.

`compare` is what makes two scenarios legible side by side: for each configuration it
reports the best match the engine produced, the totals, the transport burden the
freight estimate computed, whether any route is viable at all, and - the number the
brief asks for - the monthly tonnage at which the haul starts paying.
"""

from __future__ import annotations

from typing import Any

from matching import engine

# The knobs a scenario may turn, and the field each one lands on.
RULE_FIELDS = (
    "destination_recipient_id",
    "require_viable_transport",
    "max_transport_cost_inr_per_tonne",
    "processing_capability_required",
    "max_processing_burden",
)

RULE_LABELS = {
    "destination_recipient_id": "Named destination only",
    "require_viable_transport": "Transport not impractical",
    "max_transport_cost_inr_per_tonne": "Transport cost ceiling",
    "processing_capability_required": "Required processing step",
    "max_processing_burden": "Maximum processing burden",
}


def rules_from(payload: dict[str, Any]) -> dict[str, Any]:
    """Pick the rule fields out of a request body, dropping the unset ones.

    `0` is a rule with a meaning - a ceiling of zero tonnes of processing burden asks
    for direct reuse only - so it is tested for by identity against `None`/`False`
    rather than by truthiness.
    """
    return {
        key: payload[key]
        for key in RULE_FIELDS
        if key in payload and payload[key] is not None and payload[key] is not False and payload[key] != ""
    }


def apply_rules(cards: list[dict[str, Any]], rules: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter ranked cards. Returns (kept, dropped-with-reason)."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for card in cards:
        for rule, value in rules.items():
            if not _passes(card, rule, value):
                dropped.append(
                    {
                        "match_id": card["id"],
                        "company_name": card["company_name"],
                        "rule": rule,
                        "rule_label": RULE_LABELS[rule],
                        "value": value,
                        "reason": _why(card, rule, value),
                    }
                )
                break
        else:
            kept.append(card)
    return kept, dropped


def _passes(card: dict[str, Any], rule: str, value: Any) -> bool:
    transport = card.get("transport") or {}
    if rule == "destination_recipient_id":
        return card["recipient"]["id"] == value
    if rule == "require_viable_transport":
        return transport.get("status") != "impractical"
    if rule == "max_transport_cost_inr_per_tonne":
        return float(transport.get("transport_cost_inr_per_tonne") or 0.0) <= float(value)
    if rule == "processing_capability_required":
        needle = str(value).lower().replace("_", "")
        return any(needle in str(capability).lower().replace("_", "") for capability in card.get("processing_capability") or [])
    if rule == "max_processing_burden":
        return engine.processing_burden(card["reuse_type"]) <= int(value)
    return True


def _why(card: dict[str, Any], rule: str, value: Any) -> str:
    transport = card.get("transport") or {}
    if rule == "destination_recipient_id":
        return f"{card['company_name']} is not the chosen destination"
    if rule == "require_viable_transport":
        if not transport:
            return (
                "no haulage estimate exists for this route, because the location it starts from has no "
                "coordinates - so its transport can be neither confirmed nor ruled out"
            )
        return f"the transport estimate calls this haul {transport.get('status')} at {transport.get('distance_km')} km"
    if rule == "max_transport_cost_inr_per_tonne":
        return (
            f"haulage is ₹{float(transport.get('transport_cost_inr_per_tonne') or 0):,.0f}/tonne against a "
            f"ceiling of ₹{float(value):,.0f}"
        )
    if rule == "processing_capability_required":
        return f"this partner records no {value.replace('_', ' ')} capability"
    if rule == "max_processing_burden":
        burden = engine.processing_burden(card["reuse_type"])
        return f"{card['reuse_type'].replace('_', ' ').lower()} needs {burden} steps of processing, above the ceiling of {value}"
    return "excluded"


def transport_rollup(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """The freight picture across a scenario's routes."""
    priced = [card for card in cards if card.get("transport")]
    unpriced = len(cards) - len(priced)
    # The money only means something as a total when every route in the set was
    # priced. With a route missing an estimate the sum is stated as a partial one.
    burden = sum(float((card.get("transport") or {}).get("transport_cost_inr_per_month") or 0.0) for card in cards)
    value = sum(float(card.get("estimated_value_inr_per_month") or 0.0) for card in cards)
    statuses = [str((card.get("transport") or {}).get("status")) for card in cards]
    minima = [
        float(card["transport"]["minimum_viable_shipment_t"])
        for card in cards
        if (card.get("transport") or {}).get("minimum_viable_shipment_t")
    ]
    if not priced:
        return {
            "transport_cost_inr_per_month": None,
            "material_value_inr_per_month": round(value, 2),
            "net_economic_potential_inr_per_month": None,
            "viable_routes": 0,
            "marginal_routes": 0,
            "impractical_routes": 0,
            "unknown_routes": len(cards),
            "easiest_viable_shipment_t": None,
            # Same shape as the priced rollup below: a caller should never have to
            # know that this branch omits a key the other one carries.
            "routes_without_freight": len(cards),
            "label": "No route in this set could be priced - none of them has coordinates to measure a haul from",
        }
    return {
        "transport_cost_inr_per_month": round(burden, 2),
        "material_value_inr_per_month": round(value, 2),
        "net_economic_potential_inr_per_month": round(value - burden, 2),
        "routes_without_freight": unpriced,
        "viable_routes": statuses.count("viable"),
        "marginal_routes": statuses.count("marginal"),
        "impractical_routes": statuses.count("impractical"),
        "unknown_routes": statuses.count("unknown"),
        # The easiest route to start with: the lowest tonnage at which any of these
        # partners' hauls pays for itself.
        "easiest_viable_shipment_t": round(min(minima), 1) if minima else None,
        "label": "Transport estimate across the shown routes - demo assumptions, not a quote",
    }


def best_match_row(cards: list[dict[str, Any]], sort_label: str) -> dict[str, Any] | None:
    if not cards:
        return None
    card = cards[0]
    transport = card.get("transport") or {}
    return {
        "match_id": card["id"],
        "company_name": card["company_name"],
        "sector_label": card.get("sector_label"),
        "score": card["score"],
        "distance_km": card["distance_km"],
        "estimated_value_inr_per_month": card["estimated_value_inr_per_month"],
        "estimated_co2e_t_per_month": card["estimated_co2e_t_per_month"],
        "reuse_type": card["reuse_type"],
        "safety_level": card["safety_level"],
        "matched_quantity_t_per_month": card["matched_quantity_t_per_month"],
        "transport_status": transport.get("status"),
        "transport_cost_inr_per_month": transport.get("transport_cost_inr_per_month"),
        "net_economic_potential_inr_per_month": transport.get("net_economic_potential_inr_per_month"),
        "minimum_viable_shipment_t": transport.get("minimum_viable_shipment_t"),
        "ordered_by": sort_label,
    }


def summarise(
    *,
    label: str,
    changed: dict[str, Any],
    warnings: list[str],
    cards: list[dict[str, Any]],
    totals: dict[str, Any],
    scored_partners: int,
    rules: dict[str, Any],
    dropped: list[dict[str, Any]],
    sort_label: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "changed": changed,
        "rules": {key: value for key, value in rules.items()},
        "rule_labels": {RULE_LABELS[key]: value for key, value in rules.items()},
        "warnings": warnings,
        "match_count": len(cards),
        "scored_partners": scored_partners,
        "dropped_by_rule": dropped,
        "best_match": best_match_row(cards, sort_label),
        "totals": totals,
        "transport": transport_rollup(cards),
        "viable_at_t_per_month": (cards[0].get("transport") or {}).get("minimum_viable_shipment_t") if cards else None,
    }
