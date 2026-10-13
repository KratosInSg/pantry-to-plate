"""Step 05 - USDA FoodKeeper -> structured shelf-life tables joined to canonical ingredients.

FoodKeeper (FSIS, data version 128) gives storage guidance per product as (min, max, unit) for
pantry / refrigerator / freezer, unopened / opened / thawed. We flatten that to days and keep the
provenance and a confidence label for every ingredient link:

    high   - curated link to a specific FoodKeeper product (reference/ingredient_foodkeeper_overrides.csv)
    medium - lexical match to a FoodKeeper product name
    low    - fallback: median of the FoodKeeper category the ingredient's food group belongs to

Per the project's design rule these are *estimates*, never known use-by dates.

Outputs (data/canonical/shelf_life/):
  foodkeeper_product.parquet        FoodKeeper product catalogue (661 products)
  foodkeeper_shelf_life.parquet     tidy long table: product x storage x state x basis -> min/max days
  ingredient_shelf_life.parquet     the same, joined to canonical ingredient_id with confidence + a default row
"""
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT_INGREDIENTS, OUT_META, OUT_RECIPES, OUT_REFERENCE, OUT_SHELF_LIFE, RAW_FOODKEEPER, write_parquet  # noqa: E402
from matcher import UsdaIndex  # noqa: E402

doc = json.load(open(RAW_FOODKEEPER / "foodkeeper.json", encoding="utf-8"))
sheets = {s["name"]: pd.DataFrame([{k: v for c in row for k, v in c.items()} for row in s["data"]]) for s in doc["sheets"]}
print("FoodKeeper source file:", doc.get("fileName"))
cat = sheets["Category"].rename(columns={"ID": "Category_ID"})
prod = sheets["Product"].merge(cat, on="Category_ID", how="left")
prod["ID"] = prod.ID.astype(int)

product = pd.DataFrame({
    "product_id": prod.ID, "name": prod.Name.str.strip(), "subtitle": prod.Name_subtitle,
    "category": prod.Category_Name, "subcategory": prod.Subcategory_Name, "keywords": prod.Keywords})
product["subtitle"] = product.subtitle.where(product.subtitle.notna(), None)
write_parquet(product, OUT_SHELF_LIFE / "foodkeeper_product.parquet")

# ---------------------------------------------------------------- tidy shelf-life ----
UNIT_DAYS = {"days": 1, "day": 1, "weeks": 7, "week": 7, "months": 30, "month": 30, "years": 365, "year": 365}
# (column prefix, storage, state, basis, tips column)
SPEC = [("Pantry", "pantry", "unopened", "package_date", "Pantry_tips"),
        ("DOP_Pantry", "pantry", "unopened", "date_of_purchase", "DOP_Pantry_tips"),
        ("Pantry_After_Opening", "pantry", "opened", "after_opening", None),
        ("Refrigerate", "refrigerator", "unopened", "package_date", "Refrigerate_tips"),
        ("DOP_Refrigerate", "refrigerator", "unopened", "date_of_purchase", "DOP_Refrigerate_tips"),
        ("Refrigerate_After_Opening", "refrigerator", "opened", "after_opening", None),
        ("Refrigerate_After_Thawing", "refrigerator", "thawed", "after_thawing", None),
        ("Freeze", "freezer", "unopened", "package_date", "Freeze_Tips"),
        ("DOP_Freeze", "freezer", "unopened", "date_of_purchase", "DOP_Freeze_Tips")]
TIP_DAYS = re.compile(r"then\s+(\d+)(?:\s*(?:-|to)\s*(\d+))?\s*(day|week|month)s?", re.I)
rows = []
for _, r in prod.iterrows():
    for prefix, storage, state, basis, tips_col in SPEC:
        mn, mx, metric = r.get(f"{prefix}_Min"), r.get(f"{prefix}_Max"), r.get(f"{prefix}_Metric")
        if pd.isna(metric) and pd.isna(mn) and pd.isna(mx):
            continue
        m = str(metric).strip().lower() if pd.notna(metric) else ""
        k = UNIT_DAYS.get(m)
        indefinite = m == "indefinitely"
        when_ripe = m == "when ripe"
        not_rec = m == "not recommended"
        pkg_date = m == "package use-by date"
        lo = float(mn) * k if (k and pd.notna(mn)) else np.nan
        hi = float(mx) * k if (k and pd.notna(mx)) else (lo if k and pd.notna(mn) else np.nan)
        if np.isnan(lo) and not (indefinite or when_ripe or not_rec or pkg_date):
            continue
        tips = r.get(tips_col) if tips_col else None
        tips = tips if isinstance(tips, str) else None
        # "When Ripe" rows often carry the number in the tip text ("Until ripe, then 7 days")
        tip_lo = tip_hi = np.nan
        if when_ripe and tips:
            mt = TIP_DAYS.search(tips)
            if mt:
                unit = {"day": 1, "week": 7, "month": 30}[mt.group(3).lower()]
                tip_lo = float(mt.group(1)) * unit
                tip_hi = float(mt.group(2) or mt.group(1)) * unit
        rows.append({"product_id": int(r.ID), "storage": storage, "state": state, "basis": basis,
                     "min_days": lo, "max_days": hi, "is_indefinite": indefinite, "is_when_ripe": when_ripe,
                     "is_not_recommended": not_rec, "is_package_date_only": pkg_date,
                     "tip_min_days": tip_lo, "tip_max_days": tip_hi,
                     "metric_raw": metric if pd.notna(metric) else None, "tips": tips})
sl = pd.DataFrame(rows).merge(product[["product_id", "category"]], on="product_id", how="left")

# category medians over the numeric FoodKeeper rows: used for package-date-only rows and ingredient fallbacks
num = sl[sl.min_days.notna()]
med_cat = (num.groupby(["category", "storage", "state"]).agg(cat_min=("min_days", "median"), cat_max=("max_days", "median"))
           .reset_index())
sl = sl.merge(med_cat, on=["category", "storage", "state"], how="left")
INDEFINITE_CAP = 3650.0
eff_min, eff_max, eff_src = [], [], []
for r in sl.itertuples():
    if not np.isnan(r.min_days):
        eff_min.append(r.min_days); eff_max.append(r.max_days); eff_src.append("foodkeeper")
    elif r.is_indefinite:
        eff_min.append(INDEFINITE_CAP); eff_max.append(INDEFINITE_CAP); eff_src.append("indefinite_cap")
    elif not np.isnan(r.tip_min_days):
        eff_min.append(r.tip_min_days); eff_max.append(r.tip_max_days); eff_src.append("foodkeeper_tip")
    elif r.is_not_recommended:
        eff_min.append(np.nan); eff_max.append(np.nan); eff_src.append("not_recommended")
    elif not np.isnan(r.cat_min):
        eff_min.append(r.cat_min); eff_max.append(r.cat_max); eff_src.append("category_median")
    else:
        eff_min.append(np.nan); eff_max.append(np.nan); eff_src.append("unknown")
sl["min_days_effective"] = np.array(eff_min, dtype="float32")
sl["max_days_effective"] = np.array(eff_max, dtype="float32")
sl["effective_source"] = eff_src
for c in ("min_days", "max_days", "tip_min_days", "tip_max_days"):
    sl[c] = sl[c].astype("float32")
sl_out = sl.drop(columns=["category", "cat_min", "cat_max", "tip_min_days", "tip_max_days"])
write_parquet(sl_out, OUT_SHELF_LIFE / "foodkeeper_shelf_life.parquet")
print("shelf-life rows by storage/state:", sl_out.groupby(["storage", "state"]).size().to_dict())
print("effective_source:", sl_out.effective_source.value_counts().to_dict())
sl = sl_out

# ----------------------------------------------------- category medians (fallback) ----
sl_cat = sl.merge(product[["product_id", "category"]], on="product_id")
num = sl_cat[sl_cat.min_days.notna()]
cat_default = (num.groupby(["category", "storage", "state", "basis"])
               .agg(min_days=("min_days", "median"), max_days=("max_days", "median"), n=("product_id", "size"))
               .reset_index())
GROUP_TO_CATEGORY = {
    "dairy": "Dairy Products & Eggs", "egg": "Dairy Products & Eggs", "meat": "Meat", "poultry": "Poultry",
    "seafood": "Seafood", "vegetable": "Produce", "fruit": "Produce", "grain_pasta": "Grains, Beans & Pasta",
    "legume": "Grains, Beans & Pasta", "bakery": "Baked Goods", "herb_spice": "Baked Goods",
    "oil_fat": "Baked Goods", "sweetener": "Baked Goods", "sauce_condiment": "Condiments, Sauces & Canned Goods",
    "soup_broth": "Condiments, Sauces & Canned Goods", "beverage": "Beverages", "alcohol": "Beverages",
    "nut_seed": "Shelf Stable Foods", "snack_sweet": "Shelf Stable Foods", "mixed_dish": "Deli & Prepared Foods",
    "water": "Beverages", "other": "Shelf Stable Foods"}

PERISHABLE = {"dairy", "egg", "meat", "poultry", "seafood", "vegetable", "fruit", "mixed_dish"}

# ----------------------------------------------------------- ingredient matching ----
ing = pd.read_parquet(OUT_INGREDIENTS / "ingredient.parquet")
ri = pd.read_parquet(OUT_RECIPES / "recipe_ingredient.parquet")
used = set(ri.ingredient_id)
ing_used = ing[ing.ingredient_id.isin(used) | (ing.fdc_id.notna() & ~ing.is_non_food)].copy()  # recipes + any mapped pantry item
name_to_id = dict(zip(ing.canonical_name, ing.ingredient_id))

overrides = {}
for r in csv.DictReader(open(OUT_REFERENCE / "ingredient_foodkeeper_overrides.csv", encoding="utf-8")):
    overrides[r["canonical_name"].strip()] = int(r["foodkeeper_product_id"])
unknown = [n for n in overrides if n not in name_to_id]
if unknown:
    print(f"note: {len(unknown)} override names are not canonical ingredient names (ignored):", unknown[:10])
valid_pid = set(product.product_id)
bad = {n: p for n, p in overrides.items() if p not in valid_pid}
if bad:
    raise SystemExit(f"unknown FoodKeeper product ids in overrides: {bad}")

fk_idx_df = pd.DataFrame({"fdc_id": product.product_id,
                          "description": product.name + np.where(product.subtitle.notna(), ", " + product.subtitle.fillna(""), ""),
                          "data_type": "foodkeeper", "category": product.category})
fk_idx = UsdaIndex(fk_idx_df)

links = []
for r in ing_used.itertuples():
    pid, method, score = None, None, None
    if r.canonical_name in overrides:
        pid, method, score = overrides[r.canonical_name], "curated", 2.0
    else:
        res = fk_idx.match(r.canonical_name, topk=1)
        if res and res[0]["score"] >= 0.95:
            pid, method, score = res[0]["fdc_id"], "auto", res[0]["score"]
    links.append((r.ingredient_id, r.food_group, pid, method, score))
links = pd.DataFrame(links, columns=["ingredient_id", "food_group", "foodkeeper_product_id", "match_method", "match_score"])

out_rows = []
CONF = {"curated": "high", "auto": "medium"}
pid_rows = {pid: g for pid, g in sl.groupby("product_id")}
for r in links.itertuples():
    if r.foodkeeper_product_id is not None and not pd.isna(r.foodkeeper_product_id) and int(r.foodkeeper_product_id) in pid_rows:
        g = pid_rows[int(r.foodkeeper_product_id)].copy()
        g["ingredient_id"], g["foodkeeper_product_id"] = r.ingredient_id, int(r.foodkeeper_product_id)
        g["match_method"], g["match_score"], g["confidence"] = r.match_method, r.match_score, CONF[r.match_method]
        out_rows.append(g)
    else:
        catname = GROUP_TO_CATEGORY.get(r.food_group, "Shelf Stable Foods")
        g = cat_default[cat_default.category == catname].copy()
        g = g[g.state == "unopened"]
        if r.food_group in PERISHABLE and (g.storage != "pantry").any():
            g = g[g.storage != "pantry"]   # an unknown fresh item is assumed to be kept cold, not in the cupboard
        g["ingredient_id"], g["foodkeeper_product_id"] = r.ingredient_id, pd.NA
        g["match_method"], g["match_score"], g["confidence"] = "category_fallback", np.nan, "low"
        g["is_indefinite"] = False; g["is_when_ripe"] = False; g["is_not_recommended"] = False
        g["is_package_date_only"] = False
        g["min_days_effective"], g["max_days_effective"] = g.min_days, g.max_days
        g["effective_source"] = "category_median"
        g["metric_raw"] = None; g["tips"] = None
        out_rows.append(g.drop(columns=["category", "n"]))
isl = pd.concat(out_rows, ignore_index=True)

# default row: unopened, preferring a numeric/indefinite value, then pantry > refrigerator > freezer, DOP basis first
storage_rank = {"pantry": 0, "refrigerator": 1, "freezer": 2}
isl["_usable"] = ~isl.is_not_recommended & isl.min_days_effective.notna()
cand = isl[(isl.state == "unopened") & isl._usable].copy()
cand["_rank"] = cand.storage.map(storage_rank) * 10 + (cand.basis != "date_of_purchase").astype(int)
best = cand.sort_values(["ingredient_id", "_rank"]).groupby("ingredient_id").head(1)
isl["is_default"] = False
isl.loc[best.index, "is_default"] = True
isl = isl.drop(columns=["_usable"])
isl["foodkeeper_product_id"] = isl.foodkeeper_product_id.astype("Int64")
isl["ingredient_id"] = isl.ingredient_id.astype("int32")
isl["match_score"] = isl.match_score.astype("float32")
cols = ["ingredient_id", "foodkeeper_product_id", "match_method", "match_score", "confidence", "storage", "state",
        "basis", "min_days", "max_days", "min_days_effective", "max_days_effective", "effective_source",
        "is_indefinite", "is_when_ripe", "is_package_date_only", "is_not_recommended", "tips", "is_default"]
isl = isl[cols].sort_values(["ingredient_id", "storage", "state", "basis"]).reset_index(drop=True)
write_parquet(isl, OUT_SHELF_LIFE / "ingredient_shelf_life.parquet")

# ------------------------------------------------------------------ report ----
n_used = len(ing_used)
by = links.assign(m=links.match_method.fillna("category_fallback")).merge(
    ri.groupby("ingredient_id").recipe_id.nunique().rename("n_recipes").reset_index(), on="ingredient_id")
share = by.groupby("m").n_recipes.sum() / by.n_recipes.sum()
print(f"\ningredients used in recipes: {n_used:,}")
print("link method (ingredient count):", by.m.value_counts().to_dict())
print("link method (recipe-usage share):", share.round(3).to_dict())
d = isl[isl.is_default]
print(f"ingredients with a default shelf-life row: {d.ingredient_id.nunique():,} of {n_used:,}")
print("default storage:", d.storage.value_counts().to_dict())
print("default max_days_effective quantiles:", d.max_days_effective.describe().round(1).to_dict())
print("default effective_source:", d.effective_source.value_counts().to_dict())
name = ing.set_index("ingredient_id").canonical_name
chk = d[d.ingredient_id.isin([name.index[name == n][0] for n in ("spinach", "chicken breast", "milk", "rice", "egg", "onion", "salt", "butter", "tomato") if (name == n).any()])]
print(chk.assign(name=chk.ingredient_id.map(name))[["name", "storage", "basis", "min_days_effective", "max_days_effective", "effective_source", "confidence"]].to_string(index=False))
OUT_META.mkdir(parents=True, exist_ok=True)
