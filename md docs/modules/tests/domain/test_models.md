# `tests/domain/test_models.py`

Tests [`domain/models.py`](../../domain/models.md). Pure unit tests; no dataset needed.

| Test | Pins |
| --- | --- |
| `test_dinner_target_and_band_follow_the_profile` | 2000 kcal × 30 % = 600; ±20 % band = 480–720 |
| `test_profile_rejects_an_unknown_allergen` | a typo can never silently disable a safety rule |
| `test_profile_accepts_every_known_allergen` | valid subsets pass |
| `test_profile_rejects_absurd_calorie_targets` | `daily_kcal_target` bounds |
| `test_defaults_are_the_least_restrictive_profile` | omnivore, no allergens/exclusions/time cap |
| `test_pantry_item_needs_positive_grams` | zero-gram stock is invalid |
| `test_is_weekday_respects_the_start_weekday` | Monday-start and Friday-start week patterns |
| `test_scenario_horizon_is_bounded` | `horizon_days >= 1` |
| `test_week_plan_completeness` | `is_complete` for ok/optimal/feasible, not for partial/infeasible/empty |

## Change log

- 2026-10-12 — Created.
- 2026-10-16 — Added `test_a_rated_dinner_needs_a_five_star_rating_and_cannot_be_changed` and `test_rated_dinners_default_to_none_and_survive_a_json_round_trip` (old scenarios without the field still load).
