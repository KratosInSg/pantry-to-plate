# `tests/knowledge/test_recipes.py`

Tests [`knowledge/recipes.py`](../../knowledge/recipes.md) against the real `data/canonical` build (uses the `catalog`
fixture).

| Test | Pins |
| --- | --- |
| `test_catalog_is_sorted_and_arrays_are_aligned` | ascending ids (stable row index); every array has length `n` |
| `test_index_round_trip_and_unknown_id` | `index_of` / `recipe_id_of` are inverses; unknown id → `KeyError` |
| `test_every_documented_flag_is_available` | all `FLAG_COLUMNS` are boolean arrays; unknown flag → `KeyError` |
| `test_vegan_implies_vegetarian` | consistency of the dataset flags |
| `test_ingredients_are_parallel_and_unique` | one row per ingredient per recipe, non-negative grams |
| `test_flat_arrays_agree_with_per_recipe_slices` | the vectorisation hook equals `ingredients(idx)` |
| `test_inverted_index_matches_the_ingredient_lists` | `recipes_using` both ways |
| `test_mask_using_any_is_the_union` | union of inverted-index hits |
| `test_info_returns_display_fields` | `RecipeInfo` content and rating range |

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added `test_every_recipe_has_cooking_steps_of_the_stated_length` (steps exist for sampled recipes and match `n_steps`) and `test_steps_for_a_recipe_without_a_step_table_are_empty_not_an_error`.
