# `tests/evaluation/test_taste_users.py`

Tests [`src/evaluation/taste_users.py`](../../evaluation/taste_users.md).

## What it checks

| Test | Guarantees |
| --- | --- |
| `test_ingredient_text_maps_whole_names_first_then_parses` | "cream cheese" stays whole; preparation words are dropped; unknown text maps to nothing |
| `test_catalogue_names_link_only_unambiguous_names` | a name shared by several catalogue recipes is not linked |
| `test_build_recipes_keeps_main_dishes_and_maps_tags_and_names` | desserts are dropped; only catalogue cuisine names are kept; name links and statistics are correct |
| `test_the_split_is_by_date_earliest_first` | history = earliest ratings |
| `test_select_users_needs_enough_dinners_and_checkable_later_ones` | qualification rules; fails loudly when too few qualify; history must leave held-out dinners |
| `test_held_out_dinners_already_linked_from_the_history_do_not_count` | no leakage through two MealRec dishes that link to one catalogue recipe |
| `test_user_split_is_deterministic_and_disjoint` | the validation/test split |
| `test_freeze_and_load_round_trip_and_refuse_tampering` | freeze, verified load, refusal to overwrite, invalid split name, tamper detection |
| `test_v2_has_the_same_users_and_dinners_as_v1_plus_tags` | when both sets exist: identical users, splits and dinners apart from the added tags; over 95 % of dinners tagged |
| `test_the_frozen_taste_set` | when built: 100 users split evenly, 80 history dinners each, history before held-out, at least 3 checkable held-out dinners |

## Change log

- 2026-10-16 — Created.
- 2026-10-16 — Tags are checked in `build_recipes` and the frozen set. Added the v1/v2 identity test. The tamper test follows `TASTE_VERSION`.
- 2026-10-16 — Added `test_rated_dinners_are_what_a_profile_carries`.
