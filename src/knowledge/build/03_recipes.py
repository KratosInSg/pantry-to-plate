"""Step 03 - clean Food.com recipes, select the dinner pool, build recipe tables.

Keeps only what the planner uses:
  * dinner-eligible recipes (main dish / one-dish meal / soup-stew, minus desserts, drinks, breads ...)
  * whose every ingredient resolved to a canonical ingredient with USDA nutrition (no guessing)
  * with sane cooking time and stated calories

Outputs (data/canonical/recipes/ and interactions/):
  recipe.parquet               one row per retained recipe (grams/nutrition added by step 04)
  recipe_ingredient.parquet    recipe_id, position, ingredient_id, raw_text  (grams added by step 04)
  recipe_step.parquet          recipe_id, steps (list of instructions) - for display only
  interaction_{train,validation,test}.parquet   ratings restricted to retained recipes (Food.com's own splits)
"""
import ast
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (OUT_INGREDIENTS, OUT_INTERACTIONS, OUT_META, OUT_RECIPES, RAW_RECIPES,  # noqa: E402
                    write_parquet)

# Daily values Food.com used for its %DV columns (calibrated: kcal = 9*fat+4*protein+4*carb, R^2 = 0.987;
# sugar from sugar+water recipes; this is the pre-2016 FDA label).
DV = {"fat_g": 65.0, "sat_fat_g": 20.0, "sugars_g": 25.0, "sodium_mg": 2400.0, "protein_g": 50.0, "carbohydrate_g": 300.0}

DINNER_ANY = {"main-dish", "one-dish-meal", "soups-stews"}
NOT_DINNER = {"desserts", "beverages", "cocktails", "smoothies", "cookies-and-brownies", "cakes", "pies", "candy",
              "breads", "snacks", "spreads", "dips", "sauces", "condiments-etc", "frostings-and-icing", "punch"}
CUISINE_PRIORITY = [  # most specific first; the first present becomes the primary cuisine
    "indian", "chinese", "thai", "japanese", "korean", "vietnamese", "szechuan", "filipino", "indonesian", "malaysian",
    "pakistani", "italian", "french", "greek", "spanish", "german", "polish", "hungarian", "russian", "swedish",
    "portuguese", "irish", "scottish", "english", "welsh", "scandinavian", "moroccan", "lebanese", "turkish",
    "iranian-persian", "egyptian", "south-african", "middle-eastern", "african", "mexican", "tex-mex", "cuban",
    "brazilian", "caribbean", "central-american", "south-american", "cajun", "creole", "southern-united-states",
    "southwestern-united-states", "midwestern", "northeastern-united-states", "pacific-northwest", "californian",
    "hawaiian", "canadian", "australian", "new-zealand", "american", "jewish-ashkenazi", "asian", "european",
    "north-american"]
DIET_TAGS = ["vegetarian", "vegan", "gluten-free", "egg-free", "nut-free", "lactose", "kosher", "low-carb",
             "very-low-carbs", "low-fat", "low-sodium", "low-calorie", "low-cholesterol", "low-saturated-fat",
             "high-protein", "high-calcium", "low-protein", "diabetic", "healthy"]
MAIN_ING_TAGS = ["chicken", "chicken-breasts", "chicken-thighs-legs", "beef", "ground-beef", "pork", "pork-chops",
                 "pork-sausage", "ham", "bacon", "lamb-sheep", "turkey", "fish", "seafood", "shellfish", "shrimp",
                 "salmon", "tuna", "eggs", "beans", "lentils", "cheese", "pasta", "rice", "potatoes", "tomatoes",
                 "vegetables", "mushrooms", "soy-tofu", "chick-peas-garbanzos", "spinach", "casseroles", "stir-fry",
                 "curries", "chili", "pizza", "sandwiches", "salads", "stews", "soups-stews", "bisques-cream-soups"]
STYLE_TAGS = ["easy", "comfort-food", "kid-friendly", "spicy", "weeknight", "inexpensive", "one-dish-meal",
              "crock-pot-slow-cooker", "grilling", "stove-top", "oven", "microwave", "no-cook", "for-1-or-2",
              "for-large-groups", "beginner-cook", "5-ingredients-or-less", "3-steps-or-less", "oamc-freezer-make-ahead",
              "dinner-party", "potluck", "main-dish", "lunch", "breakfast", "brunch", "side-dishes", "appetizers"]
KEEP_TAGS = set(CUISINE_PRIORITY) | set(DIET_TAGS) | set(MAIN_ING_TAGS) | set(STYLE_TAGS)

# ------------------------------------------------------------------ load -----
raw = pd.read_csv(RAW_RECIPES / "RAW_recipes.csv")
print(f"raw recipes: {len(raw):,}")
for c in ("tags", "nutrition", "ingredients", "steps"):
    raw[c] = raw[c].map(ast.literal_eval)
ingredient = pd.read_parquet(OUT_INGREDIENTS / "ingredient.parquet")
alias = pd.read_parquet(OUT_INGREDIENTS / "ingredient_alias.parquet")

# alias -> ingredient ids. A raw string maps to >1 id only for explicit splits ("salt + black pepper").
amap = {}
for a, g in alias.groupby("alias"):
    ids = list(g.ingredient_id)
    if len(ids) > 1 and not g.is_split.any():
        ids = [int(g.sort_values("n_occurrences", ascending=False).ingredient_id.iloc[0])]  # conflict: most frequent wins
    amap[a] = ids
ing = ingredient.set_index("ingredient_id")
non_food = set(ing.index[ing.is_non_food])
has_fdc = set(ing.index[ing.fdc_id.notna()])

# ------------------------------------------------- ingredient rows per recipe --
rows = []
n_unmapped, n_total_food = [], []
for rid, items in zip(raw.id, raw.ingredients):
    seen = set()
    pos = 0
    unm = 0
    for s in items:
        ids = amap.get(re.sub(r"\s+", " ", s.lower().strip()), [])
        for iid in ids:
            if iid in non_food or iid in seen:
                continue
            seen.add(iid)
            rows.append((rid, pos, iid, s))
            pos += 1
            if iid not in has_fdc:
                unm += 1
    n_unmapped.append(unm)
    n_total_food.append(pos)
ri = pd.DataFrame(rows, columns=["recipe_id", "position", "ingredient_id", "raw_text"])
raw["n_food_ingredients"] = n_total_food
raw["n_unmapped"] = n_unmapped
print(f"recipe-ingredient rows: {len(ri):,} | recipes with all ingredients mapped: {(raw.n_unmapped==0).mean():.1%}")

# --------------------------------------------------------------- cleaning -----
raw["name"] = raw.name.fillna("").str.replace(r"\s+", " ", regex=True).str.strip()
raw["name"] = raw.name.str[:1].str.upper() + raw.name.str[1:]
nd = pd.DataFrame(raw.nutrition.tolist(), columns=["kcal", "fat_pdv", "sugar_pdv", "sodium_pdv", "protein_pdv",
                                                   "satfat_pdv", "carb_pdv"])
raw["kcal_stated"] = nd.kcal.values
raw["fat_g_stated"] = nd.fat_pdv.values * DV["fat_g"] / 100
raw["sugars_g_stated"] = nd.sugar_pdv.values * DV["sugars_g"] / 100
raw["sodium_mg_stated"] = nd.sodium_pdv.values * DV["sodium_mg"] / 100
raw["protein_g_stated"] = nd.protein_pdv.values * DV["protein_g"] / 100
raw["sat_fat_g_stated"] = nd.satfat_pdv.values * DV["sat_fat_g"] / 100
raw["carbohydrate_g_stated"] = nd.carb_pdv.values * DV["carbohydrate_g"] / 100

tagset = raw.tags.map(set)
is_dinner = tagset.map(lambda s: bool(s & DINNER_ANY) and not (s & NOT_DINNER))
sane_time = raw.minutes.between(5, 1440)
sane_kcal = raw.kcal_stated.between(80, 2500)
# stated macros must roughly agree with stated calories (catches corrupted rows): 4P + 4C + 9F within 35%
atwater = 4 * raw.protein_g_stated + 4 * raw.carbohydrate_g_stated + 9 * raw.fat_g_stated
consistent = (atwater - raw.kcal_stated).abs() <= 0.35 * raw.kcal_stated + 30
sane_ing = raw.n_food_ingredients.between(2, 30)
mapped = raw.n_unmapped == 0

funnel = [("all recipes", pd.Series(True, index=raw.index)), ("dinner-eligible tags", is_dinner),
          ("+ cooking time 5-1440 min", is_dinner & sane_time), ("+ stated kcal 80-2500", is_dinner & sane_time & sane_kcal),
          ("+ macros consistent with kcal", is_dinner & sane_time & sane_kcal & consistent),
          ("+ 2-30 ingredients", is_dinner & sane_time & sane_kcal & consistent & sane_ing),
          ("+ every ingredient mapped to USDA", is_dinner & sane_time & sane_kcal & consistent & sane_ing & mapped)]
keep = funnel[-1][1]
for label, m in funnel:
    print(f"  {label:<36} {int(m.sum()):>8,}")

# exact duplicates: same normalised name and same ingredient set -> keep the first id
ing_sets = ri.groupby("recipe_id").ingredient_id.apply(lambda s: tuple(sorted(s)))
cand = raw[keep].copy()
cand["ing_key"] = cand.id.map(ing_sets)
cand["name_key"] = cand.name.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True)
dups = cand.duplicated(["name_key", "ing_key"], keep="first")
print(f"  exact duplicates removed: {int(dups.sum()):,}")
cand = cand[~dups].copy()

# ---------------------------------------------------------- derived fields ----
cand["tags_kept"] = cand.tags.map(lambda l: sorted({t for t in l if t in KEEP_TAGS}))
cand["cuisine"] = cand.tags.map(lambda l: next((c for c in CUISINE_PRIORITY if c in set(l)), None))
ri = ri[ri.recipe_id.isin(cand.id)].copy()
ri = ri.merge(ing[["is_vegetarian", "is_vegan", "contains_dairy", "contains_egg", "contains_gluten", "contains_peanut",
                   "contains_tree_nut", "contains_soy", "contains_sesame", "contains_fish", "contains_shellfish",
                   "contains_meat", "contains_poultry", "contains_pork", "contains_alcohol", "contains_honey",
                   "contains_gelatin"]], left_on="ingredient_id", right_index=True, how="left")
agg = ri.groupby("recipe_id").agg(
    is_vegetarian=("is_vegetarian", "all"), is_vegan=("is_vegan", "all"),
    contains_dairy=("contains_dairy", "any"), contains_egg=("contains_egg", "any"),
    contains_gluten=("contains_gluten", "any"), contains_peanut=("contains_peanut", "any"),
    contains_tree_nut=("contains_tree_nut", "any"), contains_soy=("contains_soy", "any"),
    contains_sesame=("contains_sesame", "any"), contains_fish=("contains_fish", "any"),
    contains_shellfish=("contains_shellfish", "any"), contains_meat=("contains_meat", "any"),
    contains_poultry=("contains_poultry", "any"), contains_pork=("contains_pork", "any"),
    contains_alcohol=("contains_alcohol", "any"))
cand = cand.merge(agg, left_on="id", right_index=True, how="left")
ri = ri[["recipe_id", "position", "ingredient_id", "raw_text"]].sort_values(["recipe_id", "position"]).reset_index(drop=True)
ri["position"] = ri.position.astype("int16")
ri["ingredient_id"] = ri.ingredient_id.astype("int32")

# ------------------------------------------------------------- interactions ---
splits = {}
for name in ("train", "validation", "test"):
    d = pd.read_csv(RAW_RECIPES / f"interactions_{name}.csv", usecols=["user_id", "recipe_id", "date", "rating"])
    d = d[d.recipe_id.isin(cand.id)].copy()
    d["is_rated"] = d.rating > 0           # Food.com stores "no rating" as 0
    d["date"] = pd.to_datetime(d.date)
    d["rating"] = d.rating.astype("int8")
    d["user_id"] = d.user_id.astype("int64")
    d["recipe_id"] = d.recipe_id.astype("int64")
    splits[name] = d.reset_index(drop=True)
tr = splits["train"]
rt = tr[tr.is_rated].groupby("recipe_id").rating.agg(rating_mean_train="mean", n_ratings_train="size")
cand = cand.merge(rt, left_on="id", right_index=True, how="left")
cand["n_ratings_train"] = cand.n_ratings_train.fillna(0).astype("int32")
cand["rating_mean_train"] = cand.rating_mean_train.astype("float32").round(3)

# ------------------------------------------------------------------ write -----
recipe = cand.drop(columns=["n_ingredients"]).rename(columns={"id": "recipe_id", "minutes": "minutes_total",
                                                                  "n_food_ingredients": "n_ingredients"})
recipe["tags"] = recipe.tags_kept
recipe = recipe[["recipe_id", "name", "minutes_total", "n_steps", "n_ingredients", "cuisine", "tags", "is_vegetarian",
                 "is_vegan", "contains_dairy", "contains_egg", "contains_gluten", "contains_peanut", "contains_tree_nut",
                 "contains_soy", "contains_sesame", "contains_fish", "contains_shellfish", "contains_meat",
                 "contains_poultry", "contains_pork", "contains_alcohol", "kcal_stated", "protein_g_stated",
                 "fat_g_stated", "sat_fat_g_stated", "carbohydrate_g_stated", "sugars_g_stated", "sodium_mg_stated",
                 "rating_mean_train", "n_ratings_train"]].sort_values("recipe_id").reset_index(drop=True)
for c in ("minutes_total", "n_steps", "n_ingredients"):
    recipe[c] = recipe[c].astype("int32")
for c in ("kcal_stated", "protein_g_stated", "fat_g_stated", "sat_fat_g_stated", "carbohydrate_g_stated",
          "sugars_g_stated", "sodium_mg_stated"):
    recipe[c] = recipe[c].astype("float32").round(2)
recipe["recipe_id"] = recipe.recipe_id.astype("int64")
write_parquet(recipe, OUT_RECIPES / "recipe.parquet")
write_parquet(ri, OUT_RECIPES / "recipe_ingredient.parquet")

steps = cand[["id", "steps"]].rename(columns={"id": "recipe_id"}).sort_values("recipe_id").reset_index(drop=True)
steps["steps"] = steps.steps.map(lambda l: [re.sub(r"\s+", " ", x).strip() for x in l])
steps["recipe_id"] = steps.recipe_id.astype("int64")
write_parquet(steps, OUT_RECIPES / "recipe_step.parquet")
for name, d in splits.items():
    write_parquet(d, OUT_INTERACTIONS / f"interaction_{name}.parquet")

# ------------------------------------------------------------------ report ----
print("\n=== recipe pool ===")
print("recipes:", len(recipe), "| ingredient rows:", len(ri), "| median ingredients:", int(recipe.n_ingredients.median()),
      "| median minutes:", int(recipe.minutes_total.median()))
print("cuisine (top 8):", recipe.cuisine.value_counts().head(8).to_dict(), "| no cuisine tag:", int(recipe.cuisine.isna().sum()))
print("vegetarian derived:", int(recipe.is_vegetarian.sum()), "| vegan:", int(recipe.is_vegan.sum()),
      "| gluten-free:", int((~recipe.contains_gluten).sum()), "| dairy-free:", int((~recipe.contains_dairy).sum()))
foodcom_veg = recipe.tags.map(lambda l: "vegetarian" in l)
print(f"Food.com 'vegetarian' tag: {int(foodcom_veg.sum())} | tagged vegetarian but we derive non-veg: "
      f"{int((foodcom_veg & ~recipe.is_vegetarian).sum())} | derived veg but untagged: "
      f"{int((~foodcom_veg & recipe.is_vegetarian).sum())}")
print("interactions kept:", {k: len(v) for k, v in splits.items()})
OUT_META.mkdir(parents=True, exist_ok=True)
pd.DataFrame([(l, int(m.sum())) for l, m in funnel], columns=["stage", "recipes"]).to_csv(OUT_META / "recipe_funnel.csv", index=False)
