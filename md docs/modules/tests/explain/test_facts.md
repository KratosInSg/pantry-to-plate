# `tests/explain/test_facts.py`

Tests [`explain/facts.py`](../../explain/facts.md). Plans are built by hand (`plan_from_indices`) where the test needs
to know the answer in advance, and from the real optimiser (the shared `optimised_week` fixture) where it needs the
solver's own numbers.

| Test | Pins |
| --- | --- |
| `test_pantry_use_and_deadlines_are_read_from_the_replay` | day-0 pantry uses equal the recipe's grams; deadline, stated-vs-estimated and "user said urgent" are carried |
| `test_week_totals_equal_the_inventory_replay_and_the_per_day_lists` | waste / consumed / grocery totals equal `account_inventory`; per-day groceries sum to the week's |
| `test_leftover_stock_that_will_expire_unused_is_reported` | 400 g spinach, deadline day 1, never cooked ⇒ exactly one `Leftover` of 400 g (precondition asserted, so not vacuous) |
| `test_stock_that_expires_before_a_dinner_needs_it_is_reported_as_rebought` | `Stranded` lists stock owned but past its deadline when the dinner needs it |
| `test_estimated_deadlines_are_listed_but_stated_ones_are_not` | `estimated_deadline_items` |
| `test_deadlines_beyond_the_plan_are_not_deadlines` | a deadline on day 20 creates no waste / caveat |
| `test_kcal_status_is_measured_against_the_users_own_band` (×3) | in range / below / above, and the gap in kcal |
| `test_protein_shortfall_is_the_distance_to_the_minimum` | gap = 10 g when the minimum is 10 g above; 0 when met |
| `test_weekday_time_limit_applies_to_weekdays_only` | 10 min over on Monday; 0 on Saturday |
| `test_preference_reasons_are_the_scorers_own_components` | liked/disliked cuisine and ingredient names |
| `test_rule_counts_come_from_the_hard_rule_masks` | rule names/counts and `n_allowed` equal `violation_masks` |
| `test_a_plan_that_breaks_a_rule_is_reported_as_such` | `violations ≥ 1` for a meat dinner on a vegan profile |
| `test_no_plan_still_explains_the_rules` | empty plan: no days, status `no_candidates`, rule counts present |
| `test_solver_facts_carry_the_optimisers_cost_terms` | all `COST_TERMS` present and summing to the objective |
| `test_baselines_have_no_solver_facts` | a random plan has `solver is None` |
| `test_optimiser_plan_facts_are_complete_and_safe` | 7 dinners, 0 violations, ids match the plan |

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Added `test_assumed_quantities_are_listed_but_stated_ones_are_not`.
