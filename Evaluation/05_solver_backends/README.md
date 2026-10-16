# 05 · Solver backends: HiGHS vs OR-Tools CP-SAT (same model, same weights)

The weekly MILP is solver-agnostic. HiGHS (in-process, default) and CP-SAT (child process) solve the identical model.
The question is whether the choice of solver changes the plans.

| | |
| --- | --- |
| Data | Frozen benchmark v1 (same scenarios as v2) · **validation split** · 48 scenarios (6 per family) |
| Settings | Shortlist 120 recipes · 8 s limit · 2 % gap · weights as of 2026-10-13 (before the 2026-10-14 vegetarian-rule change) |
| Date / code | 2026-10-13 · `src/optimizer/backends.py`, `src/optimizer/cpsat_worker.py` |
| Command (plan quality) | `python src/evaluation/runner.py --split validation --planners greedy,optimiser,optimiser_cpsat --limit 48 --baseline greedy --save` |
| Rows | [`plan_quality_validation.csv`](plan_quality_validation.csv) |

## Solver-only comparison (identical built models)

"True gap" is measured against the best objective *any* configuration found on that scenario. Produced by a one-off
script that is not in the repository; the numbers were recorded at the time.

| Configuration | Proved optimal | Mean s | Mean true gap | p90 true gap | Within 0.5 % of best |
| --- | --- | --- | --- | --- | --- |
| HiGHS (default) | 62 % | 5.8 | 0.38 % | 1.3 % | 41 / 48 |
| CP-SAT, 8 workers | 60 % | 6.0 | 0.51 % | 1.4 % | 40 / 48 |
| CP-SAT, 1 worker | 2 % | 9.6 | 17.6 % | 31.5 % | 3 / 48 |
| CP-SAT, 8 workers, 30 s (reference) | 85 % | 10.6 | 0 | 0 | 48 / 48 |

HiGHS and 8-worker CP-SAT return the same objective on 34 / 48 scenarios. HiGHS is strictly better on 6 and CP-SAT on 8.

## Plan quality

| Method | Waste (g) | Extra grocery items | Pantry used % | Dinners in kcal band % | Preference | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Greedy | 736 | 24.2 | 26.2 | 4.5 | 0.53 | 0 | 0.08 |
| MILP (HiGHS) | 682 | 13.3 | 16.9 | 58.0 | 0.57 | 0 | 5.6 |
| MILP (CP-SAT) | 679 | 13.1 | 17.2 | 56.3 | 0.58 | 0 | 5.5 |

Paired CP-SAT − HiGHS (95 % bootstrap CI, n = 48):
- waste −3 g [−14, +7]
- grocery items −0.21 [−0.42, 0.00]
- kcal-in-band −1.8 pts [−4.5, +0.6]
- preference 0.00

**No difference is distinguishable from zero**, and waste is identical in 31 / 48 scenarios.

## How to read it

- At these settings the solver choice does not change the plans. **HiGHS stays the default** (in-process, no
  start-up cost). CP-SAT is kept as an independent cross-check, and it already caught a modelling discrepancy once.
- HiGHS's "loose proven gap" is a loose *bound*, not a loose plan: its plans are within about 0.4 % of the best found.
- CP-SAT's edge, if any, is parallelism: with one worker it is far worse. HiGHS is single-threaded, while CP-SAT used 8
  workers on a 32-core machine, so this is not equal compute.

## Caveats

These results predate the current weights and vegetarian rule. The conclusion is about solvers on an identical model,
so it is not expected to change.
