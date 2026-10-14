# `tests/evaluation/test_metrics.py`

Tests [`evaluation/metrics.py`](../../evaluation/metrics.md) with hand-built single-dinner plans and synthetic
DataFrames.

| Test | Pins |
| --- | --- |
| `test_a_fully_stocked_dinner_needs_nothing_and_wastes_nothing` | 100 % utilisation, 0 groceries, 0 waste, 0 violations |
| `test_an_empty_pantry_means_everything_is_bought` | 0 % utilisation, groceries > 0 |
| `test_waste_is_measured_against_the_hidden_truth_not_the_planners_belief` | visible "no deadline" + true day 0 → all 400 g wasted; without truth → 0 |
| `test_violations_are_counted` | a non-vegan dinner for a vegan counts |
| `test_disliked_rate_and_preference` | |
| `test_weekend_dinners_do_not_count_as_weekday_overtime` | Saturday start → 0; Monday start → 1 |
| `test_incomplete_plans_are_flagged` | 3 of 7 meals → `complete == 0` |
| `test_nutrition_band_metrics` | one in-band + one out-of-band dinner → 50 % |
| `test_paired_bootstrap_*` (3) | direction, interval contains the true difference, only shared scenarios are paired |
| `test_summarise_groups_by_planner` | |

## Change log

- 2026-10-12 — Created.
- 2026-10-14 — Added `test_waste_is_split_into_avoidable_and_unavoidable` (vegan user, chicken vs spinach).
