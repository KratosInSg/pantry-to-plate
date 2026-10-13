# `tests/app/test_grocery.py`

Tests [`app/grocery.py`](../../app/grocery.md) against the inventory replay on a fake catalogue, so every number is
stated by hand.

| Test | Pins |
| --- | --- |
| `test_items_match_the_replay_exactly` | grams per item, `n_items` and `total_g` equal the replay's |
| `test_first_needed_day_and_weekday_name` | first day an item is short, mapped through the start weekday; sorted soonest first |
| `test_pinches_are_flagged_minor_but_still_listed` | < `MINOR_GROCERY_G` is `minor`; count unchanged |
| `test_grouping_is_by_food_group_with_a_default_for_unknown` | `by_group()` sorted; unknown group → `other`; unknown ingredient named `ingredient <id>` |
| `test_a_plan_that_needs_nothing_has_an_empty_box` | empty box, zero totals |

## Change log

- 2026-10-13 — Created.
