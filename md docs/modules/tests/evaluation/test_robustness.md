# `tests/evaluation/test_robustness.py`

Tests [`src/evaluation/robustness.py`](../../evaluation/robustness.md).

## What it checks

| Test | Guarantees |
| --- | --- |
| `test_nominal_is_the_scenario_itself` | the nominal kitchen is the unchanged scenario and is part of the standard set |
| `test_earlier_expiry_moves_only_estimated_deadlines_inside_the_week` | known dates, "no deadline" and beyond-the-week deadlines are untouched; clamped at day 0; the input is not modified |
| `test_quantity_perturbation_changes_grams_but_nothing_the_planner_saw` | grams scale; visible deadlines, confidence, urgency, profile and truth stay |
| `test_random_perturbations_are_reproducible_and_seeded` | same seed gives the same reality, a different seed a different one; jitter never touches known / no-deadline items |
| `test_spoiling_earlier_costs_a_plan_that_relied_on_the_stock` | a real recipe whose stock spoils before its day buys more and wastes more |
| `test_degradation_is_positive_when_worse_whichever_way_the_metric_points` | the sign convention, for a lower-is-better and a higher-is-better metric |
| `test_run_robustness_end_to_end` | shape of the results; nominal rows equal the ordinary benchmark metrics; less stock never means less to buy; summary and paired tables; the report prints |
| `test_a_run_without_the_nominal_kitchen_is_refused` | degradation needs a nominal baseline |

## Change log

- 2026-10-16 — Created.
