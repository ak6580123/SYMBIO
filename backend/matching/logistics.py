"""Minimum viable transport (§8) - a transparent estimate, never a quote.

Symbio has no freight API and no rate contracts in this build, so it does the only
honest thing available: it prices a trip from published-as-assumed constants, shows
every one of them, and states the result as an estimate. A route is then judged on
the number the brief asks for - value minus transport burden - rather than on
distance alone, which is how a 4 km route with a 2-tonne load ends up ranked below a
40 km route with a 40-tonne one.

Nothing in here re-scores a match. `engine` owns the ranking; this module explains
whether the ranked route can physically be trucked without losing money on the road.
"""

from __future__ import annotations

import math
from typing import Any

# --- demo freight model ------------------------------------------------------
# One line each, so the UI can print them and a reviewer can disagree with a
# specific number instead of the whole estimate.
ASSUMPTIONS: tuple[tuple[str, float, str, str], ...] = (
    ("truck_capacity_t", 16.0, "tonnes", "a 16-tonne tipper, the common bulk haulage unit in the dataset"),
    ("diesel_consumption_km_per_litre", 3.2, "km/litre", "laden heavy vehicle, city-plus-highway mix"),
    ("diesel_price_inr_per_litre", 92.0, "₹/litre", "Tamil Nadu commercial diesel, rounded"),
    ("average_speed_kmph", 28.0, "km/hour", "one-way industrial roads, calibrated on the Chennai-area network this build ships with"),
    ("driver_cost_inr_per_hour", 180.0, "₹/hour", "driver and helper, per hour of the round trip"),
    ("tipping_and_gate_inr_per_trip", 600.0, "₹/trip", "weighbridge, gate fee and tipping at both ends"),
    ("loading_hours_per_trip", 1.5, "hours", "loading, uncovered travel and unloading allowance"),
    ("return_load_probability", 0.25, "share of trips", "chance the lorry carries something back, credited against the trip"),
)

CAPACITY = dict((key, value) for key, value, _unit, _why in ASSUMPTIONS)

VIABLE_RATIO = 1.0
"""A route is viable when the material is worth at least as much as the haulage."""
MARGINAL_RATIO = 0.35
"""Below 35% of the material value left after transport, the numbers are close enough
that a return load, a better tip rate or a fuller truck decides it - so it is called
marginal rather than either verdict."""
ZERO_VALUE_FLOOR_INR_PER_TONNE = 250.0
"""Material the knowledge base prices at zero still gets a ceiling: below this per
tonne of haulage, moving it is a favour rather than a cost, which is true of free
fill material and false of a 90 km haul of wet sludge."""


def _per_trip_cost(distance_km: float, load_t: float) -> tuple[float, dict[str, float]]:
    diesel = CAPACITY["diesel_consumption_km_per_litre"]
    price = CAPACITY["diesel_price_inr_per_litre"]
    round_trip_km = 2 * distance_km
    fuel = round_trip_km / diesel * price
    hours = round_trip_km / CAPACITY["average_speed_kmph"] + CAPACITY["loading_hours_per_trip"]
    labour = hours * CAPACITY["driver_cost_inr_per_hour"]
    # A lorry that comes back loaded is a lorry that does not pay a full return leg.
    credit = fuel * CAPACITY["return_load_probability"]
    total = fuel + labour + CAPACITY["tipping_and_gate_inr_per_trip"] - credit
    # Heavier loads spread the fixed part across more tonnes; keep the split visible.
    return round(total, 2), {
        "fuel_inr": round(fuel, 2),
        "labour_inr": round(labour, 2),
        "tipping_inr": CAPACITY["tipping_and_gate_inr_per_trip"],
        "return_load_credit_inr": round(-credit, 2),
        "hours": round(hours, 2),
        "round_trip_km": round(round_trip_km, 1),
        "cost_per_trip_inr": round(total, 2),
        "cost_per_tonne_inr": round(total / load_t, 2) if load_t else 0.0,
    }


def estimate(
    distance_km: float,
    quantity_t_per_month: float,
    value_inr_per_month: float | None = None,
    unit_value_inr_per_tonne: float | None = None,
) -> dict[str, Any]:
    """Price the haulage for one month of one route, and judge the route on it.

    `value_inr_per_month` is the engine's own estimate for this match; passing it in
    (rather than re-deriving a price here) is what keeps the two numbers consistent.
    """
    distance = max(0.0, float(distance_km or 0.0))
    monthly = max(0.0, float(quantity_t_per_month or 0.0))
    capacity = CAPACITY["truck_capacity_t"]

    trips = max(1, math.ceil(monthly / capacity)) if monthly > 0 else 0
    load = round(monthly / trips, 3) if trips else 0.0
    per_trip, parts = _per_trip_cost(distance, load if load else capacity)
    burden = round(per_trip * trips, 2)

    value = float(value_inr_per_month or 0.0)
    unit_value = float(unit_value_inr_per_tonne or 0.0)
    reference_value = value if value > 0 else unit_value * monthly

    cost_per_tonne = round(burden / monthly, 2) if monthly else 0.0
    # What the haulage has to be worth relative to the material, in one number.
    if reference_value > 0:
        ratio = round(burden / reference_value, 4)
        basis = "match value estimated by the engine"
    else:
        ratio = round(cost_per_tonne / ZERO_VALUE_FLOOR_INR_PER_TONNE, 4) if cost_per_tonne else 0.0
        basis = f"₹{ZERO_VALUE_FLOOR_INR_PER_TONNE:,.0f}/tonne floor, because this stream has no recorded price"

    if trips == 0 or monthly <= 0:
        status, status_label = "unknown", "Nothing to move"
    elif ratio <= MARGINAL_RATIO:
        status, status_label = "viable", "Transport costs a small share of the value"
    elif ratio <= VIABLE_RATIO:
        status, status_label = "marginal", "Haulage eats most of the value"
    else:
        status, status_label = "impractical", "Haulage costs more than the material is worth"

    # The quantity at which this route crosses back into `viable`, found by walking
    # the tonnage up: a fuller truck is the only lever the sender controls.
    viable_at = _viable_quantity(distance, unit_value, reference_value / monthly if monthly else 0.0)

    return {
        "estimate": True,
        "distance_km": round(distance, 1),
        "quantity_t_per_month": round(monthly, 3),
        "trips_per_month": trips,
        "load_per_trip_t": load,
        "truck_capacity_t": capacity,
        "cost_per_trip_inr": parts["cost_per_trip_inr"],
        "cost_breakdown": parts,
        "transport_cost_inr_per_month": burden,
        "transport_cost_inr_per_tonne": cost_per_tonne,
        "material_value_inr_per_month": round(value, 2),
        "net_economic_potential_inr_per_month": round(value - burden, 2),
        "burden_to_value_ratio": ratio,
        "ratio_basis": basis,
        "status": status,
        "status_label": status_label,
        "minimum_viable_shipment_t": viable_at["quantity_t_per_month"],
        "minimum_viable_explanation": viable_at["note"],
        "assumptions": [
            {"key": key, "value": value, "unit": unit, "why": why} for key, value, unit, why in ASSUMPTIONS
        ],
        "disclaimer": (
            "Estimate from published demo freight assumptions, not a quotation. Contact a haulier for a price; "
            "nothing here reflects a negotiated rate, fuel surcharge, permits or waiting time."
        ),
    }


def _viable_quantity(distance_km: float, unit_value: float, realised_unit_value: float) -> dict[str, Any]:
    """Smallest monthly tonnage at which haulage stops dominating.

    Two cases, because the honest answer differs: with a per-tonne value the engine
    recorded, we can solve for the tonnage where burden falls under the marginal
    threshold; with a zero-value stream, more tonnage never helps (the material is
    still worthless), so the answer is "no quantity makes this pay".
    """
    if unit_value <= 0 and realised_unit_value <= 0:
        return {
            "quantity_t_per_month": None,
            "note": (
                "No price is recorded for this stream, so no shipment size turns the haul "
                "positive - the route only works if someone pays to take it or the tipper "
                "is going that way anyway."
            ),
        }
    value_per_tonne = unit_value or realised_unit_value
    capacity = CAPACITY["truck_capacity_t"]
    # Quarter-tonne steps up to forty trucks. Starting at a full truck would answer
    # "16 t" for a route that already pays at 2 t, which is the opposite of the
    # useful number - and the status band above must agree with this.
    for tonnes in [n / 4 for n in range(1, 40 * int(capacity * 4) + 1)]:
        trips = max(1, math.ceil(tonnes / capacity))
        load = tonnes / trips
        per_trip, _parts = _per_trip_cost(distance_km, load)
        if per_trip * trips / tonnes <= value_per_tonne * MARGINAL_RATIO:
            return {
                "quantity_t_per_month": round(tonnes, 1),
                "note": (
                    f"At about {tonnes:,.0f} t/month the haul drops to under "
                    f"{MARGINAL_RATIO:.0%} of the material value. Below that, the trip "
                    "is doing more of the work than the material is."
                ),
            }
    return {
        "quantity_t_per_month": None,
        "note": (
            f"Even a {capacity:,.0f}-tonne load cannot bring haulage under {MARGINAL_RATIO:.0%} of the "
            "material value at this distance. Consolidating with a neighbour or finding a nearer "
            "partner is the move, not adding tonnes."
        ),
    }
