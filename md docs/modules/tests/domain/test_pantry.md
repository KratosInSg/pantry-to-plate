# `tests/domain/test_pantry.py`

Tests [`domain/pantry.py`](../../domain/pantry.md). Builds `ParsedItem`s directly (deterministic, independent of the
parser) with real ingredient ids from the `store` fixture.

| Test | Pins |
| --- | --- |
| `test_shelf_life_halved_for_unknown_age` | 3–5 d → last day index 1, 10–14 d → 5; confidence by shelf-life link quality |
| `test_long_shelf_life_means_no_deadline` | 20–30 d → `None` |
| `test_missing_or_indefinite_shelf_life_means_no_deadline` | `None` shelf / indefinite → no deadline |
| `test_deadline_is_never_negative` | sub-day shelf lives clamp to day 0 |
| `test_stated_date_is_a_known_hard_deadline` | explicit date → known, confidence 1.0 |
| `test_qualitative_cue_is_a_soft_estimate` | "getting old" → not known, confidence 0.6 |
| `test_stated_date_beyond_the_horizon_is_known_but_not_binding` | "in 2 weeks" → `None`, still flagged known |
| `test_leftovers_get_the_food_safety_default` | 3 days |
| `test_frozen_food_has_no_deadline_this_week` | freezer → `None` |
| `test_no_cue_falls_back_to_the_foodkeeper_default` | agrees with `estimate_last_use_day` of the store's default |
| `test_unusable_items_are_skipped_with_a_reason` | unknown / ambiguous / no amount / unsafe each skipped with its reason |
| `test_duplicates_merge_grams_and_keep_the_earliest_known_deadline` | grams add, earliest deadline, known beats estimate, most urgent level |

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added tests for the carried `quantity_assumed` flag, merging, the `SKIP_*` reason constants, and `make_pantry_item` (stated date = known/hard; vague cue = estimate 0.6; none = FoodKeeper estimate).
