# `build/03_recipes.py`

## Purpose

Clean the Food.com corpus and select the **dinner pool** the planner may use.

## Selection funnel (231,637 → ~54K)

| Stage | Rule |
| --- | --- |
| dinner-eligible tags | has `main-dish` / `one-dish-meal` / `soups-stews` and none of desserts, beverages, breads, snacks, sauces … |
| cooking time | 5–1440 min (drops the `2147483647` sentinel and zero-minute rows) |
| stated kcal | 80–2500 |
| macros consistent | 4P + 4C + 9F within 35% (+30 kcal) of stated kcal — catches corrupt rows |
| ingredient count | 2–30 |
| **all ingredients mapped** | every canonical ingredient has USDA nutrition — recipes are excluded, never guessed |
| duplicates | same normalised name + same ingredient set → keep one |

Step 04 then drops recipes whose nutrition cannot be reproduced from realistic amounts.

## Decisions

* **%DV → grams** uses the pre-2016 label values Food.com used (fat 65, sat fat 20, sodium 2400, carb 300,
  protein 50, sugar 25 g), calibrated empirically (kcal ≈ 9F + 4P + 4C with R² = 0.987; sugar from sugar + water
  recipes). Recorded in `reference/nutrient_daily_value.csv`.
* **Diet/allergen flags are derived from ingredients**, not Food.com tags.
* **Tags kept:** a curated subset (cuisine, diet, main-ingredient, style) — the other hundreds are noise.
* **Ratings:** `rating_mean_train` / `n_ratings_train` use the *train* split only (no leakage into evaluation).
  `rating == 0` means "no rating" and is flagged `is_rated = False`.
* **Interactions** keep Food.com's own frozen train/validation/test assignment.

## Outputs

`recipes/recipe` (no grams yet), `recipes/recipe_ingredient`, `recipes/recipe_step`,
`interactions/interaction_{train,validation,test}`, `_meta/recipe_funnel.csv`.

## Change log

- 2026-10-12 — Created (docs backfilled).
