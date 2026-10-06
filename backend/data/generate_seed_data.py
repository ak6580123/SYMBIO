"""One-off generator for backend/data/*.json (demo seed data).

Run from the backend directory:  python data/generate_seed_data.py
The generated JSON files are what the application actually loads.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# (lat, lng) anchors for the Chennai / Tamil Nadu demo area
LOC = {
    "Manali": (13.1667, 80.2667),
    "Korukkupet": (13.1140, 80.2830),
    "Perambur": (13.1067, 80.2341),
    "Ambattur": (13.0947, 80.1622),
    "Padi": (13.0969, 80.1881),
    "Avadi": (13.1067, 80.1000),
    "Guindy": (13.0067, 80.2206),
    "Velachery": (12.9789, 80.2209),
    "Thiruvanmiyur": (12.9840, 80.2560),
    "Perungudi": (12.9714, 80.2414),
    "Taramani": (12.9860, 80.2430),
    "Adyar": (13.0010, 80.2560),
    "Chromepet": (12.9516, 80.1440),
    "Tambaram": (12.9249, 80.1000),
    "Pallavaram": (12.9673, 80.1490),
    "Porur": (13.0361, 80.1561),
    "Sriperumbudur": (12.9680, 79.9460),
    "Kanchipuram": (12.8352, 79.7036),
    "Ennore": (13.1601, 80.3100),
    "Kattupalli": (13.2500, 80.3200),
    "Minjur": (13.2800, 80.2700),
    "Red Hills": (13.1940, 80.1800),
    "Thiruvottiyur": (13.1582, 80.3014),
    "Royapuram": (13.1083, 80.2900),
    "Madhavaram": (13.1482, 80.2305),
    "Poonamallee": (13.0459, 80.0949),
    "Oragadam": (12.7900, 79.9500),
    "Maraimalai Nagar": (12.7900, 80.0100),
    "Chengalpattu": (12.6878, 79.9800),
    "Tindivanam": (12.2410, 79.6530),
    "Vellore": (12.9165, 79.1325),
    "Ranipet": (12.9300, 79.3400),
    "Anna Nagar": (13.0850, 80.2101),
    "Nungambakkam": (13.0604, 80.2496),
    "Mylapore": (13.0336, 80.2706),
    "T. Nagar": (13.0418, 80.2341),
    "Besant Nagar": (13.0000, 80.2650),
    "Sholinganallur": (12.9000, 80.2300),
    "Perungalathur": (12.9140, 80.0980),
    "Gummidipoondi": (13.4100, 80.1300),
}


def r(rid, name, sector, place, accepted, mn, mx, cap, price, reuse, safety, note=""):
    lat, lng = LOC[place]
    return {
        "id": rid,
        "company_name": name,
        "sector": sector,
        "location": f"{place}, Chennai region",
        "latitude": lat,
        "longitude": lng,
        "accepted_materials": accepted,
        "accepted_categories": [],
        "min_quantity_t_per_month": mn,
        "max_quantity_t_per_month": mx,
        "processing_capability": cap,
        "estimated_price_inr_per_tonne": price,
        "reuse_type": reuse,
        "safety_level": safety,
        "notes": note,
    }


# accepted_categories lets a recipient take a whole family of streams
RECIPIENTS = [
    r("rec_cement_01", "Coromandel Cement Materials", "cement_manufacturing", "Red Hills",
      ["fly_ash", "bottom_ash", "steel_slag", "bagasse_ash", "rice_husk_ash", "lime_sludge", "marble_slurry", "gypsum_waste", "phosphogypsum", "concrete_waste"],
      3, 120, ["drying", "grinding", "silos", "bulk_logistics"], 1950, "REQUIRES_PROCESSING", "moderate",
      "Buys pozzolanic residues as cement replacement. Demo buyer."),
    r("rec_cement_02", "Southern Blended Cements", "cement_manufacturing", "Kanchipuram",
      ["fly_ash", "bottom_ash", "steel_slag", "copper_slag"],
      10, 250, ["grinding", "blending", "rail_sidings"], 1850, "REQUIRES_PROCESSING", "moderate",
      "Large-volume blended cement grinding unit. Demo buyer."),
    r("rec_cement_03", "Deccan Pozzolana Works", "cement_manufacturing", "Vellore",
      ["fly_ash", "rice_husk_ash", "bagasse_ash"],
      5, 80, ["grinding", "quality_lab"], 2000, "REQUIRES_PROCESSING", "moderate",
      "Specialises in high-silica supplementary materials. Demo buyer."),

    r("rec_brick_01", "Padi Interlock Bricks", "brick_manufacturing", "Padi",
      ["fly_ash", "foundry_sand", "bottom_ash", "marble_slurry", "brick_waste", "concrete_waste", "lime_sludge"],
      2, 40, ["mixing", "curing_yard", "block_press"], 1300, "REQUIRES_PROCESSING", "moderate",
      "Fly-ash brick and paver block line. Demo buyer."),
    r("rec_brick_02", "Ambattur Fly Ash Blocks", "brick_manufacturing", "Ambattur",
      ["fly_ash", "bottom_ash", "marble_slurry", "foundry_sand"],
      1, 25, ["block_press", "steam_curing"], 1450, "REQUIRES_PROCESSING", "moderate",
      "Small-block producer, accepts partial loads. Demo buyer."),
    r("rec_brick_03", "Gummidipoondi Clay & Ash Bricks", "brick_manufacturing", "Gummidipoondi",
      ["fly_ash", "brick_waste", "foundry_sand", "bottom_ash"],
      5, 60, ["kiln", "mixing", "yard_storage"], 1100, "REQUIRES_PROCESSING", "moderate",
      "Kiln-based producer blending ash into clay. Demo buyer."),

    r("rec_rmc_01", "Chennai Ready-Mix Concrete", "ready_mix_concrete", "Guindy",
      ["fly_ash", "concrete_waste", "steel_slag", "copper_slag"],
      4, 60, ["batching_plant", "silos", "lab_testing"], 1750, "REQUIRES_PROCESSING", "moderate",
      "Uses fly ash in blended mixes. Demo buyer."),
    r("rec_rmc_02", "Tambaram Aggregates & RMC", "ready_mix_concrete", "Tambaram",
      ["concrete_waste", "brick_waste", "fly_ash", "copper_slag"],
      6, 90, ["crushing", "screening", "batching"], 900, "REQUIRES_PROCESSING", "low",
      "Runs its own crushing line for recycled aggregate. Demo buyer."),

    r("rec_constr_01", "Marina Infrastructure Projects", "construction_company", "Perungudi",
      ["concrete_waste", "brick_waste", "steel_slag", "bottom_ash", "foundry_sand"],
      10, 400, ["earthworks", "haulage", "compaction"], 550, "REQUIRES_PROCESSING", "low",
      "Takes inert fill for site works. Demo buyer."),
    r("rec_constr_02", "Pallavaram Site Services", "construction_company", "Pallavaram",
      ["concrete_waste", "brick_waste", "gypsum_waste"],
      3, 60, ["haulage", "site_clearance"], 480, "REQUIRES_PROCESSING", "low",
      "Small contractor, flexible volumes. Demo buyer."),

    r("rec_road_01", "Tamil Nadu Road Materials Unit", "road_infrastructure", "Chromepet",
      ["steel_slag", "copper_slag", "bottom_ash", "foundry_sand", "plastic_mixed", "concrete_waste"],
      20, 800, ["grading", "mixing_plant", "laying"], 700, "REQUIRES_PROCESSING", "moderate",
      "Uses slag and plastic-modified mixes in pavement layers. Demo buyer."),
    r("rec_road_02", "Sriperumbudur Highway Aggregates", "road_infrastructure", "Sriperumbudur",
      ["concrete_waste", "brick_waste", "bottom_ash", "steel_slag"],
      15, 500, ["crushing", "screening", "haulage"], 600, "REQUIRES_PROCESSING", "low",
      "Sub-base and embankment supplier. Demo buyer."),

    r("rec_fert_01", "Delta Bio-Fertilisers", "fertiliser_company", "Chengalpattu",
      ["phosphogypsum", "gypsum_waste", "lime_sludge", "food_processing_waste"],
      8, 150, ["granulation", "blending", "lab_testing"], 900, "REQUIRES_PROCESSING", "high",
      "Industrial handling only; tests for contaminants before use. Demo buyer."),
    r("rec_fert_02", "Kaveri Organics", "fertiliser_company", "Tindivanam",
      ["food_processing_waste", "green_waste", "lime_sludge", "marble_slurry"],
      5, 100, ["composting", "screening", "bagging"], 700, "REQUIRES_PROCESSING", "moderate",
      "Organic input supplier for farms. Demo buyer."),

    r("rec_compost_01", "Perungudi Compost Yard", "composting_facility", "Perungudi",
      ["food_processing_waste", "green_waste", "sawdust"],
      2, 50, ["windrow_composting", "turning", "screening"], 400, "REQUIRES_PROCESSING", "low",
      "City-scale composting. Demo buyer."),
    r("rec_compost_02", "GreenLoop Compost Co.", "composting_facility", "Madhavaram",
      ["food_processing_waste", "green_waste", "textile_waste", "sawdust"],
      1, 30, ["windrow_composting", "in_vessel"], 450, "REQUIRES_PROCESSING", "low",
      "Takes mixed organics from bulk generators. Demo buyer."),

    r("rec_biogas_01", "Anna Nagar Biogas Plant", "biogas_plant", "Anna Nagar",
      ["food_processing_waste", "green_waste"],
      3, 40, ["anaerobic_digestion", "gas_storage"], 600, "REQUIRES_PROCESSING", "low",
      "Digestion plant feeding a captive generator. Demo buyer."),

    r("rec_plastic_01", "RePolymer Recyclers", "plastic_recycler", "Ambattur",
      ["plastic_pet", "plastic_mixed"],
      1, 45, ["washing", "sorting", "flaking", "pelletising"], 20000, "REQUIRES_PROCESSING", "moderate",
      "PET and polyolefin line. Demo buyer."),
    r("rec_plastic_02", "Chennai Polymer Reprocessing", "plastic_recycler", "Poonamallee",
      ["plastic_pet", "plastic_mixed", "textile_waste"],
      4, 120, ["washing", "extrusion", "pelletising"], 18500, "REQUIRES_PROCESSING", "moderate",
      "High-volume pellet producer. Demo buyer."),

    r("rec_paper_01", "Tamil Fibre & Paper Mills", "paper_recycler", "Royapuram",
      ["cardboard", "paper_waste"],
      3, 200, ["pulping", "de-inking", "baling"], 9200, "DIRECT_REUSE", "low",
      "Takes baled OCC and mixed paper. Demo buyer."),
    r("rec_paper_02", "EcoPack Board Mills", "paper_recycler", "Thiruvottiyur",
      ["cardboard", "paper_waste", "sawdust"],
      1, 60, ["pulping", "board_forming"], 8600, "DIRECT_REUSE", "low",
      "Board-grade producer. Demo buyer."),

    r("rec_pack_01", "CirclePack Solutions", "packaging_company", "Padi",
      ["cardboard", "paper_waste", "plastic_pet"],
      1, 35, ["converting", "die_cutting"], 8000, "DIRECT_REUSE", "low",
      "Buys clean board for packaging conversion. Demo buyer."),
    r("rec_pack_02", "GreenWrap Packaging", "packaging_company", "Porur",
      ["cardboard", "paper_waste", "textile_waste"],
      0.5, 20, ["converting", "shredding"], 7600, "DIRECT_REUSE", "low",
      "Small-batch converter, flexible minimums. Demo buyer."),

    r("rec_metal_01", "Chennai Metal Reclamation", "metal_recycler", "Korukkupet",
      ["metal_scrap", "aluminium_dross", "ewaste", "spent_catalyst"],
      0.5, 300, ["shredding", "magnetic_separation", "melting", "licensed_handling"], 27000,
      "REQUIRES_PROCESSING", "high",
      "Licensed for hazardous and metal-bearing streams. Demo buyer."),
    r("rec_metal_02", "Coromandel Alloy Recovery", "metal_recycler", "Ennore",
      ["metal_scrap", "aluminium_dross", "spent_catalyst"],
      2, 200, ["melting", "refining", "licensed_handling"], 25500, "INDUSTRIAL_ONLY", "high",
      "Secondary smelter. Industrial inputs only. Demo buyer."),

    r("rec_ewaste_01", "E-Cycle Recovery Hub", "ewaste_processor", "Ambattur",
      ["ewaste", "spent_catalyst"],
      0.2, 40, ["dismantling", "separation", "licensed_handling"], 58000, "INDUSTRIAL_ONLY", "hazardous",
      "Authorised e-waste recycler. Demo buyer."),

    r("rec_furn_01", "Timber Craft Furniture", "furniture_manufacturer", "Padi",
      ["sawdust", "wood_waste", "textile_waste"],
      0.5, 25, ["drying", "panel_press", "upholstery"], 2100, "REQUIRES_PROCESSING", "low",
      "Uses offcuts and board feedstock. Demo buyer."),
    r("rec_furn_02", "Chennai Panel & Board Co.", "furniture_manufacturer", "Sriperumbudur",
      ["sawdust", "wood_waste", "textile_waste"],
      5, 150, ["drying", "resin_mixing", "panel_press"], 2400, "REQUIRES_PROCESSING", "low",
      "Particle board producer. Demo buyer."),

    r("rec_glass_01", "Coromandel Glass Works", "glass_manufacturing", "Kattupalli",
      ["glass_waste"],
      5, 300, ["colour_sorting", "furnace", "batching"], 3100, "REQUIRES_PROCESSING", "low",
      "Container glass furnace taking sorted cullet. Demo buyer."),

    r("rec_ceramic_01", "Kanchipuram Ceramics", "ceramic_tile_manufacturing", "Kanchipuram",
      ["marble_slurry", "glass_waste", "rice_husk_ash", "fly_ash", "foundry_sand"],
      2, 70, ["milling", "kiln", "slip_preparation"], 1200, "REQUIRES_PROCESSING", "low",
      "Uses mineral sludges in tile bodies. Demo buyer."),

    r("rec_adsorb_01", "AquaSorb Materials", "adsorbent_manufacturer", "Oragadam",
      ["rice_husk_ash", "fly_ash", "sawdust"],
      1, 30, ["activation", "grinding", "quality_lab"], 3800, "REQUIRES_PROCESSING", "moderate",
      "Makes activated adsorbents for water treatment. Demo buyer."),

    r("rec_energy_01", "Maraimalai Biomass Energy", "energy_plant", "Maraimalai Nagar",
      ["sawdust", "wood_waste", "green_waste", "plastic_mixed", "food_processing_waste"],
      8, 400, ["boiler", "shredding", "emission_controls"], 1600, "REQUIRES_PROCESSING", "moderate",
      "Co-fires biomass with emission controls. Demo buyer."),

    r("rec_wp_01", "Chennai Circular Waste Hub", "waste_processor", "Perungalathur",
      ["concrete_waste", "brick_waste", "plastic_mixed", "cardboard", "paper_waste", "glass_waste",
       "textile_waste", "metal_scrap", "ewaste", "sawdust", "food_processing_waste", "green_waste"],
      0.5, 500, ["sorting", "baling", "shredding", "transfer_station"], 1200, "REQUIRES_PROCESSING", "moderate",
      "Multi-stream aggregation and pre-processing. Demo buyer."),
    r("rec_wp_02", "Tiruvottiyur Resource Recovery", "waste_processor", "Thiruvottiyur",
      ["foundry_sand", "bottom_ash", "copper_slag", "aluminium_dross", "phosphogypsum", "gypsum_waste", "concrete_waste"],
      2, 250, ["leach_testing", "stabilisation", "licensed_handling"], 950, "INDUSTRIAL_ONLY", "high",
      "Handles industrial residues under licence. Demo buyer."),

    r("rec_farm_01", "Sri Balaji Farms", "agriculture_farm", "Minjur",
      ["food_processing_waste", "green_waste", "rice_husk_ash", "marble_slurry"],
      1, 25, ["field_application", "composting_pit"], 350, "REQUIRES_PROCESSING", "low",
      "Applies composted organics to field crops. Demo buyer."),
    r("rec_farm_02", "Puzhal Horticulture Collective", "agriculture_farm", "Red Hills",
      ["green_waste", "food_processing_waste", "sawdust"],
      0.5, 15, ["composting_pit", "mulching"], 300, "REQUIRES_PROCESSING", "low",
      "Smallholder collective near Red Hills. Demo buyer."),

    r("rec_sme_01", "Velachery Artisan Collective", "artisan_sme", "Velachery",
      ["textile_waste", "sawdust", "cardboard", "glass_waste"],
      0.2, 8, ["hand_sorting", "upcycling", "small_batch"], 4200, "REQUIRES_PROCESSING", "low",
      "Makes upcycled goods in small batches. Demo buyer."),
    r("rec_sme_02", "Adyar Eco Products", "artisan_sme", "Adyar",
      ["paper_waste", "cardboard", "textile_waste", "plastic_pet"],
      0.2, 6, ["hand_sorting", "upcycling"], 3600, "DIRECT_REUSE", "low",
      "Stationery and crafts from clean dry waste. Demo buyer."),

    r("rec_comm_01", "Mylapore Zero-Waste Neighbourhood", "community_programme", "Mylapore",
      ["cardboard", "paper_waste", "green_waste", "food_processing_waste"],
      0.1, 5, ["segregation", "community_composting"], 200, "DIRECT_REUSE", "low",
      "Neighbourhood segregation and composting group. Demo buyer."),
    r("rec_comm_02", "Besant Nagar Recycling Collective", "community_programme", "Besant Nagar",
      ["cardboard", "paper_waste", "plastic_pet", "glass_waste"],
      0.1, 4, ["segregation", "baling"], 250, "DIRECT_REUSE", "low",
      "Collects and bales clean dry recyclables. Demo buyer."),
]

SOURCES = [
    {
        "id": "src_ind_01",
        "name": "Thermal Power Station - Unit 3 (Demo facility)",
        "sector": "industry",
        "location": "Manali, Chennai",
        "latitude": 13.1667, "longitude": 80.2667,
        "material_hint": "fly_ash",
        "description": "Pulverised coal boiler flue gas residue collected from electrostatic precipitators.",
    },
    {
        "id": "src_ind_02",
        "name": "Coromandel Steel Rolling Mill (Demo facility)",
        "sector": "industry",
        "location": "Ennore, Chennai",
        "latitude": 13.1601, "longitude": 80.3100,
        "material_hint": "steel_slag",
        "description": "Slag from electric arc furnace steel making.",
    },
    {
        "id": "src_ind_03",
        "name": "Kattupalli Aluminium Castings (Demo facility)",
        "sector": "industry",
        "location": "Kattupalli, Chennai",
        "latitude": 13.2500, "longitude": 80.3200,
        "material_hint": "aluminium_dross",
        "description": "Dross skimmed from aluminium melting furnaces.",
    },
    {
        "id": "src_ind_04",
        "name": "Ambattur Metal Castings Foundry (Demo facility)",
        "sector": "industry",
        "location": "Ambattur, Chennai",
        "latitude": 13.0947, "longitude": 80.1622,
        "material_hint": "foundry_sand",
        "description": "Spent moulding sand from iron casting operations.",
    },
    {
        "id": "src_ind_05",
        "name": "Chengalpattu Stone Processing Park (Demo facility)",
        "sector": "industry",
        "location": "Chengalpattu, Chennai",
        "latitude": 12.6878, "longitude": 79.9800,
        "material_hint": "marble_slurry",
        "description": "Wet slurry from granite and marble cutting lines.",
    },
    {
        "id": "src_ind_06",
        "name": "Poonamallee Paper Mill (Demo facility)",
        "sector": "industry",
        "location": "Poonamallee, Chennai",
        "latitude": 13.0459, "longitude": 80.0949,
        "material_hint": "lime_sludge",
        "description": "Calcium carbonate sludge from the causticising plant.",
    },
    {
        "id": "src_ind_07",
        "name": "Tambaram Electronics Assembly (Demo facility)",
        "sector": "industry",
        "location": "Tambaram, Chennai",
        "latitude": 12.9249, "longitude": 80.1000,
        "material_hint": "ewaste",
        "description": "Rejected boards, cables and assemblies from the assembly line.",
    },
    {
        "id": "src_sme_01",
        "name": "Perambur Woodworking Unit (Demo SME)",
        "sector": "sme",
        "location": "Perambur, Chennai",
        "latitude": 13.1067, "longitude": 80.2341,
        "material_hint": "sawdust",
        "description": "Sawdust and offcuts from a small furniture workshop.",
    },
    {
        "id": "src_sme_02",
        "name": "Guindy Garment Unit (Demo SME)",
        "sector": "sme",
        "location": "Guindy, Chennai",
        "latitude": 13.0067, "longitude": 80.2206,
        "material_hint": "textile_waste",
        "description": "Fabric offcuts and rejected garments.",
    },
    {
        "id": "src_sme_03",
        "name": "Chromepet Food Products (Demo SME)",
        "sector": "sme",
        "location": "Chromepet, Chennai",
        "latitude": 12.9516, "longitude": 80.1440,
        "material_hint": "food_processing_waste",
        "description": "Peel, pulp and spoilage from a fruit processing line.",
    },
    {
        "id": "src_house_01",
        "name": "Anna Nagar Apartment Complex (Demo household)",
        "sector": "household",
        "location": "Anna Nagar, Chennai",
        "latitude": 13.0850, "longitude": 80.2101,
        "material_hint": "cardboard",
        "description": "Segregated packaging waste from 240 households.",
    },
    {
        "id": "src_house_02",
        "name": "T. Nagar Retail Street (Demo household/community)",
        "sector": "household",
        "location": "T. Nagar, Chennai",
        "latitude": 13.0418, "longitude": 80.2341,
        "material_hint": "plastic_pet",
        "description": "Beverage bottles collected from street bins.",
    },
    {
        "id": "src_house_03",
        "name": "Nungambakkam Housing Society (Demo household)",
        "sector": "household",
        "location": "Nungambakkam, Chennai",
        "latitude": 13.0604, "longitude": 80.2496,
        "material_hint": "green_waste",
        "description": "Garden trimmings and kitchen organics.",
    },
    {
        "id": "src_agri_01",
        "name": "Red Hills Paddy Cluster (Demo agriculture)",
        "sector": "agriculture",
        "location": "Red Hills, Chennai",
        "latitude": 13.1940, "longitude": 80.1800,
        "material_hint": "rice_husk_ash",
        "description": "Husk ash from cluster-level rice milling.",
    },
    {
        "id": "src_agri_02",
        "name": "Minjur Vegetable Farms (Demo agriculture)",
        "sector": "agriculture",
        "location": "Minjur, Chennai",
        "latitude": 13.2800, "longitude": 80.2700,
        "material_hint": "green_waste",
        "description": "Crop residues and unsold produce.",
    },
]


def main() -> None:
    # `accepted_categories` is derived from the material knowledge base: a
    # recipient that lists "fly_ash" implicitly accepts the whole
    # coal_combustion_residue family (at a lower score than an exact match).
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
    from knowledge_base.materials import MATERIALS_BY_ID  # noqa: E402

    for recipient in RECIPIENTS:
        cats = {
            MATERIALS_BY_ID[m]["category"]
            for m in recipient["accepted_materials"]
            if m in MATERIALS_BY_ID
        }
        recipient["accepted_categories"] = sorted(cats)

    with open(os.path.join(HERE, "recipients.json"), "w", encoding="utf-8") as fh:
        json.dump(RECIPIENTS, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(HERE, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(SOURCES, fh, indent=2, ensure_ascii=False)
    print(f"wrote {len(RECIPIENTS)} recipients and {len(SOURCES)} sources")


if __name__ == "__main__":
    main()
