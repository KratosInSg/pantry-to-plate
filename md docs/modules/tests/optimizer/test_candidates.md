# `tests/optimizer/test_candidates.py`

Tests [`optimizer/candidates.py`](../../optimizer/candidates.md) with a tiny fake catalogue (only `n`, `flat`, `kcal`,
`cuisine`, `recipes_using`), so every number is hand-checkable.

| Test | Pins |
| --- | --- |
| `test_urgency_weight_scale` | 1.0 (no deadline) … 3.0 (known, today); a guess is worth chasing less |
| `test_coverage_is_the_share_of_mass_the_pantry_supplies` | half-covered recipe → 0.5 |
| `test_coverage_is_capped_by_available_stock` | 40 g of 100 g → 0.4; excess stock doesn't exceed 1 |
| `test_urgent_stock_counts_more_than_ordinary_stock` | same share, urgent half ranks higher |
| `test_ignored_ingredients_do_not_inflate_coverage` | staples excluded from numerator and denominator |
| `test_nutrition_fit_peaks_at_the_target` | 1 at target, 0.5 at half, 0 at ±100 % |
| `test_small_feasible_set_is_returned_whole` | no needless dropping |
| `test_shortlist_takes_the_best_and_never_an_infeasible_recipe` | feasibility is absolute |
| `test_urgent_ingredient_always_has_options_even_if_they_rank_low` | the pantry-aware guarantee |
| `test_no_cuisine_floods_the_shortlist` | `max_cuisine_share` cap |

## Change log

- 2026-10-12 — Created.
