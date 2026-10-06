"""
Material knowledge base for Symbio.

This is the source of truth for material facts: category, reuse applications,
compatible sectors, safety restrictions and environmental/economic factors.

DESIGN RULE: the LLM may *identify* a material and *suggest* reuse categories,
but every property, price, safety level and emission factor used downstream is
read from THIS file. The LLM can never introduce a new fact.

NOTE ON DATA PROVENANCE
-----------------------
All prices and CO2e factors below are DEMO / ESTIMATED values chosen so the
matching engine produces sensible, explainable numbers. They are NOT
scientifically certified figures. Replace `typical_price_inr_per_tonne` and
`co2e_avoided_t_per_tonne` with validated factors (e.g. from published LCA
databases) before any real-world use.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Vocabularies (kept as constants so the matching engine and the API stay in sync)
# ---------------------------------------------------------------------------

MATERIAL_CATEGORIES = [
    "coal_combustion_residue",
    "metallurgical_slag",
    "mineral_sludge",
    "construction_demolition",
    "organic_biomass",
    "paper_fibre",
    "polymer",
    "glass",
    "metal",
    "textile",
    "electronic",
    "chemical_process",
    "mixed_unknown",
]

REUSE_CATEGORIES = [
    "cement_supplementary_material",
    "brick_and_block_making",
    "aggregate_substitute",
    "road_and_embankment_fill",
    "soil_amendment",
    "compost_feedstock",
    "animal_feed",
    "energy_recovery",
    "fibre_pulping",
    "packaging_material",
    "polymer_reprocessing",
    "metal_recovery",
    "ceramic_and_tile_body",
    "glass_batch_cullet",
    "adsorbent_water_treatment",
    "fertiliser_raw_material",
    "panel_and_board_making",
    "textile_shoddy",
    "precious_metal_recovery",
]

SAFETY_LEVELS = ["low", "moderate", "high", "hazardous", "unknown"]

REUSE_TYPES = [
    "DIRECT_REUSE",
    "REQUIRES_PROCESSING",
    "INDUSTRIAL_ONLY",
    "RESTRICTED",
    "UNKNOWN",
]

SOURCE_SECTORS = ["industry", "household", "sme", "agriculture", "other"]

RECIPIENT_SECTORS = [
    "cement_manufacturing",
    "brick_manufacturing",
    "ceramic_tile_manufacturing",
    "glass_manufacturing",
    "construction_company",
    "ready_mix_concrete",
    "road_infrastructure",
    "fertiliser_company",
    "composting_facility",
    "biogas_plant",
    "agriculture_farm",
    "plastic_recycler",
    "paper_recycler",
    "packaging_company",
    "metal_recycler",
    "ewaste_processor",
    "furniture_manufacturer",
    "waste_processor",
    "community_programme",
    "artisan_sme",
    "energy_plant",
    "adsorbent_manufacturer",
]

# Sectors that may receive material for casual / non-industrial end use.
CASUAL_SECTORS = {"community_programme", "agriculture_farm", "artisan_sme"}

# Sectors that operate under industrial handling controls.
INDUSTRIAL_SECTORS = {
    "cement_manufacturing",
    "brick_manufacturing",
    "ceramic_tile_manufacturing",
    "glass_manufacturing",
    "construction_company",
    "ready_mix_concrete",
    "road_infrastructure",
    "fertiliser_company",
    "metal_recycler",
    "ewaste_processor",
    "waste_processor",
    "energy_plant",
    "adsorbent_manufacturer",
    "plastic_recycler",
    "paper_recycler",
}


# ---------------------------------------------------------------------------
# Material records
# ---------------------------------------------------------------------------
# Field notes:
#   reuse_categories      -> KB-sanctioned reuse applications (used for scoring)
#   compatible_sectors    -> which recipient sectors handle this material
#   safety_level          -> low / moderate / high / hazardous / unknown
#   requires_processing   -> default handling requirement
#   default_reuse_type    -> classification used when a recipient has no override
#   typical_price_inr_per_tonne   -> DEMO value
#   co2e_avoided_t_per_tonne      -> DEMO value (tonnes CO2e avoided per tonne reused)
#   keywords              -> used only by the deterministic fallback classifier

MATERIALS: list[dict[str, Any]] = [
    {
        "id": "fly_ash",
        "name": "Fly Ash",
        "category": "coal_combustion_residue",
        "aliases": ["pulverised fuel ash", "pfa", "class f ash", "class c ash"],
        "description": "Fine siliceous residue collected from flue gases of coal combustion.",
        "properties": ["pozzolanic", "fine_particle", "siliceous", "low_carbon"],
        "reuse_categories": [
            "cement_supplementary_material",
            "brick_and_block_making",
            "aggregate_substitute",
            "road_and_embankment_fill",
            "adsorbent_water_treatment",
            "ceramic_and_tile_body",
        ],
        "compatible_sectors": [
            "cement_manufacturing",
            "brick_manufacturing",
            "ready_mix_concrete",
            "construction_company",
            "road_infrastructure",
            "ceramic_tile_manufacturing",
            "waste_processor",
        ],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 1800.0,
        "co2e_avoided_t_per_tonne": 0.36,
        "keywords": [
            "fly ash", "flyash", "flue ash", "pfa", "pulverised fuel", "pulverized fuel",
            "sio2", "sio₂", "al2o3", "al₂o₃", "pozzolan", "pozzolanic", "thermal power",
            "coal ash", "combustion residue",
        ],
        "notes": "Widely used as a partial cement replacement. Not for household or food-contact use.",
    },
    {
        "id": "bottom_ash",
        "name": "Bottom Ash",
        "category": "coal_combustion_residue",
        "aliases": ["furnace ash", "boiler ash"],
        "description": "Coarser ash collected at the base of a combustion furnace.",
        "properties": ["granular", "abrasive", "inert"],
        "reuse_categories": ["aggregate_substitute", "road_and_embankment_fill", "brick_and_block_making"],
        "compatible_sectors": [
            "construction_company", "ready_mix_concrete", "road_infrastructure",
            "brick_manufacturing", "waste_processor",
        ],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 600.0,
        "co2e_avoided_t_per_tonne": 0.18,
        "keywords": ["bottom ash", "furnace ash", "boiler ash", "grit ash"],
        "notes": "Useful as lightweight aggregate or embankment fill after screening.",
    },
    {
        "id": "steel_slag",
        "name": "Steel Slag",
        "category": "metallurgical_slag",
        "aliases": ["bos slag", "eaf slag"],
        "description": "By-product of steel making, dense and highly durable.",
        "properties": ["high_density", "alkaline", "durable", "abrasive"],
        "reuse_categories": ["aggregate_substitute", "road_and_embankment_fill", "cement_supplementary_material"],
        "compatible_sectors": [
            "road_infrastructure", "construction_company", "ready_mix_concrete",
            "cement_manufacturing", "waste_processor",
        ],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 750.0,
        "co2e_avoided_t_per_tonne": 0.22,
        "keywords": ["steel slag", "bos slag", "eaf slag", "ld slag", "slag"],
        "notes": "Free-lime content requires weathering before use in bound layers.",
    },
    {
        "id": "copper_slag",
        "name": "Copper Slag",
        "category": "metallurgical_slag",
        "aliases": ["iron silicate slag"],
        "description": "Glassy granular residue from copper smelting.",
        "properties": ["glassy", "dense", "hard", "low_porosity"],
        "reuse_categories": ["aggregate_substitute", "road_and_embankment_fill"],
        "compatible_sectors": ["road_infrastructure", "construction_company", "ready_mix_concrete", "waste_processor"],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 900.0,
        "co2e_avoided_t_per_tonne": 0.20,
        "keywords": ["copper slag", "iron silicate", "smelter slag"],
        "notes": "Residual heavy metals must be leach-tested before any use near soil or water.",
    },
    {
        "id": "aluminium_dross",
        "name": "Aluminium Dross",
        "category": "metallurgical_slag",
        "aliases": ["black dross", "white dross", "salt cake"],
        "description": "Oxide-rich skimmings from aluminium melting.",
        "properties": ["reactive", "residual_metal", "saline"],
        "reuse_categories": ["metal_recovery", "aggregate_substitute"],
        "compatible_sectors": ["metal_recycler", "waste_processor", "cement_manufacturing"],
        "safety_level": "high",
        "requires_processing": True,
        "default_reuse_type": "INDUSTRIAL_ONLY",
        "typical_price_inr_per_tonne": 6500.0,
        "co2e_avoided_t_per_tonne": 0.55,
        "keywords": ["dross", "aluminium dross", "aluminum dross", "salt cake", "skimming"],
        "notes": "Can react with water releasing ammonia and hydrogen. Industrial handling only.",
    },
    {
        "id": "foundry_sand",
        "name": "Foundry Sand",
        "category": "metallurgical_slag",
        "aliases": ["moulding sand", "spent foundry sand"],
        "description": "Silica sand spent from metal casting moulds.",
        "properties": ["siliceous", "uniform_grain", "thermally_stressed"],
        "reuse_categories": [
            "aggregate_substitute",
            "brick_and_block_making",
            "road_and_embankment_fill",
            "ceramic_and_tile_body",
        ],
        "compatible_sectors": [
            "brick_manufacturing", "construction_company", "road_infrastructure",
            "ready_mix_concrete", "ceramic_tile_manufacturing", "waste_processor",
        ],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 500.0,
        "co2e_avoided_t_per_tonne": 0.12,
        "keywords": ["foundry sand", "moulding sand", "molding sand", "spent sand"],
        "notes": "Requires screening and leach testing before reuse.",
    },
    {
        "id": "marble_slurry",
        "name": "Marble Slurry",
        "category": "mineral_sludge",
        "aliases": ["stone slurry", "cutting sludge"],
        "description": "Calcium-carbonate-rich slurry from stone cutting and polishing.",
        "properties": ["fine_particle", "calcareous", "high_moisture"],
        "reuse_categories": ["brick_and_block_making", "cement_supplementary_material", "soil_amendment", "ceramic_and_tile_body"],
        "compatible_sectors": [
            "brick_manufacturing", "cement_manufacturing", "ceramic_tile_manufacturing",
            "agriculture_farm", "waste_processor",
        ],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 400.0,
        "co2e_avoided_t_per_tonne": 0.10,
        "keywords": ["marble slurry", "stone slurry", "cutting sludge", "marble waste", "granite slurry"],
        "notes": "Needs dewatering/drying. High pH makes it a liming agent candidate.",
    },
    {
        "id": "lime_sludge",
        "name": "Lime Sludge",
        "category": "mineral_sludge",
        "aliases": ["calcium carbonate sludge", "paper mill sludge"],
        "description": "Calcium carbonate sludge from causticising in paper mills.",
        "properties": ["calcareous", "alkaline", "fine_particle"],
        "reuse_categories": ["cement_supplementary_material", "soil_amendment", "brick_and_block_making"],
        "compatible_sectors": ["cement_manufacturing", "agriculture_farm", "brick_manufacturing", "waste_processor"],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 450.0,
        "co2e_avoided_t_per_tonne": 0.11,
        "keywords": ["lime sludge", "lime mud", "calcium carbonate sludge", "causticising"],
        "notes": "Alkaline; pH must be checked before agricultural application.",
    },
    {
        "id": "gypsum_waste",
        "name": "Gypsum Waste",
        "category": "construction_demolition",
        "aliases": ["plasterboard waste", "drywall waste"],
        "description": "Calcium sulfate material from demolition and board offcuts.",
        "properties": ["calcium_sulfate", "moisture_sensitive"],
        "reuse_categories": ["cement_supplementary_material", "soil_amendment", "brick_and_block_making"],
        "compatible_sectors": ["cement_manufacturing", "agriculture_farm", "waste_processor", "brick_manufacturing"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 1100.0,
        "co2e_avoided_t_per_tonne": 0.15,
        "keywords": ["gypsum", "plasterboard", "drywall", "plaster of paris waste"],
        "notes": "Must be kept dry and separated from biodegradable waste to avoid hydrogen sulfide.",
    },
    {
        "id": "phosphogypsum",
        "name": "Phosphogypsum",
        "category": "chemical_process",
        "aliases": ["pg stack material"],
        "description": "Calcium sulfate by-product of phosphoric acid production.",
        "properties": ["calcium_sulfate", "acidic", "trace_contaminants"],
        "reuse_categories": ["cement_supplementary_material", "soil_amendment"],
        "compatible_sectors": ["cement_manufacturing", "waste_processor", "fertiliser_company"],
        "safety_level": "high",
        "requires_processing": True,
        "default_reuse_type": "INDUSTRIAL_ONLY",
        "typical_price_inr_per_tonne": 700.0,
        "co2e_avoided_t_per_tonne": 0.13,
        "keywords": ["phosphogypsum", "phospho gypsum", "phosphoric acid residue"],
        "notes": "Naturally occurring radionuclides require radiological screening before reuse.",
    },
    {
        "id": "spent_catalyst",
        "name": "Spent Catalyst",
        "category": "chemical_process",
        "aliases": ["spent hydroprocessing catalyst", "fcc catalyst"],
        "description": "Deactivated refinery or petrochemical catalyst, often metal-bearing.",
        "properties": ["metal_bearing", "pyrophoric_risk", "high_value_residue"],
        "reuse_categories": ["metal_recovery"],
        "compatible_sectors": ["metal_recycler", "waste_processor"],
        "safety_level": "hazardous",
        "requires_processing": True,
        "default_reuse_type": "RESTRICTED",
        "typical_price_inr_per_tonne": 45000.0,
        "co2e_avoided_t_per_tonne": 0.80,
        "keywords": [
            "spent catalyst", "catalyst", "catalyst waste", "fcc catalyst",
            "hydroprocessing", "hydrotreating", "refinery residue",
        ],
        "notes": "Hazardous stream. Authorised recycler only. Never offered to households or farms.",
    },
    {
        "id": "bagasse_ash",
        "name": "Bagasse Ash",
        "category": "organic_biomass",
        "aliases": ["sugarcane bagasse ash", "cane ash"],
        "description": "Silica-rich ash from burning sugarcane bagasse.",
        "properties": ["siliceous", "pozzolanic", "agricultural_origin"],
        "reuse_categories": ["cement_supplementary_material", "brick_and_block_making", "soil_amendment"],
        "compatible_sectors": ["cement_manufacturing", "brick_manufacturing", "agriculture_farm", "ceramic_tile_manufacturing"],
        "safety_level": "low",
        "requires_processing": False,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 800.0,
        "co2e_avoided_t_per_tonne": 0.14,
        "keywords": ["bagasse ash", "cane ash", "sugarcane ash", "bagasse"],
        "notes": "Good pozzolan where grinding is available.",
    },
    {
        "id": "rice_husk_ash",
        "name": "Rice Husk Ash",
        "category": "organic_biomass",
        "aliases": ["rha"],
        "description": "High-silica ash from controlled rice husk combustion.",
        "properties": ["high_silica", "pozzolanic", "very_fine"],
        "reuse_categories": ["cement_supplementary_material", "adsorbent_water_treatment", "ceramic_and_tile_body"],
        "compatible_sectors": ["cement_manufacturing", "adsorbent_manufacturer", "ceramic_tile_manufacturing", "agriculture_farm"],
        "safety_level": "low",
        "requires_processing": False,
        "default_reuse_type": "DIRECT_REUSE",
        "typical_price_inr_per_tonne": 3500.0,
        "co2e_avoided_t_per_tonne": 0.28,
        "keywords": ["rice husk ash", "rha", "husk ash", "paddy husk"],
        "notes": "High reactive silica when burnt under controlled conditions.",
    },
    {
        "id": "food_processing_waste",
        "name": "Food Processing Waste",
        "category": "organic_biomass",
        "aliases": ["food waste", "kitchen waste", "organic refuse"],
        "description": "Biodegradable residues from food handling and processing.",
        "properties": ["biodegradable", "high_moisture", "putrescible"],
        "reuse_categories": ["compost_feedstock", "energy_recovery", "animal_feed"],
        "compatible_sectors": ["composting_facility", "biogas_plant", "agriculture_farm", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 500.0,
        "co2e_avoided_t_per_tonne": 0.45,
        "keywords": ["food waste", "kitchen waste", "organic waste", "vegetable waste", "canteen waste", "spoilage"],
        "notes": "Requires composting or digestion. Do not feed raw to animals without treatment.",
    },
    {
        "id": "green_waste",
        "name": "Garden / Green Waste",
        "category": "organic_biomass",
        "aliases": ["yard waste", "horticultural waste"],
        "description": "Leaves, trimmings and other horticultural residues.",
        "properties": ["biodegradable", "fibrous"],
        "reuse_categories": ["compost_feedstock", "energy_recovery", "soil_amendment"],
        "compatible_sectors": ["composting_facility", "biogas_plant", "agriculture_farm", "community_programme"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 300.0,
        "co2e_avoided_t_per_tonne": 0.30,
        "keywords": ["garden waste", "green waste", "leaves", "trimmings", "yard waste", "park waste"],
        "notes": "Good compost bulking material.",
    },
    {
        "id": "sawdust",
        "name": "Sawdust",
        "category": "organic_biomass",
        "aliases": ["wood shavings", "wood dust"],
        "description": "Fine wood particles from sawing and machining.",
        "properties": ["cellulosic", "combustible", "low_bulk_density"],
        "reuse_categories": ["panel_and_board_making", "energy_recovery", "animal_feed"],
        "compatible_sectors": ["furniture_manufacturer", "energy_plant", "artisan_sme", "composting_facility", "waste_processor"],
        "safety_level": "low",
        "requires_processing": False,
        "default_reuse_type": "DIRECT_REUSE",
        "typical_price_inr_per_tonne": 1500.0,
        "co2e_avoided_t_per_tonne": 0.25,
        "keywords": ["sawdust", "wood shavings", "wood dust", "wood chips", "wood offcut"],
        "notes": "Treated or painted wood must be segregated before panel or fuel use.",
    },
    {
        "id": "wood_waste",
        "name": "Wood Waste",
        "category": "organic_biomass",
        "aliases": ["timber waste", "pallet wood"],
        "description": "Offcuts, pallets and demolition timber.",
        "properties": ["cellulosic", "bulky"],
        "reuse_categories": ["panel_and_board_making", "energy_recovery"],
        "compatible_sectors": ["furniture_manufacturer", "energy_plant", "artisan_sme", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 2200.0,
        "co2e_avoided_t_per_tonne": 0.27,
        "keywords": ["wood waste", "timber", "pallet", "plywood offcut", "wood"],
        "notes": "Check for coatings, preservatives and nails before reprocessing.",
    },
    {
        "id": "cardboard",
        "name": "Cardboard / OCC",
        "category": "paper_fibre",
        "aliases": ["corrugated cardboard", "occ", "cartons"],
        "description": "Corrugated boxes and packaging board.",
        "properties": ["cellulosic_fibre", "recyclable", "dry"],
        "reuse_categories": ["fibre_pulping", "packaging_material"],
        "compatible_sectors": ["paper_recycler", "packaging_company", "waste_processor", "community_programme"],
        "safety_level": "low",
        "requires_processing": False,
        "default_reuse_type": "DIRECT_REUSE",
        "typical_price_inr_per_tonne": 9000.0,
        "co2e_avoided_t_per_tonne": 0.90,
        "keywords": ["cardboard", "carton", "corrugated", "occ", "boxes", "packaging board"],
        "notes": "Must be dry and free of food contamination for pulping.",
    },
    {
        "id": "paper_waste",
        "name": "Mixed Paper Waste",
        "category": "paper_fibre",
        "aliases": ["office paper", "newsprint", "mixed paper"],
        "description": "Office, newsprint and mixed grade paper.",
        "properties": ["cellulosic_fibre", "recyclable"],
        "reuse_categories": ["fibre_pulping", "packaging_material"],
        "compatible_sectors": ["paper_recycler", "packaging_company", "waste_processor", "community_programme"],
        "safety_level": "low",
        "requires_processing": False,
        "default_reuse_type": "DIRECT_REUSE",
        "typical_price_inr_per_tonne": 11000.0,
        "co2e_avoided_t_per_tonne": 0.95,
        "keywords": ["paper", "newsprint", "office paper", "newspaper", "magazines"],
        "notes": "Grades must be sorted; thermal paper should be excluded.",
    },
    {
        "id": "plastic_pet",
        "name": "PET Plastic Waste",
        "category": "polymer",
        "aliases": ["pet bottles", "polyester waste"],
        "description": "Polyethylene terephthalate bottles and sheet.",
        "properties": ["thermoplastic", "recyclable", "food_grade_possible"],
        "reuse_categories": ["polymer_reprocessing", "packaging_material", "textile_shoddy"],
        "compatible_sectors": ["plastic_recycler", "packaging_company", "artisan_sme", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 22000.0,
        "co2e_avoided_t_per_tonne": 1.20,
        "keywords": ["pet", "plastic bottle", "polyester", "plastic bottles", "pet bottle"],
        "notes": "Requires washing, sorting by colour and flaking.",
    },
    {
        "id": "plastic_mixed",
        "name": "Mixed Plastic Waste",
        "category": "polymer",
        "aliases": ["mixed polyolefin", "plastic film"],
        "description": "Unsorted plastic film, wrappers and containers.",
        "properties": ["thermoplastic", "contaminated", "mixed_polymers"],
        "reuse_categories": ["polymer_reprocessing", "energy_recovery", "road_and_embankment_fill"],
        "compatible_sectors": ["plastic_recycler", "road_infrastructure", "energy_plant", "waste_processor"],
        "safety_level": "moderate",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 8000.0,
        "co2e_avoided_t_per_tonne": 0.85,
        "keywords": ["mixed plastic", "plastic film", "polythene", "poly bags", "plastic waste"],
        "notes": "PVC must be removed. Sorting is the main cost driver.",
    },
    {
        "id": "textile_waste",
        "name": "Textile Waste",
        "category": "textile",
        "aliases": ["fabric offcuts", "garment waste", "cotton waste"],
        "description": "Offcuts, seconds and post-consumer textiles.",
        "properties": ["fibrous", "mixed_fibre"],
        "reuse_categories": ["textile_shoddy", "packaging_material", "panel_and_board_making"],
        "compatible_sectors": ["artisan_sme", "packaging_company", "furniture_manufacturer", "community_programme", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 12000.0,
        "co2e_avoided_t_per_tonne": 1.60,
        "keywords": ["textile", "fabric", "garment", "cloth", "cotton waste", "yarn waste", "apparel"],
        "notes": "Fibre content drives the route: shoddy, insulation or wiping cloth.",
    },
    {
        "id": "glass_waste",
        "name": "Glass Waste / Cullet",
        "category": "glass",
        "aliases": ["cullet", "broken glass"],
        "description": "Container and flat glass cullet.",
        "properties": ["inert", "recyclable", "abrasive"],
        "reuse_categories": ["glass_batch_cullet", "aggregate_substitute", "ceramic_and_tile_body"],
        "compatible_sectors": ["glass_manufacturing", "ceramic_tile_manufacturing", "construction_company", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 3000.0,
        "co2e_avoided_t_per_tonne": 0.31,
        "keywords": ["glass", "cullet", "bottles glass", "broken glass", "glass waste"],
        "notes": "Colour sorting and contaminant removal determine furnace acceptance.",
    },
    {
        "id": "concrete_waste",
        "name": "Concrete Waste",
        "category": "construction_demolition",
        "aliases": ["crushed concrete", "rcc waste", "demolition concrete"],
        "description": "Demolished concrete and mortar fragments.",
        "properties": ["granular", "inert", "alkaline"],
        "reuse_categories": ["aggregate_substitute", "road_and_embankment_fill", "cement_supplementary_material"],
        "compatible_sectors": ["construction_company", "ready_mix_concrete", "road_infrastructure", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 650.0,
        "co2e_avoided_t_per_tonne": 0.12,
        "keywords": ["concrete", "rcc", "demolition", "masonry rubble", "debris", "cd waste"],
        "notes": "Crushing and sizing produces recycled concrete aggregate (RCA).",
    },
    {
        "id": "brick_waste",
        "name": "Brick & Masonry Waste",
        "category": "construction_demolition",
        "aliases": ["brick bats", "rubble"],
        "description": "Broken bricks, tiles and masonry rubble.",
        "properties": ["granular", "porous", "inert"],
        "reuse_categories": ["aggregate_substitute", "road_and_embankment_fill", "brick_and_block_making"],
        "compatible_sectors": ["construction_company", "road_infrastructure", "brick_manufacturing", "waste_processor"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 500.0,
        "co2e_avoided_t_per_tonne": 0.10,
        "keywords": ["brick", "masonry", "rubble", "brick bats", "tile waste"],
        "notes": "Common low-value fill; crushing opens aggregate routes.",
    },
    {
        "id": "metal_scrap",
        "name": "Metal Scrap",
        "category": "metal",
        "aliases": ["ferrous scrap", "non-ferrous scrap", "turnings"],
        "description": "Ferrous and non-ferrous metal residues and end-of-life parts.",
        "properties": ["high_value", "recyclable", "dense"],
        "reuse_categories": ["metal_recovery"],
        "compatible_sectors": ["metal_recycler", "waste_processor", "artisan_sme"],
        "safety_level": "low",
        "requires_processing": True,
        "default_reuse_type": "REQUIRES_PROCESSING",
        "typical_price_inr_per_tonne": 26000.0,
        "co2e_avoided_t_per_tonne": 1.50,
        "keywords": ["scrap", "metal", "steel scrap", "iron", "aluminium scrap", "copper", "turnings", "swarf"],
        "notes": "Segregation by alloy greatly increases recovered value.",
    },
    {
        "id": "ewaste",
        "name": "E-Waste",
        "category": "electronic",
        "aliases": ["weee", "discarded electronics", "pcb waste"],
        "description": "Discarded electronics, boards, cables and appliances.",
        "properties": ["metal_bearing", "hazardous_components", "high_value_residue"],
        "reuse_categories": ["precious_metal_recovery", "metal_recovery"],
        "compatible_sectors": ["ewaste_processor", "metal_recycler", "waste_processor"],
        "safety_level": "hazardous",
        "requires_processing": True,
        "default_reuse_type": "INDUSTRIAL_ONLY",
        "typical_price_inr_per_tonne": 60000.0,
        "co2e_avoided_t_per_tonne": 2.50,
        "keywords": ["e-waste", "ewaste", "pcb", "circuit board", "electronics", "laptop", "cable", "weee", "mobile"],
        "notes": "Contains batteries and flame retardants. Authorised recycler only.",
    },
    {
        "id": "unknown_material",
        "name": "Unidentified Material",
        "category": "mixed_unknown",
        "aliases": [],
        "description": "Input could not be confidently matched to a known material.",
        "properties": ["unknown"],
        "reuse_categories": [],
        "compatible_sectors": ["waste_processor"],
        "safety_level": "unknown",
        "requires_processing": True,
        "default_reuse_type": "UNKNOWN",
        "typical_price_inr_per_tonne": 0.0,
        "co2e_avoided_t_per_tonne": 0.0,
        "keywords": [],
        "notes": "Assume unknown risk. Only route to a licensed waste processor for assessment.",
    },
]

MATERIALS_BY_ID: dict[str, dict[str, Any]] = {m["id"]: m for m in MATERIALS}

UNKNOWN_MATERIAL_ID = "unknown_material"


def get_material(material_id: str | None) -> dict[str, Any]:
    """Look up a material record; fall back to the unknown material."""
    if material_id and material_id in MATERIALS_BY_ID:
        return MATERIALS_BY_ID[material_id]
    return MATERIALS_BY_ID[UNKNOWN_MATERIAL_ID]


def all_materials() -> list[dict[str, Any]]:
    return list(MATERIALS)


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------

def primary_reuse_category(material_id: str) -> str | None:
    """The canonical destination for a material - the first recorded reuse route.

    The order of `reuse_categories` in the records above is deliberate: the
    first entry is the route the material is best known for (fly ash -> cement
    supplementary material, cardboard -> fibre pulping, and so on). The matching
    engine uses it to reward recipients who are actually after that route.
    """
    mat = MATERIALS_BY_ID.get(material_id or "")
    if not mat or not mat["reuse_categories"]:
        return None
    return mat["reuse_categories"][0]


def price_ceiling_inr() -> float:
    """90th percentile of recorded material prices - normalises the value score."""
    prices = sorted(m["typical_price_inr_per_tonne"] for m in MATERIALS if m["id"] != UNKNOWN_MATERIAL_ID)
    if not prices:
        return 1.0
    return prices[max(0, int(len(prices) * 0.9) - 1)]


def co2e_ceiling_t_per_tonne() -> float:
    """90th percentile of recorded avoidance factors - normalises the env score."""
    factors = sorted(m["co2e_avoided_t_per_tonne"] for m in MATERIALS if m["id"] != UNKNOWN_MATERIAL_ID)
    if not factors:
        return 1.0
    return factors[max(0, int(len(factors) * 0.9) - 1)]
