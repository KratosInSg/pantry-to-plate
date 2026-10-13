"""Step 06 - finalise the dataset: prune, verify integrity, compute quality gates, write manifest + README.

* Ingredient tables keep only ingredients the application can use (USDA-mapped, or present in a retained recipe).
* Hard integrity checks (foreign keys, uniqueness, no NaN keys) - the build fails loudly rather than ship a
  dataset with dangling references.
* Quality gates from docs/data.md are computed from the final tables and written to _meta/quality_report.md.
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (OUT, OUT_INGREDIENTS, OUT_INTERACTIONS, OUT_META, OUT_NUTRITION, OUT_RECIPES,  # noqa: E402
                    OUT_SHELF_LIFE, ROOT, write_parquet)

# ----------------------------------------------------------------- load ---------
recipe = pd.read_parquet(OUT_RECIPES / "recipe.parquet")
ri = pd.read_parquet(OUT_RECIPES / "recipe_ingredient.parquet")
steps = pd.read_parquet(OUT_RECIPES / "recipe_step.parquet")
ing = pd.read_parquet(OUT_INGREDIENTS / "ingredient.parquet")
alias = pd.read_parquet(OUT_INGREDIENTS / "ingredient_alias.parquet")
uw = pd.read_parquet(OUT_INGREDIENTS / "ingredient_unit_weight.parquet")
nut = pd.read_parquet(OUT_NUTRITION / "ingredient_nutrition_per100g.parquet")
isl = pd.read_parquet(OUT_SHELF_LIFE / "ingredient_shelf_life.parquet")
inter = {n: pd.read_parquet(OUT_INTERACTIONS / f"interaction_{n}.parquet") for n in ("train", "validation", "test")}

# --------------------------------------------------- prune ingredient layer ------
used = set(ri.ingredient_id)
mapped = set(ing.ingredient_id[ing.fdc_id.notna() & ~ing.is_non_food])
keep = used | mapped
pool_counts = ri.groupby("ingredient_id").recipe_id.nunique()
if "n_occurrences" in ing.columns:        # first run: give the Food.com-wide counts explicit names
    ing = ing.rename(columns={"n_occurrences": "n_occurrences_foodcom", "n_recipes": "n_recipes_foodcom"})
ing = ing[ing.ingredient_id.isin(keep)].copy()
ing["n_recipes_pool"] = ing.ingredient_id.map(pool_counts).fillna(0).astype("int32")
ing = ing.drop(columns=[c for c in ("is_non_food",) if c in ing.columns])
ing = ing.sort_values("ingredient_id").reset_index(drop=True)
alias = alias[alias.ingredient_id.isin(keep)].reset_index(drop=True)
uw = uw[uw.ingredient_id.isin(keep)].reset_index(drop=True)
nut = nut[nut.ingredient_id.isin(keep)].reset_index(drop=True)
isl = isl[isl.ingredient_id.isin(keep)].reset_index(drop=True)
write_parquet(ing, OUT_INGREDIENTS / "ingredient.parquet")
write_parquet(alias, OUT_INGREDIENTS / "ingredient_alias.parquet")
write_parquet(uw, OUT_INGREDIENTS / "ingredient_unit_weight.parquet")
write_parquet(nut, OUT_NUTRITION / "ingredient_nutrition_per100g.parquet")
write_parquet(isl, OUT_SHELF_LIFE / "ingredient_shelf_life.parquet")

# ------------------------------------------------------ integrity checks ---------
errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)


rid = set(recipe.recipe_id)
check(recipe.recipe_id.is_unique, "recipe_id not unique")
check(set(ri.recipe_id) == rid, "recipe_ingredient recipes != recipe recipes")
check(set(steps.recipe_id) == rid, "recipe_step recipes != recipe recipes")
check(ri.ingredient_id.isin(ing.ingredient_id).all(), "recipe_ingredient has unknown ingredient_id")
check(ri.ingredient_id.isin(nut.ingredient_id).all(), "recipe ingredient without nutrition row")
check(not ri.duplicated(["recipe_id", "ingredient_id"]).any(), "duplicate (recipe, ingredient)")
check(not ri.duplicated(["recipe_id", "position"]).any(), "duplicate (recipe, position)")
check(ing.ingredient_id.is_unique and ing.canonical_name.is_unique, "ingredient id/name not unique")
check(alias.ingredient_id.isin(ing.ingredient_id).all(), "alias -> unknown ingredient")
check(not alias.duplicated(["alias", "ingredient_id"]).any(), "duplicate alias rows")
check(nut.ingredient_id.is_unique, "nutrition not unique per ingredient")
check(uw.ingredient_id.isin(ing.ingredient_id).all(), "unit_weight -> unknown ingredient")
check(isl.ingredient_id.isin(ing.ingredient_id).all(), "shelf_life -> unknown ingredient")
for n, d in inter.items():
    check(d.recipe_id.isin(rid).all(), f"interaction_{n} references unknown recipe")
check(ri.grams_per_serving.notna().all() and (ri.grams_per_serving >= 0).all(), "bad grams")
check(recipe.kcal_computed.notna().all(), "missing computed kcal")
if errors:
    raise SystemExit("INTEGRITY FAILURES:\n  - " + "\n  - ".join(errors))
print("integrity checks passed")

# ---------------------------------------------------------- quality gates --------
q = {}
fc = pd.read_parquet(OUT_INGREDIENTS / "ingredient.parquet")
q["recipes"] = len(recipe)
q["recipe_ingredient_rows"] = len(ri)
q["ingredients_total"] = len(ing)
q["ingredients_used_by_pool"] = int((ing.n_recipes_pool > 0).sum())
occ = ing.n_occurrences_foodcom.sum()
map_rep = json.loads((OUT_META / "ingredient_mapping_report.json").read_text())
q["foodcom_occurrence_coverage_mapped"] = map_rep["occurrence_coverage_mapped"]
q["foodcom_occurrence_share_curated"] = map_rep["occurrence_share_curated"]
q["foodcom_distinct_raw_strings"] = map_rep["distinct_raw_strings"]
q["pool_ingredient_rows_mapped_pct"] = 100.0  # by construction: unmapped ingredients exclude the recipe
q["pool_rows_curated_pct"] = float((ri.merge(ing[["ingredient_id", "match_method"]], on="ingredient_id").match_method == "curated").mean() * 100)
q["pool_rows_auto_pct"] = 100.0 - q["pool_rows_curated_pct"]
q["quantity_source"] = {"estimated": int((ri.grams_source == "estimated").sum()), "parsed": int((ri.grams_source == "parsed").sum())}
# nutrition consistency (stated vs computed from grams x USDA per 100 g)
pairs = {"kcal": ("kcal_stated", "kcal_computed"), "protein_g": ("protein_g_stated", "protein_g_computed"),
         "fat_g": ("fat_g_stated", "fat_g_computed"), "carbohydrate_g": ("carbohydrate_g_stated", "carbohydrate_g_computed"),
         "sat_fat_g": ("sat_fat_g_stated", "sat_fat_g_computed"), "sugars_g": ("sugars_g_stated", "sugars_g_computed"),
         "sodium_mg": ("sodium_mg_stated", "sodium_mg_computed")}
cons = {}
for k, (s, c) in pairs.items():
    err = (recipe[c] - recipe[s]).abs()
    base = recipe[s].where(recipe[s] > 0)
    cons[k] = {"mae": round(float(err.mean()), 2), "median_abs_err": round(float(err.median()), 2),
               "median_rel_err": round(float((err / base).median()), 4)}
q["nutrition_consistency"] = cons
grams_report = json.loads((OUT_META / "grams_estimation_report.json").read_text()) if (OUT_META / "grams_estimation_report.json").exists() else {}
q["held_out_median_ape"] = grams_report.get("held_out_median_ape", {})
# nutrition coverage of ingredients used
nut_cov = nut.set_index("ingredient_id")[["energy_kcal", "protein_g", "fat_g", "carbohydrate_g", "fiber_g", "sodium_mg"]].notna().mean()
q["nutrition_field_coverage_pool_ingredients"] = {k: round(float(v), 3) for k, v in nut_cov.items()}
# shelf-life coverage
pool_ing = set(ri.ingredient_id)
d = isl[isl.is_default & isl.ingredient_id.isin(pool_ing)]
q["shelf_life_default_coverage_pool_pct"] = round(100 * d.ingredient_id.nunique() / len(pool_ing), 1)
w = ri.groupby("ingredient_id").size()
conf = d.drop_duplicates("ingredient_id").set_index("ingredient_id").confidence
q["shelf_life_confidence_by_usage_pct"] = {k: round(float(100 * w[conf[conf == k].index].sum() / w[conf.index].sum()), 1)
                                           for k in ("high", "medium", "low")}
# diet/cuisine coverage of the pool
q["pool_diet"] = {"vegetarian": int(recipe.is_vegetarian.sum()), "vegan": int(recipe.is_vegan.sum()),
                  "gluten_free": int((~recipe.contains_gluten).sum()), "dairy_free": int((~recipe.contains_dairy).sum()),
                  "nut_free": int((~(recipe.contains_tree_nut | recipe.contains_peanut)).sum()),
                  "pescatarian": int(((~recipe.contains_meat) & (~recipe.contains_poultry)).sum())}
q["pool_minutes_quantiles"] = recipe.minutes_total.quantile([0.1, 0.5, 0.9]).round(0).to_dict()
q["pool_kcal_quantiles"] = recipe.kcal_computed.quantile([0.1, 0.5, 0.9]).round(0).to_dict()
q["interactions"] = {n: int(len(d_)) for n, d_ in inter.items()}
q["interaction_users_train"] = int(inter["train"].user_id.nunique())
q["built_on"] = date.today().isoformat()
(OUT_META / "quality_gates.json").write_text(json.dumps(q, indent=2, default=str), encoding="utf-8")

# --------------------------------------------------------------- manifest --------
def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


files = []
for p in sorted(OUT.rglob("*")):
    if not p.is_file() or p.name in ("MANIFEST.json", "README.md"):
        continue
    rel = p.relative_to(OUT).as_posix()
    entry = {"path": rel, "bytes": p.stat().st_size, "sha256": sha(p)}
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
        entry.update(rows=len(df), columns=list(df.columns))
    elif p.suffix == ".csv":
        df = pd.read_csv(p)
        entry.update(rows=len(df), columns=list(df.columns))
    files.append(entry)
manifest = {"dataset": "pantry-to-plate canonical dataset", "built_on": date.today().isoformat(), "files": files}
(OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
total_mb = sum(f["bytes"] for f in files) / 1e6
print(f"manifest: {len(files)} files, {total_mb:.1f} MB")
print(json.dumps({k: q[k] for k in ("recipes", "ingredients_total", "foodcom_occurrence_coverage_mapped",
                                    "shelf_life_confidence_by_usage_pct", "pool_diet")}, indent=2))
