"""The material flow funnel (§9): where the tonnes go, stage by stage.

Six stages, each one a strict subset of the one before it, so a drop between two bars
is a real loss rather than a change of accounting. Every stage prints its own
definition, because a funnel whose stages are undefined is decoration.

The tonnage comes from stored analyses - the same records the dashboard and the impact
page read - and the viability test uses `matching.logistics`, so "economically viable"
means *this build's transport estimate does not call the haul impractical*, not
"approved by an economist".

The last two stages are equal in this dataset, and the module says so out loud rather
than inventing a processing loss: there are no weighbridge receipts or return records
to compute one from.
"""

from __future__ import annotations

from typing import Any

from matching import logistics
from services import storage

STAGES = (
    "Generated",
    "Technically reusable",
    "Economically viable",
    "Matched",
    "Processed",
    "Reused",
)

DEFINITIONS = {
    "Generated": "Tonnes/month offered by every analysis in the store, at the source's own stated figure.",
    "Technically reusable": (
        "Of those, the tonnes whose material the knowledge base can describe a reuse route for. An unidentified "
        "stream, or one where the safety layer refused every partner, is not technically reusable *yet*."
    ),
    "Economically viable": (
        "Matched tonnes on routes the transport estimate does not call impractical - i.e. the haul does not cost "
        "more than the material is worth, on this build's demo freight assumptions."
    ),
    "Matched": "Sum of matched_quantity_t_per_month across every ranked match: what partners could take.",
    "Processed": "Sum of allocated_t_per_month: the share of the source's tonnes this pool of partners actually absorbs.",
    "Reused": "Tonnes a partner took in and turned into a product. Equal to Processed here - see the caveat.",
}

CAVEATS = {
    "Reused": (
        "The demo dataset has no weighbridge receipts, no returns and no processing-loss factors, so nothing can be "
        "subtracted. A deployment that records intake slips would fill this stage from them."
    ),
    "Economically viable": (
        "An estimate from published freight assumptions, not a quote. A route marked impractical here can be "
        "perfectly economic with a return load or a shared lorry."
    ),
}


def _analysis_rows(analysis_id: str | None) -> list[dict[str, Any]]:
    if analysis_id:
        analysis = storage.get(analysis_id)
        return [analysis] if analysis else []
    return storage.all_newest_first()


def flow(*, analysis_id: str | None = None, include_routes: int = 12) -> dict[str, Any]:
    """Build the funnel, and the routes behind the lower bars.

    Each stage is capped at the stage above it. That matters: `matched_quantity` is
    what a partner *could* take, and 14 partners can each be ready for 60 t/month of a
    5 t stream without the stream growing. Capping keeps the funnel a subset chain, and
    `apparent_tonnes_per_month` shows the uncapped figure beside it so nothing is hidden.
    """
    analyses = _analysis_rows(analysis_id)
    if not analyses:
        return {
            "stages": [
                {"stage": stage, "tonnes_per_month": 0.0, "apparent_tonnes_per_month": 0.0, "share_of_generated": 0.0,
                 "definition": DEFINITIONS[stage], "caveat": CAVEATS.get(stage)}
                for stage in STAGES
            ],
            "routes": [],
            "note": "No analyses in the store yet, so there is nothing to flow. Run POST /api/analyze first.",
            "demo_data": True,
        }

    generated = 0.0
    reusable = 0.0
    viable = 0.0
    matched = 0.0
    processed = 0.0
    reused = 0.0
    routes: list[dict[str, Any]] = []
    blocked_streams: list[dict[str, Any]] = []
    materials_in_flow: set[str] = set()

    for analysis in analyses:
        source = analysis["source"]
        offered = float(source["quantity_t_per_month"])
        generated += offered
        material = analysis["material"]
        matches = analysis.get("matches") or []
        identified = material["id"] != "unknown_material"
        allowed = [m for m in matches if m["reuse_type"] not in {"RESTRICTED", "UNKNOWN"}]

        if identified and allowed:
            reusable += offered
            materials_in_flow.add(material["id"])
        else:
            blocked_streams.append(
                {
                    "analysis_id": analysis["id"],
                    "material": material["name"],
                    "tonnes_per_month": round(offered, 3),
                    "reason": (
                        "material not identified, so no reuse route can be claimed"
                        if not identified
                        else "every partner route was refused by the safety layer"
                    ),
                }
            )

        stream_viable = 0.0
        stream_matched = 0.0
        stream_allocated = 0.0
        stream_reused = 0.0
        for match in allowed:
            matched_t = float(match["matched_quantity_t_per_month"])
            allocated_t = float(match["allocated_t_per_month"])
            if match["distance_km"] is None:
                # Nothing to price this against, so the route is neither counted as
                # viable nor thrown away: it is reported as unpriced, and the funnel
                # note below says how much of the tonnage that covers.
                estimate = None
            else:
                estimate = logistics.estimate(
                    float(match["distance_km"]),
                    matched_t,
                    float(match["estimated_value_inr_per_month"]),
                    (float(match["estimated_value_inr_per_month"]) / matched_t) if matched_t > 0 else 0.0,
                )
            if estimate and estimate["status"] != "impractical":
                stream_viable += matched_t
            stream_matched += matched_t
            stream_allocated += allocated_t
            steps = match["reuse_pathway"]["steps"] if isinstance(match["reuse_pathway"], dict) else match["reuse_pathway"]
            product = steps[4] if len(steps) > 4 else "Assessed Material"
            if product != "Assessed Material":
                stream_reused += allocated_t
            routes.append(
                {
                    "source": source["location"],
                    "source_sector": source["source_type"],
                    "material": material["name"],
                    "processor": steps[2] if len(steps) > 2 else "Not recorded",
                    "recipient": match["recipient"]["company_name"],
                    "recipient_id": match["recipient"]["id"],
                    "sector": match["recipient"]["sector"],
                    "product": product,
                    "tonnes_per_month": round(allocated_t, 3),
                    "matched_tonnes_per_month": round(matched_t, 3),
                    "value_inr_per_month": round(float(match["estimated_value_inr_per_month"]), 2),
                    "co2e_t_per_month": round(float(match["estimated_co2e_t_per_month"]), 3),
                    "transport_status": estimate["status"] if estimate else "unavailable",
                    "transport_cost_inr_per_month": estimate["transport_cost_inr_per_month"] if estimate else None,
                    "net_economic_potential_inr_per_month": (
                        estimate["net_economic_potential_inr_per_month"] if estimate else None
                    ),
                    "distance_km": match["distance_km"],
                    "analysis_id": analysis["id"],
                    "match_id": match["id"],
                }
            )
        # capped per stream, so one small stream cannot be counted 14 times over
        viable += min(offered, stream_viable)
        matched += min(offered, stream_matched)
        processed += min(stream_allocated, offered)
        reused += min(stream_reused, offered)

    routes.sort(key=lambda row: (-row["tonnes_per_month"], row["recipient"]))

    raw = [generated, reusable, viable, matched, processed, reused]
    stages: list[dict[str, Any]] = []
    previous: float | None = None
    for stage, tonnes in zip(STAGES, raw):
        capped = tonnes if previous is None else min(tonnes, previous)
        previous = capped
        stages.append(
            {
                "stage": stage,
                "tonnes_per_month": round(capped, 3),
                "apparent_tonnes_per_month": round(tonnes, 3),
                "capped_by_previous_stage": abs(tonnes - capped) > 1e-9,
                "share_of_generated": round(capped / generated, 4) if generated else 0.0,
                "definition": DEFINITIONS[stage],
                "caveat": CAVEATS.get(stage),
            }
        )

    # Where the funnel leaks most, in tonnes - the number a planner acts on.
    drops = [
        {
            "from": a["stage"],
            "to": b["stage"],
            "lost_tonnes_per_month": round(a["tonnes_per_month"] - b["tonnes_per_month"], 3),
        }
        for a, b in zip(stages, stages[1:])
    ]
    biggest = max(drops, key=lambda row: row["lost_tonnes_per_month"]) if drops else None

    partners = {row["recipient"] for row in routes}
    total_appetite = round(raw[3], 2)  # the uncapped matched sum
    return {
        "stages": stages,
        "drops": drops,
        "biggest_loss": biggest,
        "recovery_percent": round(100.0 * stages[4]["tonnes_per_month"] / generated, 1) if generated else 0.0,
        "reused_percent": round(100.0 * stages[5]["tonnes_per_month"] / generated, 1) if generated else 0.0,
        "routes": routes[:include_routes],
        "route_count": len(routes),
        "partner_count": len(partners),
        "material_count": len(materials_in_flow),
        "analyses": len(analyses),
        "blocked_streams": blocked_streams,
        "partner_appetite_note": (
            "Matched tonnage is what partners could take, which for a small stream is more than the stream. Stages "
            "are therefore capped at the stage above; `apparent_tonnes_per_month` is the uncapped sum and "
            f"`partner_appetite_t_per_month` is the pool's total readiness ({total_appetite} t/month)."
        ),
        "partner_appetite_t_per_month": total_appetite,
        "generated_note": (
            "Generated is the sum of what each analysis stated, so a stream counted here is a stream someone "
            "described - not a city-wide inventory."
        ),
        # Computed rather than asserted: the two stages carry the same number because
        # there is nothing in this dataset that would make them differ.
        # Computed, not asserted: these two stages are equal only because nothing in
        # this dataset can make a partner refuse a load it has already accepted.
        "reused_equals_processed": abs(stages[5]["tonnes_per_month"] - stages[4]["tonnes_per_month"]) < 1e-9,
        "reused_note": CAVEATS["Reused"],
        "note": (
            "Six stages, each a subset of the one before it. Tonnages are per month, from the stored analyses; "
            "viability is this build's transport estimate, labelled as an estimate."
        ),
        "demo_data": True,
    }
