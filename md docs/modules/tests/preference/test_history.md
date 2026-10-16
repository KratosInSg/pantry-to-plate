# `tests/preference/test_history.py`

Tests [`src/preference/history.py`](../../preference/history.md).

## What it checks

| Test | Guarantees |
| --- | --- |
| `test_base_rates_are_shares_of_the_pool` | base rates are plain shares; an empty pool is allowed |
| `test_a_like_needs_support_and_lift` | an ingredient everyone has (lift 1) and a rare one (support 10 %) are not likes; the evidence records support, base rate and lift |
| `test_low_ratings_staples_and_unknown_ingredients_never_become_likes` | ratings below 4, staples and ingredients with no base rate never become likes |
| `test_too_short_a_history_derives_nothing` | fewer than `min_dishes` liked dishes gives empty likes, and the count is reported |
| `test_cuisines_must_be_in_the_catalogue_vocabulary` | unknown cuisine tags are dropped when a vocabulary is given |
| `test_the_strongest_likes_are_kept_and_the_order_is_deterministic` | the cap keeps the strongest; ties are broken by key |
| `test_derived_likes_plug_into_the_existing_scorer` | the profile fields work with `score_recipes` unchanged (real catalogue) |
| `test_history_similarity_is_a_cosine_in_zero_one` | range, dtype, and a recipe identical to the history scores 1 and ranks top |
| `test_history_similarity_ignores_low_ratings_and_needs_known_ingredients` | low ratings, an empty history and a staples-only history give all zeros |
| `test_nearest_dishes_puts_a_recipe_identical_to_a_liked_dish_at_the_top` | range, dtype, and an identical recipe gets the maximum |
| `test_nearest_dishes_keeps_two_different_tastes_apart` | with k = 1, two very different liked dishes both reach the top 0.1 % |
| `test_nearest_dishes_uses_whichever_evidence_exists` | tags alone work; without tags the score equals the ingredient-only setting exactly |
| `test_nearest_dishes_needs_liked_known_evidence` | empty, low-rated or entirely unknown histories give all zeros |

## Change log

- 2026-10-16 — Created.
- 2026-10-16 — Added the four `nearest_dish_scores` tests.
- 2026-10-16 — Added `test_nearest_rated_names_the_closest_liked_dishes_first`.
