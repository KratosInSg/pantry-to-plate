# `tests/knowledge/test_store.py`

Tests [`knowledge/store.py`](../../knowledge/store.md) against the real `data/canonical` build.

| Test | Pins |
| --- | --- |
| `test_missing_dataset_dir_raises` | clear `FileNotFoundError` instead of a Parquet error |
| `test_ingredient_lookup_and_flags` | group, allergens, vegetarian/vegan flags |
| `test_vegetarian_means_no_meat_no_fish_no_eggs` | egg, mayonnaise, egg noodle, salmon, shrimp, chicken are not vegetarian |
| `test_dairy_and_plants_are_vegetarian` | milk, paneer, butter, eggplant, spinach are |
| `test_unknown_ingredient_returns_none` | "not found" is `None`, never an exception |
| `test_assumed_available_staples` | salt is assumed in every kitchen, chicken is not |
| `test_alias_lookup_is_exact_and_lowercase` | the store does not guess; callers normalise |
| `test_salt_and_pepper_is_a_deliberate_split` | split aliases return two ids and are protected phrases |
| `test_unit_weight_prefers_generic_then_medium` | size preference order (small < medium < large) |
| `test_whole_item_weight` | cabbage → head, egg → each |
| `test_unit_definitions_cover_physical_units` | alias → canonical unit, kind, ml/g factors |
| `test_nutrition_per_100g_matches_usda` | egg ≈ 143 kcal, 12.6 g protein (USDA "Egg, whole, raw, fresh") |
| `test_default_shelf_life` | spinach = refrigerator 1–14 d; salt is indefinite |
| `test_fuzzy_candidates_are_parallel_and_filtered` | parallel tuples, large enough, includes "spinach" |

## Change log

- 2026-10-12 — Created.
- 2026-10-14 — Added the two vegetarian-definition tests.
