# `src/knowledge/recipes.py`

## Purpose

`RecipeCatalog`: the 54,179-recipe dinner pool as read-only numpy arrays plus an inverted index, so the planning path
(hard rules, preference scores, pantry coverage) can touch **every recipe on every request** in milliseconds.

## Where it sits

Next to `KnowledgeStore` (ingredients, nutrition, shelf life). The store answers "what is this ingredient?"; the
catalogue answers "which recipes exist and what is in them?". It reads `data/canonical/recipes/*.parquet`.

## Public API

| Name | What |
| --- | --- |
| `RecipeCatalog(data_dir=None)` / `get_default_catalog()` | Lazy, cached. Use the shared default |
| `n`, `recipe_ids` | Count; row index → Food.com recipe id (sorted ascending) |
| `minutes`, `kcal`, `protein_g`, `fat_g`, `carbohydrate_g` | Per-serving arrays aligned to the row index (nutrition **computed** from grams × USDA) |
| `rating_mean`, `n_ratings` | Train-split ratings only (leakage-safe); NaN / 0 when unrated |
| `cuisine`, `tags`, `names` | Python lists aligned to the row index |
| `flag(name)` | Boolean array for one of `FLAG_COLUMNS` (`is_vegan`, `contains_peanut`, …) |
| `ingredients(idx)` | `(ingredient_ids, grams_per_serving)` of one recipe |
| `flat` | `(owner_idx, ingredient_ids, grams)` — all recipe-ingredient rows, for vectorised scoring with `np.bincount` |
| `recipes_using(ingredient_id)`, `mask_using_any(ids)` | Inverted index |
| `index_of(recipe_id)`, `recipe_id_of(idx)`, `info(idx)` | Boundary conversions and display fields |
| `steps(idx)` | Cooking instructions of one recipe from `recipes/recipe_step.parquet` (display only; `()` if the table is absent) |
| `non_dinner_like` | Boolean array: breakfast/brunch-tagged or named dough/batter/icing/… — a heuristic behind the opt-in `dinner_only` rule |

## Decisions

* **Two kinds of id, one rule.** Inside planning code a recipe is a dense *row index*; Food.com ids appear only at the
  boundary (`WeekPlan.recipe_ids`, the UI). Never keep both in one variable — an early bug (a shortlist position used
  as a catalogue index) was exactly this.
* **Arrays, not DataFrames,** in hot paths: a pandas row loop over 54K recipes costs seconds; numpy costs
  milliseconds.
* **Ingredient grams are estimates** (Food.com has no quantities; they are fitted — see `data/canonical/README.md`).
  The catalogue exposes them as they are; callers that need to know fitted vs prior should read `grams_basis` from the
  parquet.

## Limits

* Loads the whole recipe table once (a few hundred MB at most); fine for a single-user app, not for a multi-tenant
  server without sharing the instance.
* Read-only: it does not know about a user's history.

## Tests

[`tests/knowledge/test_recipes.py`](../tests/knowledge/test_recipes.md)

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added `steps(idx)` (the build already kept them; there was no runtime accessor) and the
  `non_dinner_like` heuristic array.
