# `src/evaluation/runner.py`

## Purpose

Run planners over a frozen split and print / save the comparison.

```bash
python src/evaluation/runner.py --split validation --planners random,greedy,optimiser --limit 24
python src/evaluation/runner.py --split validation --planners greedy,optimiser,opt_no_expiry,opt_no_nutrition,opt_no_preference --save
```

## Options

| Flag | Meaning |
| --- | --- |
| `--split validation\|test` | Which frozen split. `test` prints a reminder: run it once, after weights are frozen |
| `--planners a,b,c` | `random`, `greedy`, `optimiser`, `opt_no_expiry`, `opt_no_nutrition`, `opt_no_preference`; add `_cpsat` to any optimiser name to solve it with CP-SAT instead of HiGHS (`optimiser_cpsat`) |
| `--limit N` | At most N scenarios, **taken evenly from each family** so a small run still covers all eight |
| `--baseline NAME` | Reference for the paired comparison (default `greedy`) |
| `--save` | Write per-scenario results to `data/evaluation/runs/<timestamp>_<split>.csv` |
| `--eval-dir PATH` | Folder holding another frozen benchmark (e.g. a draft) |

## Output

Overall means, per-family means, then for every other planner a paired comparison against the baseline: pooled (mean
difference, 95 % bootstrap CI, share of scenarios where it is better) **and per family** (`per_family_comparison`,
required by `md docs/evaluation.md`: a method can win overall and still lose in the family that matters to one user),
then seconds per plan. With 15 scenarios per family the per-family CIs are wide; read a CI that excludes 0 as a real
difference and one that straddles it as "not distinguishable at this sample size".

## Extending

Add a method by adding a branch to `build_planner` — the planner only has to implement `name` and
`plan(scenario) -> WeekPlan` (see `optimizer/planning.py`).

## Tests

[`tests/evaluation/test_runner.py`](../tests/evaluation/test_runner.md)

## Change log

- 2026-10-12 — Created.
- 2026-10-12 — Added `per_family_comparison` and the per-family section of the report.
- 2026-10-13 — `build_planner` routes any name starting `optimiser` / `opt_` to the weekly factory, so the `_cpsat`
  suffix variants work.
