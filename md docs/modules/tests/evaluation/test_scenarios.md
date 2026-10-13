# `tests/evaluation/test_scenarios.py`

Tests [`evaluation/scenarios.py`](../../evaluation/scenarios.md). Uses a 16-scenario mini benchmark and `tmp_path` for
freeze tests; one test checks the committed benchmark itself.

| Test | Pins |
| --- | --- |
| `test_generation_is_a_pure_function_of_family_and_seed` | same input → byte-identical JSON; different seed differs |
| `test_every_family_yields_a_valid_scenario` | (8 families) non-empty pantry, no staples, no excluded ingredients, stock cap respected, truth for every item |
| `test_known_dates_are_the_truth_and_estimates_are_flagged` | known → equals hidden truth, confidence 1; estimates carry < 1 |
| `test_the_pool_of_infeasible_combo_is_small_but_a_week_is_still_possible` | ≥ 7 feasible recipes, median < 5 % of the catalogue |
| `test_benchmark_has_every_family_in_equal_numbers` | |
| `test_split_is_stratified_disjoint_and_deterministic` | per-family balance, no overlap |
| `test_freeze_writes_hashes_refuses_overwrite_and_detects_tampering` | `FROZEN.json`, `FileExistsError`, `RuntimeError` on a modified file |
| `test_load_split_rejects_an_unknown_split` | only `validation` / `test` |
| `test_repository_benchmark_is_intact_and_balanced` | the committed v1 loads (hashes verified), 120 + 120, 15 + 15 per family |

## When this test legitimately changes

Only when `BENCHMARK_VERSION` is bumped and a new benchmark is frozen: update the expected counts in the last test.

## Change log

- 2026-10-12 — Created.
