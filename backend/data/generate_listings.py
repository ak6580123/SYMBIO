"""One-off generator for backend/data/listings.json (the demo marketplace).

Run from the backend directory:  python data/generate_listings.py

The point of generating rather than typing the file is that no listing can disagree
with the record it is attached to. A demand listing's price is that partner's
`estimated_price_inr_per_tonne`, its quantity is clamped into its own min/max window,
and its materials must be ones that partner already lists. A supply listing offers the
source's recorded `material_hint` at the knowledge base's typical price. Only the
quantity, the distance ceiling, the requirements and the note are authored here - the
numbers are copied.
"""

import json
import os

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from knowledge_base.loader import get_recipients  # noqa: E402
from knowledge_base.materials import MATERIALS_BY_ID, get_material  # noqa: E402

SOURCES = {
    s["id"]: s for s in json.loads(open(os.path.join(HERE, "sources.json"), encoding="utf-8").read())
}
RECIPIENTS = {r["id"]: r for r in get_recipients()}

# (listing id, kind, party, material ids, tonnes/month, max distance km, requirements, note, created)
DEMAND = [
    (
        "lst_dem_001",
        "rec_cement_01",
        ["fly_ash", "bottom_ash"],
        80.0,
        60.0,
        {"moisture_below_percent": 25, "excluded_contaminants": ["municipal mixed waste", "domestic ash"]},
        "Two rakes a month if the loss-on-ignition holds under 5%. Gate test on every tipper.",
        "2026-09-01",
    ),
    (
        "lst_dem_002",
        "rec_brick_01",
        ["fly_ash", "marble_slurry"],
        24.0,
        45.0,
        {"moisture_below_percent": 40, "excluded_contaminants": ["plastic", "municipal waste"]},
        "Wet slurry is fine - we have a curing yard. Anything with plastic in it stops the plant.",
        "2026-09-03",
    ),
    (
        "lst_dem_003",
        "rec_paper_01",
        ["cardboard", "paper_waste"],
        30.0,
        35.0,
        {"moisture_below_percent": 18, "excluded_contaminants": ["glossy print", "plastic liner"]},
        "Baled and dry. A wet bale is weighed as water and paid as water.",
        "2026-09-05",
    ),
    (
        "lst_dem_004",
        "rec_road_01",
        ["steel_slag", "copper_slag", "concrete_waste"],
        150.0,
        70.0,
        {"excluded_contaminants": ["organic waste", "asbestos"], "needs_leach_test": True},
        "Free material, paid haulage - the leach report is the price of admission.",
        "2026-09-06",
    ),
    (
        "lst_dem_005",
        "rec_compost_01",
        ["green_waste", "food_processing_waste"],
        40.0,
        25.0,
        {"excluded_contaminants": ["plastic film", "glass", "metal"]},
        "Segregated only. A mixed load is rejected at the weighbridge, not picked through.",
        "2026-09-08",
    ),
    (
        "lst_dem_006",
        "rec_adsorb_01",
        ["rice_husk_ash", "sawdust"],
        4.0,
        120.0,
        {"moisture_below_percent": 12, "needs_assay": True},
        "Small tonnage, tight specification - an assay before anything enters the store.",
        "2026-09-10",
    ),
    (
        "lst_dem_007",
        "rec_furn_01",
        ["textile_waste"],
        2.5,
        18.0,
        {"excluded_contaminants": ["foam", "synthetic fabric"]},
        "Woven cotton offcuts for upholstery filling. Foam is not textile and stays out.",
        "2026-09-12",
    ),
    (
        "lst_dem_008",
        "rec_pack_01",
        ["cardboard"],
        12.0,
        30.0,
        {"moisture_below_percent": 20},
        "Trim-offs and punchings only - clean fibre, already baled, is what we can pay for.",
        "2026-09-14",
    ),
    (
        "lst_dem_009",
        "rec_plastic_01",
        ["plastic_pet"],
        20.0,
        55.0,
        {"excluded_contaminants": ["multilayer film", "PVC"]},
        "Clear or light-blue PET only, caps and labels off. Mixed polymer goes to the other line.",
        "2026-09-15",
    ),
    (
        "lst_dem_010",
        "rec_glass_01",
        ["glass_waste"],
        25.0,
        40.0,
        {"excluded_contaminants": ["ceramics", "mirror glass", "Pyrex"]},
        "Colour-sorted cullet. One piece of porcelain in a batch costs a furnace charge.",
        "2026-09-16",
    ),
]

SUPPLY = [
    (
        "lst_sup_001",
        "src_ind_01",
        55.0,
        80.0,
        {"moisture_below_percent": 30},
        "Dry electrostatic precipitator ash, consistent quality, own tipper fleet.",
        "2026-09-02",
    ),
    (
        "lst_sup_002",
        "src_sme_01",
        6.0,
        20.0,
        {"excluded_contaminants": ["nails", "concrete"]},
        "De-nailed where we can. Bags, no pallet - a shared tempo load at a time.",
        "2026-09-04",
    ),
    (
        "lst_sup_003",
        "src_house_01",
        3.0,
        15.0,
        {},
        "240 apartments, baled weekly by the resident committee.",
        "2026-09-07",
    ),
    (
        "lst_sup_004",
        "src_ind_05",
        45.0,
        40.0,
        {},
        "Stone-cutting slurry; filter-pressed cake once a week, the rest as it comes off the saw.",
        "2026-09-09",
    ),
    (
        "lst_sup_005",
        "src_agri_01",
        12.0,
        60.0,
        {},
        "Husk from the paddy mill, and boiler ash when it has not been allowed to sinter.",
        "2026-09-11",
    ),
    (
        "lst_sup_006",
        "src_ind_04",
        18.0,
        50.0,
        {"needs_leach_test": True},
        "Reclaimed moulding sand, screened, chloride untested - the report is on you.",
        "2026-09-13",
    ),
    (
        "lst_sup_007",
        "src_sme_02",
        4.0,
        22.0,
        {"excluded_contaminants": ["foam", "synthetic blend"]},
        "Cutroom offcuts, cotton and silk, kept separate from the padding since the last audit.",
        "2026-09-17",
    ),
    (
        "lst_sup_008",
        "src_house_02",
        2.5,
        12.0,
        {},
        "Bottle collection from 14 shops, rinsed and de-capped by the shop staff.",
        "2026-09-18",
    ),
    (
        # Deliberately hazardous and restricted: the marketplace must show a route the
        # safety layer refuses, not only the easy ones.
        "lst_sup_009",
        "src_ind_07",
        1.5,
        30.0,
        {"needs_licensed_handler": True},
        "Board scrap and failed assemblies. Manifest and licensed transporter only.",
        "2026-09-19",
    ),
]


def demand_listing(listing_id, recipient_id, materials, quantity, distance, requirements, note, created):
    recipient = RECIPIENTS[recipient_id]
    accepted = set(recipient["accepted_materials"])
    unknown = [m for m in materials if m not in accepted]
    if unknown:
        raise SystemExit(f"{recipient_id} does not accept {unknown} - fix the generator, do not fix the data")
    low = float(recipient["min_quantity_t_per_month"])
    high = float(recipient["max_quantity_t_per_month"])
    clamped = round(min(max(quantity, low), high), 3)
    return {
        "id": listing_id,
        "kind": "demand",
        "party_id": recipient_id,
        "party_name": recipient["company_name"],
        "party_sector": recipient["sector"],
        "location": recipient["location"],
        "latitude": recipient["latitude"],
        "longitude": recipient["longitude"],
        "material_ids": list(materials),
        "quantity_t_per_month": clamped,
        "offer_price_inr_per_tonne": float(recipient["estimated_price_inr_per_tonne"]),
        "max_distance_km": distance,
        "requirements": requirements,
        "notes": note,
        "status": "open",
        "created_at": created,
        "origin": "seed",
        "quantity_window_t_per_month": [low, high],
        "processing_capability": list(recipient.get("processing_capability") or []),
    }


def supply_listing(listing_id, source_id, quantity, distance, requirements, note, created):
    source = SOURCES[source_id]
    material_id = source["material_hint"]
    material = get_material(material_id)
    return {
        "id": listing_id,
        "kind": "supply",
        "party_id": source_id,
        "party_name": source["name"],
        "party_sector": source["sector"],
        "location": source["location"],
        "latitude": source["latitude"],
        "longitude": source["longitude"],
        "material_ids": [material_id],
        "quantity_t_per_month": quantity,
        "asking_price_inr_per_tonne": float(material["typical_price_inr_per_tonne"]),
        "max_distance_km": distance,
        "requirements": requirements,
        "notes": note,
        "status": "open",
        "created_at": created,
        "origin": "seed",
        "description": source["description"],
        "material_safety_level": material["safety_level"],
        "material_reuse_type": material["default_reuse_type"],
    }


def build():
    listings = [demand_listing(*row) for row in DEMAND] + [supply_listing(*row) for row in SUPPLY]
    listings.sort(key=lambda row: (row["kind"], row["id"]))
    for row in listings:
        row["material_names"] = [MATERIALS_BY_ID[m]["name"] for m in row["material_ids"]]
    return {
        "_about": {
            "what": "The demo marketplace: demand listings (a partner that needs a material) and supply listings (a facility with a stream to place).",
            "status": "demo",
            "generated_by": "backend/data/generate_listings.py",
            "provenance_rules": [
                "Parties are the same fictional companies in data/recipients.json and data/sources.json; a listing never introduces a company the profiles do not know.",
                "A demand listing's offer price is that partner's own estimated_price_inr_per_tonne and its quantity sits inside its recorded min/max window.",
                "A supply listing offers the source's recorded material_hint at the knowledge base's typical price for it.",
                "Requirement notes, distance ceilings and tonnages are demo figures: no real buyer, tender or freight quote is represented here.",
            ],
            "persistence": "Served from this file plus anything published in the running process. See backend/services/listings.py and the note on POST /api/listings.",
            "shape_note": "Field names match the `listings` table in database/schema.sql, so the file can be swapped for a query without touching the models.",
        },
        "listings": listings,
    }


if __name__ == "__main__":
    payload = build()
    out = os.path.join(HERE, "listings.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {out}: {len(payload['listings'])} listings")
