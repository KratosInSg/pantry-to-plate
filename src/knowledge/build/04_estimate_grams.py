"""Step 04 - estimate grams per serving for every recipe ingredient, then compute recipe nutrition.

Food.com gives ingredient *names* and one nutrition vector per serving, but no quantities.
For each recipe we solve a small non-negative least-squares problem:

    minimise   sum_k w_k * ((A g)_k - t_k)^2 / s_k^2   +   lambda * sum_j ((g_j - mu_j) / sigma_j)^2
    subject to g >= 0

    A[k, j]  USDA nutrient k per gram of ingredient j      (from the canonical ingredient layer)
    t[k]     Food.com stated per-serving nutrient k        (kcal, fat, sat fat, carbs, sugars, sodium, protein)
    mu, sigma  prior grams-per-serving for the ingredient  (food-group defaults, then empirical per ingredient)

The result is an *estimate*: every row carries grams_source = 'estimated' and the recipe carries its fit
error, so downstream code (and the evaluation) can see exactly how much to trust it. Recipes whose
ingredients cannot reproduce the stated nutrition are dropped - they signal a wrong mapping or corrupt data.

A held-out check (fit on kcal/fat/carb/protein only, predict sodium/sugar/sat-fat) is reported so the
quality claim is not circular.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (NUTRIENT_OUTPUT_ORDER, OUT_INGREDIENTS, OUT_INTERACTIONS, OUT_META, OUT_NUTRITION,  # noqa: E402
                    OUT_RECIPES, write_parquet)

# target nutrients: (stated column in recipe.parquet, ingredient column per 100 g, weight, abs floor for scale)
TARGETS = [("kcal_stated", "energy_kcal", 2.0, 30.0),
           ("fat_g_stated", "fat_g", 1.0, 2.0),
           ("carbohydrate_g_stated", "carbohydrate_g", 1.0, 3.0),
           ("protein_g_stated", "protein_g", 1.0, 2.0),
           ("sat_fat_g_stated", "sat_fat_g", 0.5, 1.0),
           ("sugars_g_stated", "sugars_g", 0.5, 2.0),
           ("sodium_mg_stated", "sodium_mg", 0.7, 60.0)]
HELD_OUT = ["sat_fat_g_stated", "sugars_g_stated", "sodium_mg_stated"]

# grams per serving that a single ingredient typically contributes, by food group: (mu, sigma)
GROUP_PRIOR = {
    "herb_spice": (1.5, 2.5), "oil_fat": (12, 12), "sweetener": (15, 18), "dairy": (45, 45), "egg": (50, 40),
    "meat": (110, 60), "poultry": (110, 60), "seafood": (110, 60), "vegetable": (70, 60), "fruit": (50, 50),
    "grain_pasta": (55, 40), "bakery": (35, 30), "legume": (60, 50), "nut_seed": (15, 15),
    "sauce_condiment": (20, 22), "soup_broth": (150, 120), "beverage": (60, 70), "alcohol": (30, 35),
    "water": (100, 150), "snack_sweet": (20, 20), "mixed_dish": (80, 60), "other": (30, 40),
}
SPECIFIC_PRIOR = {}   # filled from SPECIFIC below

# hard upper bounds on grams per serving (a plausibility box: no recipe serving holds 100 g of garlic)
GROUP_CAP = {
    "herb_spice": 15, "oil_fat": 60, "sweetener": 120, "dairy": 250, "egg": 150, "meat": 400, "poultry": 400,
    "seafood": 400, "vegetable": 350, "fruit": 300, "grain_pasta": 250, "bakery": 200, "legume": 250, "nut_seed": 100,
    "sauce_condiment": 150, "soup_broth": 600, "beverage": 400, "alcohol": 200, "water": 700, "snack_sweet": 120,
    "mixed_dish": 300, "other": 150}

# Ingredient-specific (mu, sigma, cap) in grams per serving where the group default would be badly wrong.
# These ingredients carry little nutrient signal, so without a sensible prior the fit just returns the group value.
SPECIFIC = {
    # fresh herbs and aromatics
    "parsley": (2.5, 2.5, 15), "cilantro": (2.5, 2.5, 15), "chive": (1.5, 1.5, 8), "dill": (1.5, 1.5, 8),
    "mint": (1.5, 1.5, 10), "garlic": (4, 4, 25), "ginger": (3, 3, 25), "scallion": (8, 8, 40), "shallot": (10, 8, 40),
    "celery": (25, 25, 120), "lemongrass": (3, 3, 20), "basil": (2, 2, 15), "thyme": (1.5, 1.5, 8), "rosemary": (1.5, 1.5, 8),
    # chilies / peppers / produce used as accents
    "jalapeno": (8, 8, 40), "chili": (6, 6, 40), "green chili": (8, 8, 50), "bell pepper": (35, 30, 150),
    "red bell pepper": (35, 30, 150), "green bell pepper": (35, 30, 150), "yellow bell pepper": (35, 30, 150),
    "green pepper": (35, 30, 150), "red pepper": (35, 30, 150), "red onion": (25, 25, 120),
    "mushroom": (35, 35, 200), "carrot": (30, 30, 150), "tomato": (50, 45, 250), "crushed tomato": (50, 40, 200),
    "lettuce": (35, 35, 150), "spinach": (40, 40, 150), "cabbage": (40, 40, 200), "corn": (30, 30, 150),
    "frozen pea": (25, 25, 120), "olive": (8, 8, 50), "black olive": (6, 6, 40), "caper": (3, 3, 20),
    "artichoke heart": (25, 25, 120), "leek": (25, 25, 120), "cucumber": (30, 30, 150),
    # citrus and concentrated flavourings
    "lemon juice": (8, 8, 40), "lime juice": (6, 6, 35), "lemon": (15, 15, 100), "lime": (10, 10, 60),
    "lemon peel": (1.5, 1.5, 8), "orange peel": (1.5, 1.5, 8), "lime peel": (1.5, 1.5, 8), "orange juice": (30, 30, 150),
    "apple juice": (30, 30, 150), "tomato paste": (8, 8, 40), "tomato sauce": (35, 30, 150), "ketchup": (8, 8, 40),
    "salsa": (15, 15, 80), "mustard": (3, 3, 20), "dijon mustard": (3, 3, 20), "mayonnaise": (8, 8, 40),
    "soy sauce": (6, 5, 30), "worcestershire sauce": (2, 2, 15), "hot sauce": (2, 2, 15), "fish sauce": (3, 3, 20),
    "oyster sauce": (6, 5, 30), "hoisin sauce": (8, 8, 40), "teriyaki sauce": (10, 10, 50), "barbecue sauce": (20, 20, 100),
    "chili paste": (5, 5, 30), "vinegar": (5, 5, 40), "balsamic vinegar": (4, 4, 30), "tabasco sauce": (1, 1, 8),
    "peanut butter": (12, 12, 60), "dressing": (12, 12, 60), "pesto sauce": (10, 10, 50),
    # drinks / alcohol used for cooking
    "white wine": (25, 25, 120), "red wine": (25, 25, 120), "dry sherry": (10, 10, 60), "beer": (60, 60, 350),
    "brandy": (8, 8, 40),
    # sweeteners, fats, baking
    "sugar": (8, 8, 60), "brown sugar": (8, 8, 60), "powdered sugar": (8, 8, 60), "honey": (7, 7, 40),
    "maple syrup": (10, 10, 60), "all-purpose flour": (15, 15, 100), "cornstarch": (2, 2, 15), "breadcrumb": (10, 10, 60),
    "butter": (10, 10, 60), "olive oil": (8, 8, 50), "vegetable oil": (8, 8, 50), "canola oil": (8, 8, 50),
    "sesame oil": (3, 3, 20), "margarine": (8, 8, 50), "shortening": (8, 8, 50), "cooking spray": (0.5, 0.5, 5),
    "baking powder": (1, 1, 12), "baking soda": (0.7, 0.7, 8), "yeast": (1, 1, 12), "vanilla extract": (1, 1, 10),
    # dairy / eggs
    "parmesan cheese": (10, 10, 50), "cheddar cheese": (25, 25, 100), "mozzarella cheese": (25, 25, 100),
    "cream cheese": (20, 20, 80), "sour cream": (20, 20, 100), "heavy cream": (25, 25, 100), "half and half": (20, 20, 100),
    "milk": (45, 45, 250), "plain yogurt": (40, 40, 200), "ricotta cheese": (40, 40, 150), "feta cheese": (20, 20, 80),
    "egg": (50, 25, 150), "buttermilk": (30, 30, 200),
    # liquids / canned
    "chicken broth": (80, 60, 400), "beef broth": (80, 60, 400), "vegetable broth": (60, 60, 400),
    "chicken bouillon cube": (0.5, 0.5, 5), "beef bouillon cube": (0.5, 0.5, 5), "cream of mushroom soup": (40, 30, 200),
    "cream of chicken soup": (40, 30, 200), "coconut milk": (50, 50, 250),
    # staples
    "salt": (1.5, 1.5, 8), "black pepper": (0.7, 0.8, 4), "water": (100, 150, 700),
    "pasta": (50, 30, 150), "rice": (45, 30, 150), "cooked rice": (60, 40, 200),
}
SPECIFIC_PRIOR = {k: (v[0], v[1]) for k, v in SPECIFIC.items()}
SPECIFIC_CAP = {k: v[2] for k, v in SPECIFIC.items()}
LAMBDA = 1.0


def load():
    recipe = pd.read_parquet(OUT_RECIPES / "recipe.parquet")
    ri = pd.read_parquet(OUT_RECIPES / "recipe_ingredient.parquet")
    ing = pd.read_parquet(OUT_INGREDIENTS / "ingredient.parquet").set_index("ingredient_id")
    nut = pd.read_parquet(OUT_NUTRITION / "ingredient_nutrition_per100g.parquet").set_index("ingredient_id")
    # make the step re-runnable: drop anything a previous run of this step added
    recipe = recipe.drop(columns=[c for c in recipe.columns if c.endswith("_computed")
                                  or c in ("fit_kcal_rel_error", "total_grams_per_serving")])
    ri = ri.drop(columns=[c for c in ("grams_per_serving", "grams_source", "kcal_share", "grams_basis") if c in ri.columns])
    return recipe, ri, ing, nut


recipe, ri, ing, nut = load()
ids = ing.index.values
pos = {iid: i for i, iid in enumerate(ids)}
NUT_COLS = NUTRIENT_OUTPUT_ORDER
per_g = np.zeros((len(ids), len(NUT_COLS)), dtype="float64")
tmp = nut[NUT_COLS].reindex(ids)
per_g[:] = tmp.fillna(0.0).values / 100.0              # missing nutrient values contribute 0 (flagged in README)
col = {c: i for i, c in enumerate(NUT_COLS)}

mu0 = np.zeros(len(ids)); sg0 = np.zeros(len(ids)); cap0 = np.zeros(len(ids))
for iid in ids:
    name, grp = ing.canonical_name[iid], ing.food_group[iid]
    m, sd = SPECIFIC_PRIOR.get(name, GROUP_PRIOR.get(grp, GROUP_PRIOR["other"]))
    mu0[pos[iid]], sg0[pos[iid]] = m, sd
    cap0[pos[iid]] = SPECIFIC_CAP.get(name, GROUP_CAP.get(grp, GROUP_CAP["other"]))

recipe = recipe.set_index("recipe_id")
groups = {rid: g for rid, g in ri.groupby("recipe_id")}
rids = list(groups)


def solve_recipe(idx_arr, t_row, mu, sg, ub, use_mask):
    A = per_g[idx_arr][:, [col[c] for _, c, _, _ in TARGETS]].T            # K x m
    w = np.array([w for _, _, w, _ in TARGETS])
    s = np.maximum(0.10 * np.abs(t_row), np.array([f for _, _, _, f in TARGETS]))
    wt = np.sqrt(w) / s
    wt = np.where(use_mask, wt, 0.0)
    M = np.vstack([A * wt[:, None], np.sqrt(LAMBDA) * np.diag(1.0 / sg)])
    b = np.concatenate([t_row * wt, np.sqrt(LAMBDA) * mu / sg])
    res = lsq_linear(M, b, bounds=(0.0, ub), method="bvls")
    return res.x


def run_pass(mu_all, sg_all, cap_all, use_mask, label):
    out = {}
    T = recipe[[c for c, *_ in TARGETS]]
    for k, rid in enumerate(rids):
        g_df = groups[rid]
        idx_arr = np.array([pos[i] for i in g_df.ingredient_id])
        out[rid] = solve_recipe(idx_arr, T.loc[rid].values.astype("float64"), mu_all[idx_arr], sg_all[idx_arr],
                                cap_all[idx_arr], use_mask)
    print(f"{label}: solved {len(out):,} recipes")
    return out


def predict(rid, g):
    idx_arr = np.array([pos[i] for i in groups[rid].ingredient_id])
    return g @ per_g[idx_arr]              # all nutrient columns per serving


# ---- pass 1: group priors ---------------------------------------------------
full_mask = np.ones(len(TARGETS), dtype=bool)
g1 = run_pass(mu0, sg0, cap0, full_mask, "pass 1")


def rel_err_kcal(gmap):
    e = {}
    for rid, g in gmap.items():
        k = predict(rid, g)[col["energy_kcal"]]
        e[rid] = abs(k - recipe.kcal_stated[rid]) / max(recipe.kcal_stated[rid], 1.0)
    return pd.Series(e)


e1 = rel_err_kcal(g1)
good1 = set(e1.index[e1 <= 0.15])
print(f"pass-1 kcal relative error <=15%: {len(good1)/len(e1):.1%} (median {e1.median():.3f})")

# ---- empirical per-ingredient priors from well-fitted recipes -------------------
rows = [(iid, gv) for rid in good1 for iid, gv in zip(groups[rid].ingredient_id, g1[rid])]
emp = pd.DataFrame(rows, columns=["ingredient_id", "g"]).groupby("ingredient_id").g.agg(
    n="size", med="median", q25=lambda s: s.quantile(0.25), q75=lambda s: s.quantile(0.75),
    q90=lambda s: s.quantile(0.90))
emp = emp[emp.n >= 25]
mu1, sg1, cap1 = mu0.copy(), sg0.copy(), cap0.copy()
for iid, r in emp.iterrows():
    i = pos[iid]
    mu1[i] = max(0.3, r.med)
    sg1[i] = max(0.5 * r.med, (r.q75 - r.q25) / 1.35, 0.5)
    cap1[i] = min(cap0[i], max(3.0 * r.q90, 5.0))   # never above the group/specific cap
print(f"empirical priors for {len(emp):,} ingredients (>=25 well-fitted uses)")

# ---- pass 2 + final -------------------------------------------------------------
g2 = run_pass(mu1, sg1, cap1, full_mask, "pass 2")
e2 = rel_err_kcal(g2)

# ---- held-out validation: fit without sat fat / sugars / sodium, predict them ---------
mask_ho = np.array([c not in HELD_OUT for c, *_ in TARGETS])
g_ho = run_pass(mu1, sg1, cap1, mask_ho, "held-out fit")
ho = {}
for stated, ingcol, *_ in TARGETS:
    if stated not in HELD_OUT:
        continue
    pred = np.array([predict(rid, g_ho[rid])[col[ingcol]] for rid in rids])
    true = recipe.loc[rids, stated].values
    ok = true > (2.0 if "mg" not in stated else 60.0)
    ape = np.abs(pred[ok] - true[ok]) / true[ok]
    ho[stated] = (float(np.median(ape)), float(np.mean(ape <= 0.25)))
print("held-out (not used in fit):", {k: f"median APE {v[0]:.0%}, within 25%: {v[1]:.0%}" for k, v in ho.items()})

# ---- quality gate: stated kcal must be reproducible from the ingredients --------------
pred_all = {rid: predict(rid, g2[rid]) for rid in rids}
fit = pd.DataFrame({"fit_kcal_rel_error": e2})
for stated, ingcol, *_ in TARGETS[1:4]:   # fat, carb, protein: absolute error vs stated
    fit[f"_err_{ingcol}"] = pd.Series({rid: abs(pred_all[rid][col[ingcol]] - recipe.loc[rid, stated]) for rid in rids})
fit["total_g"] = pd.Series({rid: g2[rid].sum() for rid in rids})
quality_ok = (fit.fit_kcal_rel_error <= 0.15) & fit.total_g.between(60, 1500)
print(f"fit quality gate: {quality_ok.mean():.1%} of recipes pass | dropped {int((~quality_ok).sum()):,}")
dropped = fit[~quality_ok].reset_index().rename(columns={"index": "recipe_id"})
dropped.to_csv(OUT_META / "recipes_dropped_poor_fit.csv", index=False)

keep_ids = set(fit.index[quality_ok])
# ---- write final tables ----------------------------------------------------------------
ri_out = ri[ri.recipe_id.isin(keep_ids)].copy()
ri_out["grams_per_serving"] = [float(g2[r][list(groups[r].ingredient_id).index(i)]) for r, i in
                               zip(ri_out.recipe_id, ri_out.ingredient_id)]
ri_out["grams_per_serving"] = ri_out.grams_per_serving.astype("float32").round(2)
ri_out["grams_source"] = "estimated"
# which amounts did the data actually inform? Ingredients carrying >=5% of the recipe's calories are constrained by
# the stated nutrition ("fitted"); accents (herbs, spices, aromatics) are prior-dominated defaults.
kc_col = col["energy_kcal"]
share = {}
for rid in keep_ids:
    ia = np.array([pos[i] for i in groups[rid].ingredient_id])
    kc = g2[rid] * per_g[ia, kc_col]
    share[rid] = dict(zip(groups[rid].ingredient_id, kc / max(kc.sum(), 1e-6)))
ri_out["kcal_share"] = np.array([share[r][i] for r, i in zip(ri_out.recipe_id, ri_out.ingredient_id)], dtype="float32").round(4)
ri_out["grams_basis"] = np.where(ri_out.kcal_share >= 0.05, "fitted", "prior_default")
write_parquet(ri_out, OUT_RECIPES / "recipe_ingredient.parquet")

comp = pd.DataFrame({rid: pred_all[rid] for rid in keep_ids}, index=NUT_COLS).T
comp.columns = [c if c != "energy_kcal" else "kcal" for c in comp.columns]
comp = comp.rename(columns=lambda c: f"{c}_computed")
comp["total_grams_per_serving"] = pd.Series({rid: g2[rid].sum() for rid in keep_ids})
comp = comp.astype("float32").round(2)
final = recipe.loc[sorted(keep_ids)].join(comp)
final["fit_kcal_rel_error"] = fit.fit_kcal_rel_error.reindex(final.index).astype("float32").round(4)
final = final.reset_index()
write_parquet(final, OUT_RECIPES / "recipe.parquet")

steps = pd.read_parquet(OUT_RECIPES / "recipe_step.parquet")
write_parquet(steps[steps.recipe_id.isin(keep_ids)].reset_index(drop=True), OUT_RECIPES / "recipe_step.parquet")
for name in ("train", "validation", "test"):
    d = pd.read_parquet(OUT_INTERACTIONS / f"interaction_{name}.parquet")
    write_parquet(d[d.recipe_id.isin(keep_ids)].reset_index(drop=True), OUT_INTERACTIONS / f"interaction_{name}.parquet")

# ---- ingredient-level summary (what the estimator learned) --------------------------------
look = ri_out.merge(ing[["canonical_name", "food_group"]], left_on="ingredient_id", right_index=True)
summ = look.groupby("canonical_name").grams_per_serving.agg(["size", "median"]).sort_values("size", ascending=False)
print("\nmedian estimated grams per serving, most frequent ingredients:")
print(summ.head(25).round(1).T.to_string())
rep = {"recipes_final": len(final), "kcal_fit_median_rel_error": float(final.fit_kcal_rel_error.median()),
       "total_grams_median": float(final.total_grams_per_serving.median()),
       "held_out_median_ape": {k: round(v[0], 3) for k, v in ho.items()}}
pd.Series(rep).to_json(OUT_META / "grams_estimation_report.json", indent=2)
print(rep)
