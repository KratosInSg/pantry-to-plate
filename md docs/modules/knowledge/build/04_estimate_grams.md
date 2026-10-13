# `build/04_estimate_grams.py`

## Purpose

Food.com publishes ingredient **names** and one nutrition vector per serving, but no quantities. This step estimates
**grams per serving** for every recipe ingredient so that nutrition can be computed (`grams × USDA per 100 g`), pantry
use and grocery shortfalls can be simulated, and everything is labelled as an estimate.

## Model (per recipe, bounded least squares, `scipy.optimize.lsq_linear` / BVLS)

```
minimise   Σ_k w_k ((A g)_k − t_k)² / s_k²   +   λ Σ_j ((g_j − μ_j) / σ_j)²
subject to 0 ≤ g_j ≤ cap_j
```

* `A` USDA nutrient per gram of each ingredient; `t` Food.com's stated kcal, fat, carbs, protein, sat fat, sugars,
  sodium; `s_k = max(10% of t_k, floor)`.
* **Priors** `(μ, σ)`: food-group defaults, overridden by ~110 ingredient-specific values (`SPECIFIC`) for items
  where the group default is badly wrong (garlic, parsley, lemon juice, soy sauce …).
* **Caps**: group caps, ingredient caps, then `min(cap, 3 × q90)` from the first pass.
* **Two passes:** pass 1 with defaults; pass 2 with empirical priors learned from well-fitted recipes.

## Why priors and caps matter (lessons learned)

* Ingredients with little nutrient signal return their *prior*; a wrong group prior (herbs as "vegetable", 70 g)
  produced 50 g of parsley per serving.
* Unbounded fits "bought" calories with garlic (111 g in one roast). Caps fixed it; recipes that cannot match their
  stated nutrition under the caps are **dropped** (~7%), which also removes bad mappings.

## Outputs

`recipe_ingredient`: `grams_per_serving`, `grams_source = estimated`, `kcal_share`, `grams_basis`
(`fitted` if the ingredient carries ≥ 5% of kcal, else `prior_default`).
`recipe`: `*_computed` nutrients (15), `total_grams_per_serving`, `fit_kcal_rel_error`.
`_meta/grams_estimation_report.json`, `_meta/recipes_dropped_poor_fit.csv`.

## Honest accuracy

Held-out check — fit *without* sat fat / sugars / sodium, then predict them: median APE **12% / 29% / 36%**.
`kcal_computed` matches `kcal_stated` by construction (do not quote it as accuracy).

## Gate

kcal relative error ≤ 15% and total mass 60–1500 g per serving.

## Change log

- 2026-10-12 — Created (docs backfilled). NNLS replaced by bounded least squares + caps; ingredient-specific priors;
  `grams_basis` / `kcal_share` added.
