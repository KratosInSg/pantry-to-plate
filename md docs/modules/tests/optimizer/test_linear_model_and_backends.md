# `tests/optimizer/test_linear_model_and_backends.py`

Tests [`optimizer/linear_model.py`](../../optimizer/linear_model.md),
[`optimizer/backends.py`](../../optimizer/backends.md) and [`optimizer/cpsat_worker.py`](../../optimizer/cpsat_worker.md)
on problems small enough to solve by hand. No dataset.

Every solver behaviour is parametrised over **both backends** (HiGHS and CP-SAT with `workers=1`, so deterministic):
the formulation must mean the same thing to each. CP-SAT cases are *skipped*, not failed, where OR-Tools cannot be
loaded; availability is probed in a child process, because in the test process pandas/pyarrow are loaded and OR-Tools
cannot be imported next to them.

| Test | Pins |
| --- | --- |
| `test_builder_bookkeeping` | counts, accumulated costs, array export, objective value |
| `test_repeated_variables_in_a_row_are_summed_and_zeros_dropped` | row normalisation |
| `test_knapsack_is_solved_to_optimality` (×2) | binaries: best of 3 items under a capacity (value 10) |
| `test_continuous_variables` (×2) | LP optimum x = 1, y = 1.5, cost 1.9 |
| `test_a_model_without_constraints_still_solves` (×2) | the empty-constraint path |
| `test_infeasible_model_is_reported_not_raised` (×2) | status `infeasible`, no solution |
| `test_negative_costs_and_equality_rows` (×2) | negative costs (waste avoided) and `== 1` rows, as in the weekly model |
| `test_cpsat_matches_highs_on_a_mixed_model` | binary + continuous flow + big-M link: same objective from both solvers |
| `test_cpsat_is_not_made_infeasible_by_a_boundary_tight_buy_bound` (×4) | **regression**: float32 / 3-decimal gram bound next to a `buy ≥ demand` row (verified to fail on the old inward rounding) |
| `test_cpsat_reads_back_continuous_values_at_model_scale` | scaled integers are mapped back to model units |
| `test_cpsat_rounds_row_bounds_inwards_never_loosening_them` | `ub = 2.999` → solution never exceeds it |
| `test_cpsat_refuses_to_silently_drop_a_tiny_coefficient` | `ValueError`, not a deleted row |
| `test_cpsat_refuses_a_cost_that_scales_to_zero` | `ValueError`, not a deleted objective term |
| `test_cpsat_reports_rounding_and_status_in_the_message` | the scale used is visible to the caller |
| `test_worker_reports_unloadable_ortools_in_its_result_file` | an OS-refused DLL becomes `status=unavailable`, not a traceback |
| `test_unavailable_worker_becomes_a_clear_error_and_highs_still_works` | parent raises `BackendUnavailableError`; HiGHS unaffected |
| `test_a_crashing_worker_is_reported_not_swallowed` | non-zero exit → `BackendUnavailableError("worker failed")` |
| `test_backend_registry_names` | `BACKENDS` keys |

## Notes

* The boundary-tight regression exists because the first CP-SAT implementation passed every other test here and still
  produced a wrong "optimal"; it was only found by comparing with HiGHS on real scenarios
  (`test_weekly.py::test_cpsat_backend_plans_a_safe_week_that_matches_highs` is the integration-level cross-check).

## Change log

- 2026-10-12 — Created. (The first LP test had a wrong hand-computed optimum; the solver was right — fixed the test.)
- 2026-10-13 — Parametrised over both backends; added CP-SAT scaling, regression and availability tests.
