"""Step 07 - generate data/canonical/README.md (dataset card) from the real tables, manifest and quality gates."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT, OUT_META  # noqa: E402

manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
q = json.loads((OUT_META / "quality_gates.json").read_text(encoding="utf-8"))
gr = json.loads((OUT_META / "grams_estimation_report.json").read_text(encoding="utf-8"))
files = {f["path"]: f for f in manifest["files"]}

TABLE_DOC = [
    ("recipes/recipe.parquet", "recipe_id", "One row per dinner-eligible Food.com recipe that passed every quality gate. "
     "Per-serving nutrition appears twice: `*_stated` (Food.com's own numbers) and `*_computed` (grams x USDA per 100 g)."),
    ("recipes/recipe_ingredient.parquet", "recipe_id + ingredient_id", "Recipe -> canonical ingredient with **estimated** "
     "grams per serving. `raw_text` keeps the original Food.com string."),
    ("recipes/recipe_step.parquet", "recipe_id", "Instruction steps (list of strings) - display only, never used for decisions."),
    ("interactions/interaction_train.parquet", "user_id + recipe_id + date", "Food.com ratings restricted to retained recipes; Food.com's own "
     "train split (frozen - do not re-split)."),
    ("interactions/interaction_validation.parquet", "user_id + recipe_id + date", "Validation split (frozen)."),
    ("interactions/interaction_test.parquet", "user_id + recipe_id + date", "Test split (frozen). Never tune on it."),
    ("ingredients/ingredient.parquet", "ingredient_id", "The canonical ingredient master: USDA match, food group, "
     "allergen/diet flags, frequency counts."),
    ("ingredients/ingredient_alias.parquet", "alias + ingredient_id", "Every spelling seen -> ingredient_id. This is what "
     "the NLP layer looks names up in."),
    ("ingredients/ingredient_unit_weight.parquet", "ingredient_id + unit + size", "Grams per cup / tbsp / tsp / each / "
     "slice ... for converting pantry text to grams."),
    ("nutrition/ingredient_nutrition_per100g.parquet", "ingredient_id", "USDA nutrients per 100 g for each canonical ingredient."),
    ("nutrition/usda_food_nutrient_per100g.parquet", "fdc_id", "All 13,694 non-branded USDA foods (SR Legacy, Foundation, "
     "FNDDS) with the planner's 15 nutrients - the pool a pantry item can be re-mapped from."),
    ("nutrition/usda_food_portion_weight.parquet", "fdc_id + unit + size + prep", "Cleaned household-unit weights for those USDA foods."),
    ("shelf_life/foodkeeper_product.parquet", "product_id", "USDA FoodKeeper product catalogue (data version 128)."),
    ("shelf_life/foodkeeper_shelf_life.parquet", "product_id + storage + state + basis", "FoodKeeper storage guidance flattened to days: product x storage x state x basis."),
    ("shelf_life/ingredient_shelf_life.parquet", "ingredient_id + storage + state + basis", "FoodKeeper joined to canonical ingredients with a confidence label "
     "and one `is_default` row per ingredient. **Estimates, never known use-by dates.**"),
    ("reference/ingredient_synonyms.csv", "name", "Curated: spelling/synonym -> canonical name (a `+` means split into two ingredients)."),
    ("reference/ingredient_usda_overrides.csv", "canonical_name", "Curated: canonical ingredient -> exact USDA description."),
    ("reference/ingredient_foodkeeper_overrides.csv", "canonical_name", "Curated: canonical ingredient -> FoodKeeper product id."),
    ("reference/unit_conversion.csv", "unit", "Physical unit constants (mass in g, volume in ml)."),
    ("reference/nutrient_daily_value.csv", "nutrient_column", "Daily values behind Food.com's %DV columns (calibrated)."),
    ("reference/nutrition_reference_ranges.csv", "nutrient + basis", "Published planning ranges (FDA DV, Dietary Guidelines AMDR) with sources."),
]

COL_DOC = {
    "recipe_id": "Food.com recipe id (stable across the dataset)", "name": "recipe title (whitespace-normalised)",
    "minutes_total": "total time in minutes (valid 5-1440)", "n_steps": "number of instruction steps",
    "n_ingredients": "number of food ingredients after canonicalisation (equipment such as skewers removed)",
    "cuisine": "primary cuisine tag, most specific first (null when untagged)", "tags": "curated subset of Food.com tags",
    "is_vegetarian": "derived from ingredients (not the Food.com tag); no meat/poultry/fish/shellfish/gelatin",
    "is_vegan": "vegetarian and no dairy/egg/honey", "contains_dairy": "any ingredient flagged dairy",
    "contains_egg": "any ingredient flagged egg", "contains_gluten": "any ingredient flagged gluten (wheat, barley, rye ...)",
    "contains_peanut": "peanut", "contains_tree_nut": "tree nut (coconut excluded)", "contains_soy": "soy",
    "contains_sesame": "sesame", "contains_fish": "fish incl. fish sauce / anchovy / Worcestershire",
    "contains_shellfish": "crustacean or mollusc", "contains_meat": "mammal meat incl. bacon/sausage",
    "contains_poultry": "poultry incl. chicken broth", "contains_pork": "pork products (halal/kosher use)",
    "contains_alcohol": "wine/beer/spirits/liqueur", "contains_honey": "honey", "contains_gelatin": "gelatin / marshmallow",
    "kcal_stated": "Food.com stated kcal per serving", "kcal_computed": "kcal per serving = sum(grams x USDA kcal per g)",
    "rating_mean_train": "mean rating over rated train interactions (leakage-safe)", "n_ratings_train": "count of those ratings",
    "total_grams_per_serving": "sum of estimated ingredient grams per serving (includes water)",
    "fit_kcal_rel_error": "abs(computed - stated) / stated kcal after the grams fit (quality gate <= 0.15)",
    "position": "order in the original ingredient list", "ingredient_id": "canonical ingredient id (project-assigned, stable per build)",
    "raw_text": "original Food.com ingredient string", "grams_per_serving": "estimated grams of this ingredient per serving",
    "grams_source": "`estimated` = fitted from Food.com nutrition + USDA per 100 g + priors; `parsed` reserved for measured quantities",
    "grams_basis": "`fitted` = ingredient carries >=5% of the recipe's kcal so the stated nutrition constrains it; `prior_default` = accent ingredient (herb, spice, aromatic) whose grams are a calibrated default",
    "kcal_share": "this ingredient's share of the recipe's computed kcal (0-1)",
    "steps": "list of instruction strings", "user_id": "Food.com user id", "rating": "1-5 stars; 0 = no rating",
    "date": "interaction date", "is_rated": "rating > 0",
    "canonical_name": "canonical ingredient name (lowercase)", "food_group": "coarse group: dairy, meat, vegetable, herb_spice ...",
    "fdc_id": "USDA FoodData Central id", "usda_description": "USDA food description matched",
    "usda_data_type": "sr_legacy | foundation | survey_fndds", "match_method": "curated | auto | none (shelf life: + category_fallback)",
    "match_score": "lexical match score (auto only)", "match_confidence": "1.0 curated; 0.85/0.75/0.55 auto tiers",
    "n_occurrences_foodcom": "mentions across all 231,637 Food.com recipes", "n_recipes_foodcom": "recipes mentioning it (Food.com)",
    "n_recipes_pool": "recipes in this dataset using it", "is_assumed_available": "water / salt / black pepper: assumed in every kitchen (configurable)",
    "alias": "normalised spelling", "alias_source": "foodcom_raw | foodcom_canonical | synonym | canonical",
    "n_occurrences": "times seen in Food.com", "is_split": "alias expands to more than one ingredient",
    "unit": "cup | tbsp | tsp | fl_oz | each | slice | clove | can ...", "size": "small | medium | large ... (for unit=each)",
    "grams_per_unit": "grams in one unit", "prep_basis": "preparation the weight refers to (e.g. chopped)",
    "source": "usda_portion | derived_volume | group_median (or provenance string for nutrition)",
    "basis": "per_100g (nutrition) / date_of_purchase | package_date | after_opening | after_thawing (shelf life)",
    "energy_kcal": "kcal per 100 g", "protein_g": "g per 100 g", "fat_g": "g per 100 g", "sat_fat_g": "g per 100 g",
    "carbohydrate_g": "g per 100 g", "sugars_g": "g per 100 g (total sugars)", "fiber_g": "g per 100 g",
    "sodium_mg": "mg per 100 g", "cholesterol_mg": "mg per 100 g", "calcium_mg": "mg per 100 g", "iron_mg": "mg per 100 g",
    "potassium_mg": "mg per 100 g", "vitamin_c_mg": "mg per 100 g", "vitamin_a_rae_ug": "ug RAE per 100 g", "water_g": "g per 100 g",
    "energy_source": "usda_energy | usda_atwater_general | computed_atwater_*", "qc_flag": "ok | no_energy | energy_out_of_range",
    "data_type": "sr_legacy | foundation | survey_fndds", "category": "USDA food category",
    "seq_num": "USDA portion sequence (1 = primary)", "amount": "quantity the label refers to", "gram_weight": "grams for `amount`",
    "label_raw": "original USDA portion text", "product_id": "FoodKeeper product id", "subtitle": "FoodKeeper name subtitle",
    "storage": "pantry | refrigerator | freezer", "state": "unopened | opened | thawed",
    "min_days": "FoodKeeper minimum shelf life in days (null if not numeric)", "max_days": "FoodKeeper maximum, days",
    "min_days_effective": "numeric usable minimum (see effective_source)", "max_days_effective": "numeric usable maximum",
    "effective_source": "foodkeeper | foodkeeper_tip | indefinite_cap (3650 d) | category_median | not_recommended",
    "is_indefinite": "FoodKeeper says indefinitely", "is_when_ripe": "ripening-dependent", "is_package_date_only": "follow the package date",
    "is_not_recommended": "storage method not recommended", "tips": "FoodKeeper storage tip", "is_default": "row the planner uses by default",
    "confidence": "high (curated product) | medium (lexical) | low (category fallback)", "foodkeeper_product_id": "linked FoodKeeper product",
    "metric_raw": "unit text in the source", "keywords": "FoodKeeper keywords",
}


def meaning(col):
    if col in COL_DOC:
        return COL_DOC[col]
    nice = col.replace("_stated", "").replace("_computed", "")
    if col.endswith("_stated"):
        return f"{nice} per serving as stated by Food.com (converted from %DV)"
    if col.endswith("_computed"):
        return f"{nice} per serving computed from estimated grams x USDA per 100 g"
    return ""


def dtype_of(rel, col):
    p = OUT / rel
    if p.suffix == ".parquet":
        import pyarrow.parquet as pq
        t = str(pq.read_schema(p).field(col).type)
        return t.replace('large_string', 'string').replace('list<element: string>', 'list<string>')
    return "text/number"


lines = []
A = lines.append
A("# Pantry-to-Plate - canonical dataset")
A("")
A(f"*Built {manifest['built_on']} by `src/knowledge/build/run_all.py`. Everything the application uses lives here; "
  "raw downloads under `data/` are inputs only and can be ignored or deleted after a build.*")
A("")
A("## At a glance")
A("")
A(f"- **{q['recipes']:,} dinner recipes** with per-serving ingredient grams and USDA-computed nutrition, "
  f"{q['ingredients_total']:,} canonical ingredients ({q['ingredients_used_by_pool']:,} used by those recipes), "
  f"{sum(q['interactions'].values()):,} ratings from {q['interaction_users_train']:,} users in frozen train/validation/test splits.")
A(f"- Sources: Food.com recipes & interactions (Kaggle `shuyangli94`), USDA FoodData Central (2026-04-30 CSV; SR Legacy, Foundation, FNDDS), "
  "USDA FoodKeeper (v128). Branded USDA foods and review text are deliberately excluded.")
A(f"- Size on disk: {sum(f['bytes'] for f in manifest['files'])/1e6:.0f} MB in {len(manifest['files'])} files (zstd Parquet + small CSVs).")
A("")
A("## Read this before using the data")
A("")
A("1. **Ingredient quantities are estimated.** Food.com publishes ingredient *names* only. Grams per serving come from a "
  "bounded least-squares fit of each recipe's stated nutrition against USDA per-100 g values, with per-ingredient priors and "
  "plausibility caps (`grams_source = estimated`). Treat them as plausible amounts, not measurements.")
A(f"   - Held-out check (nutrients *not* used in the fit): median absolute % error sat fat {gr['held_out_median_ape'].get('sat_fat_g_stated', float('nan')):.0%}, "
  f"sugars {gr['held_out_median_ape'].get('sugars_g_stated', float('nan')):.0%}, sodium {gr['held_out_median_ape'].get('sodium_mg_stated', float('nan')):.0%}.")
A("   - `kcal_computed` matches `kcal_stated` *by construction* (it was fitted); use the held-out figures above for honest accuracy.")
A("   - Only calorie-bearing ingredients are constrained by the data (`grams_basis = fitted`). Accents - fresh herbs, spices, "
  "garlic, citrus juice, condiments - carry too little nutrient signal, so their grams are calibrated defaults "
  "(`grams_basis = prior_default`): realistic, but identical across recipes.")
A("2. **Nutrition is per Food.com serving** and Food.com does not publish the number of servings. One planned dinner = one serving.")
A("3. **Missing USDA nutrient values are NaN**, and sums treat them as 0 (so micronutrients and fibre can be slightly low).")
A("4. **Diet/allergen flags are conservative keyword rules** over canonical ingredients (a false alarm costs a recipe; a miss "
  "costs a user's safety). They do not see hidden allergens inside branded products. Food.com's own tags are *not* trusted "
  "for diet/allergy (e.g. `dairy-free` appears on only 195 of 231K recipes).")
A("5. **Shelf life is an estimate** (FoodKeeper ranges with a confidence label), never a known use-by date.")
A("6. **Licence:** Food.com's reuse terms were not verified in this build; treat the recipe corpus as academic-use only until confirmed.")
A("")
A("## Folder layout and naming")
A("")
A("```")
A("data/canonical/")
A("  recipes/        recipe, recipe_ingredient, recipe_step")
A("  ingredients/    ingredient, ingredient_alias, ingredient_unit_weight")
A("  nutrition/      ingredient_nutrition_per100g, usda_food_nutrient_per100g, usda_food_portion_weight")
A("  shelf_life/     foodkeeper_product, foodkeeper_shelf_life, ingredient_shelf_life")
A("  interactions/   interaction_train | validation | test")
A("  reference/      small curated CSVs (inputs to the build, also used at run time)")
A("  _meta/          quality_gates.json, build reports, review lists (not needed at run time)")
A("  MANIFEST.json   file list with row counts and SHA-256")
A("```")
A("")
A("Conventions: `snake_case`; folder = domain, file = `<entity>[_<variant>]`; ids are `recipe_id` (Food.com), `ingredient_id` "
  "(project), `fdc_id` (USDA), `product_id` (FoodKeeper), `user_id` (Food.com). Units are in the column name "
  "(`_g`, `_mg`, `_kcal`, `_ug`, `_days`). `*_stated` = published by Food.com, `*_computed` = grams x USDA. "
  "`contains_*` / `is_*` are booleans. Parquet for tables, CSV only for small hand-editable references.")
A("")
A("## Tables")
for rel, key, desc in TABLE_DOC:
    f = files.get(rel)
    if f is None:
        continue
    A("")
    A(f"### `{rel}`  ({f['rows']:,} rows x {len(f['columns'])} cols)")
    A("")
    A(f"{desc}  Key: `{key}`.")
    A("")
    A("| column | type | meaning |")
    A("| --- | --- | --- |")
    for c in f["columns"]:
        A(f"| `{c}` | {dtype_of(rel, c)} | {meaning(c)} |")
A("")
A("## Quality gates (from docs/data.md)")
A("")
cons = q["nutrition_consistency"]
A("| gate | result |")
A("| --- | --- |")
A(f"| Ingredient mapping coverage (Food.com mentions mapped to USDA) | {q['foodcom_occurrence_coverage_mapped']:.1%} of "
  f"{q['foodcom_distinct_raw_strings']:,} distinct raw strings' occurrences; {q['foodcom_occurrence_share_curated']:.1%} via curated matches |")
A(f"| Recipes kept only if every ingredient mapped | 100% of the {q['recipes']:,} retained recipes |")
A(f"| Quantity -> grams | 100% estimated ({q['quantity_source']['estimated']:,} rows), 0% parsed - see caveat 1 |")
A(f"| Nutrition field coverage (pool ingredients) | " + ", ".join(f"{k} {v:.0%}" for k, v in q['nutrition_field_coverage_pool_ingredients'].items()) + " |")
A(f"| Shelf-life coverage (pool ingredients with a default row) | {q['shelf_life_default_coverage_pool_pct']}% ; by usage: "
  f"high {q['shelf_life_confidence_by_usage_pct']['high']}%, medium {q['shelf_life_confidence_by_usage_pct']['medium']}%, "
  f"low {q['shelf_life_confidence_by_usage_pct']['low']}% |")
A(f"| Nutrition consistency (computed vs stated, median abs error) | kcal {cons['kcal']['median_abs_err']}, protein {cons['protein_g']['median_abs_err']} g, "
  f"fat {cons['fat_g']['median_abs_err']} g, carbs {cons['carbohydrate_g']['median_abs_err']} g (fitted targets) |")
A(f"| Held-out nutrition error (median APE, not fitted) | " + ", ".join(f"{k.replace('_stated','')} {v:.0%}" for k, v in q['held_out_median_ape'].items()) + " |")
A("")
A("### Pool composition")
A("")
d = q["pool_diet"]
A(f"Vegetarian {d['vegetarian']:,} | vegan {d['vegan']:,} | pescatarian-compatible {d['pescatarian']:,} | gluten-free {d['gluten_free']:,} | "
  f"dairy-free {d['dairy_free']:,} | nut-free {d['nut_free']:,}. "
  f"Cooking time p10/p50/p90 = {int(q['pool_minutes_quantiles']['0.1'])}/{int(q['pool_minutes_quantiles']['0.5'])}/{int(q['pool_minutes_quantiles']['0.9'])} min; "
  f"kcal per serving p10/p50/p90 = {int(q['pool_kcal_quantiles']['0.1'])}/{int(q['pool_kcal_quantiles']['0.5'])}/{int(q['pool_kcal_quantiles']['0.9'])}.")
A("")
A("## Rebuild")
A("")
A("```bash")
A("python src/knowledge/build/run_all.py      # raw downloads -> data/canonical  (~6 min)")
A("```")
A("")
A("To improve ingredient matching, edit the three curated CSVs in `reference/` (a synonym, a forced USDA description, a "
  "FoodKeeper product id) and re-run. `_meta/review_unmapped_or_low_confidence.csv` lists the most frequent names still worth reviewing.")
A("")
A("## Load")
A("")
A("```python")
A("import pandas as pd")
A("recipe = pd.read_parquet('data/canonical/recipes/recipe.parquet')")
A("lines  = pd.read_parquet('data/canonical/recipes/recipe_ingredient.parquet')")
A("ing    = pd.read_parquet('data/canonical/ingredients/ingredient.parquet')")
A("```")
(OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote data/canonical/README.md", len(lines), "lines")
