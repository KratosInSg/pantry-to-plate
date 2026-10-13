# `tests/evaluation/test_runner.py`

Tests [`evaluation/runner.py`](../../evaluation/runner.md). Baselines only (fast); the optimiser is covered in
`test_weekly.py`.

| Test | Pins |
| --- | --- |
| `test_build_planner_registry` | known names resolve, unknown → `ValueError` |
| `test_run_covers_every_family_for_every_planner` | `--limit` is stratified: all 8 families × both planners; baselines have 0 violations; timing recorded |
| `test_report_prints_the_comparison` | the overall table, the pooled paired comparison and the per-family section are printed |
| `test_per_family_comparison_has_one_row_per_family` | one row per family, `n` per family, cells read `mean [low, high]` |

## Change log

- 2026-10-12 — Created.
- 2026-10-12 — Added the per-family comparison test.
