# `tests/optimizer/test_planning_and_baselines.py`

Tests [`optimizer/planning.py`](../../optimizer/planning.md) and [`optimizer/baselines.py`](../../optimizer/baselines.md)
against the real dataset (`ctx` fixture).

| Test | Pins |
| --- | --- |
| `test_context_knows_the_assumed_available_staples` | `ignore_ids` == the `is_assumed_available` ingredients |
| `test_prepare_applies_the_hard_rules_and_scores_preferences` | feasible mask + preference array shape |
| `test_plan_from_indices_statuses` | `ok` / `partial` / `no_candidates`, Food.com id conversion, diagnostics |
| `test_baselines_are_deterministic_distinct_and_safe` | (random, greedy) same scenario → same plan; 7 distinct; 0 violations for a vegetarian + peanut + dairy user |
| `test_random_planner_varies_with_the_scenario_seed` | different scenario seeds → different weeks |
| `test_greedy_cooks_what_the_pantry_covers` | with one recipe's ingredients stocked, day 0 needs nothing it lacks |
| `test_empty_feasible_set_is_reported_as_no_candidates` | a 4-minute cap (shortest recipe is 5) leaves nothing |
| `test_fewer_than_a_week_of_options_is_reported_as_partial` | tiny feasible set → `partial`, one dinner per option |

## Change log

- 2026-10-12 — Created.
