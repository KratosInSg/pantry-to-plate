# `tests/optimizer/test_replan.py`

Tests [`optimizer/replan.py`](../../optimizer/replan.md) on a fake catalogue (each test states its numbers by hand).

| Test | Pins |
| --- | --- |
| `test_cooked_dinners_leave_the_pantry_and_the_horizon_shrinks` | 100 g − 60 g cooked = 40 g; horizon 7 → 5; start weekday advances |
| `test_deadlines_shift_and_keep_what_we_knew_about_them` | `last_use_day − t`; known / confidence / urgency preserved |
| `test_stock_that_went_off_while_days_passed_is_dropped_and_reported` | expired stock removed from the pantry and listed in `expired_g` |
| `test_deadline_on_the_last_elapsed_day_is_still_usable_that_day_but_not_after` | inclusive deadline semantics |
| `test_a_skipped_day_consumes_nothing_but_the_clock_runs` | `None` day: nothing used, deadline still counts down |
| `test_a_rejected_dinners_ingredients_stay_and_keep_their_urgency` | a rejected (= not cooked) dinner leaves its food, one day closer to its deadline |
| `test_staples_are_not_carried` | ignored staples never enter the new pantry |
| `test_the_original_scenario_is_not_modified` | pure |
| `test_nothing_left_to_plan_is_an_error` | `ValueError` when no days remain |
| `test_scenario_id_records_the_roll_forward` | `…+d<t>` |

## Change log

- 2026-10-13 — Created.
- 2026-10-16 — Autouse fixture disables the real substitution table for the fake catalogue; added `test_a_cooked_dinner_that_used_a_substitution_used_up_the_substitutes`.
