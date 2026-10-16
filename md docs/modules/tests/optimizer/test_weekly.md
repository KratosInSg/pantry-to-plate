# `tests/optimizer/test_weekly.py`

Tests [`optimizer/weekly.py`](../../optimizer/weekly.md): real models on real scenarios (each solve is a few seconds,
so the shortlist is kept at 50).

| Test | Pins |
| --- | --- |
| `test_plan_is_a_complete_distinct_and_safe_week` | 7 distinct dinners, status optimal/feasible, **0 hard-rule violations** |
| `test_model_cost_terms_agree_with_the_inventory_replay` | the model's waste / grocery numbers match the independent replay (≤ 2 g) — the explainer reads the model, the evaluation re-measures; they must tell one story |
| `test_diagnostics_record_how_the_plan_was_made` | the keys the explainer relies on |
| `test_cost_terms_are_reported_and_sum_to_the_objective` | `cost_<term>` for every `COST_TERMS`, none negative, summing to `objective` — the decomposition the explainer cites |
| `test_stock_is_never_planned_past_its_deadline` | **structural** guarantee: a stock with `last_use_day = 1` gets use variables for days 0–1 only |
| `test_expiring_stock_is_pulled_into_the_plan` | one recipe's ingredients, all expiring: the optimiser wastes < 60 % and less than random |
| `test_make_planner_names` | `optimiser`, `opt_<ablation>`, unknown → `ValueError` |
| `test_cpsat_suffix_selects_the_backend_and_keeps_the_name` | `_cpsat` suffix → CP-SAT backend, name kept in `plan.method`; unknown backend → `ValueError` |
| `test_cpsat_backend_plans_a_safe_week_that_matches_highs` | same scenario on CP-SAT: complete, 0 violations, model terms match the replay, objective no worse than HiGHS's beyond the gaps (skipped if OR-Tools cannot load) |
| `test_nothing_feasible_is_reported_not_solved` | `no_candidates`, no solver call |
| `test_hard_rules_hold_for_a_restricted_user` | vegan + soy + gluten → every dinner vegan, 0 violations |

## Notes

* The cross-check test is the safeguard against the optimiser quietly optimising something other than what the
  evaluation measures.
* Solve-time and gap are deliberately **not** asserted: they depend on the machine; the benchmark runner reports them.

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added the CP-SAT backend tests (suffix selection; cross-check against HiGHS).
- 2026-10-13 — Added the cost-term decomposition test.

- 2026-10-16 — Added regression test that unavoidable expiring pantry stock absent from candidate demand contributes to the MILP's constant waste cost.
