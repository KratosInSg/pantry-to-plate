"""Paths and shared constants for the data build.

Raw inputs stay untouched under data/. Everything the application uses is written
to data/canonical/ (the "main dataset"). Each build step is a standalone script,
run in numeric order from the project root:

    python src/knowledge/build/01_usda_nutrition.py
    python src/knowledge/build/02_canonical_ingredients.py
    ...
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# --- raw inputs (read-only) -------------------------------------------------
RAW_FDC = ROOT / "data" / "FoodData_Central_csv_2026-04-30"
RAW_RECIPES = ROOT / "data" / "recipes"
RAW_FOODKEEPER = ROOT / "data" / "foodkeeper"

# --- curated dataset (everything downstream reads from here) ----------------
OUT = ROOT / "data" / "canonical"
OUT_INGREDIENTS = OUT / "ingredients"
OUT_NUTRITION = OUT / "nutrition"
OUT_RECIPES = OUT / "recipes"
OUT_INTERACTIONS = OUT / "interactions"
OUT_SHELF_LIFE = OUT / "shelf_life"
OUT_REFERENCE = OUT / "reference"
OUT_META = OUT / "_meta"

# --- USDA nutrient ids -> output column names (all values are per 100 g) -----
NUTRIENT_COLUMNS = {
    1003: "protein_g",
    1004: "fat_g",
    1258: "sat_fat_g",
    1005: "carbohydrate_g",
    2000: "sugars_g",        # "Total Sugars" (SR Legacy / FNDDS)
    1063: "sugars_g",        # "Sugars, Total" (NLEA) - fallback
    1079: "fiber_g",
    1093: "sodium_mg",
    1253: "cholesterol_mg",
    1087: "calcium_mg",
    1089: "iron_mg",
    1092: "potassium_mg",
    1162: "vitamin_c_mg",
    1106: "vitamin_a_rae_ug",
    1051: "water_g",
}
# Energy has three possible sources; resolved in this priority order.
ENERGY_IDS_PRIORITY = [1008, 2047, 2048]

# Atwater factors used only as the last-resort energy fallback (kcal per g).
ATWATER = {"protein_g": 4.0, "carbohydrate_g": 4.0, "fat_g": 9.0}

NUTRIENT_OUTPUT_ORDER = [
    "energy_kcal", "protein_g", "fat_g", "sat_fat_g", "carbohydrate_g", "sugars_g",
    "fiber_g", "sodium_mg", "cholesterol_mg", "calcium_mg", "iron_mg",
    "potassium_mg", "vitamin_c_mg", "vitamin_a_rae_ug", "water_g",
]

CORE_DATA_TYPES = ["sr_legacy_food", "foundation_food", "survey_fndds_food"]


def write_parquet(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")
    print(f"wrote {path.relative_to(ROOT)}  rows={len(df):,} cols={df.shape[1]}")
