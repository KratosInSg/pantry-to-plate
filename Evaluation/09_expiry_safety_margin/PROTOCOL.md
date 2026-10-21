# 09 · Expiry safety margin: protocol (written 2026-10-21, before any run)

**Problem.** In 03_robustness the expiry-aware MILP degraded *more* than the MILP without the expiry term when food
spoiled 1–2 days early (+18.6 g [5.4, 35.0] and +15.7 g [5.8, 26.8] waste), so measure 8 of the proposal ("less
degradation than the planner without expiry awareness") was not met.

**Remedy under test.** `estimate_margin_days` in `src/optimizer/weekly.py`: plan every *estimated* deadline inside the
week `m` days early (clamped at day 0). Known use-by dates are unchanged. Planners `opt_margin1` and `opt_margin2`.

**Step 1: selection on the v2 validation split (all 120 scenarios), seed 0 perturbations.**
Command: `python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_margin1,opt_margin2,opt_no_expiry --save`

Rule, fixed now:
1. Guards on the nominal kitchen, relative to `optimiser` (margin 0): mean waste no more than 2 % higher, extra
   grocery items no more than +0.5 per week, dinners in the calorie band no more than 2 points lower.
2. Among the candidates that pass the guards, pick the one with the lowest mean waste degradation averaged over
   `expiry_1d_early` and `expiry_2d_early`. Ties (within 1 g) go to the smaller margin.
3. If no candidate passes the guards, no margin is adopted and that is reported.

**Step 2: one run on the fresh v3 benchmark** (`data/evaluation/v3`, 120 new scenarios, never used before), same
perturbations and seed:
`python src/evaluation/robustness.py --eval-dir data/evaluation/v3 --split test --planners greedy,optimiser,opt_marginK,opt_no_expiry --save`

Success measure (the proposal's): the chosen variant's waste degradation minus `opt_no_expiry`'s, paired bootstrap 95 %
CI, for `expiry_1d_early` and `expiry_2d_early`. **Met** if the mean difference is ≤ 0 for both; the CIs are reported
either way. The nominal cost of the margin (waste, grocery items, calorie band, preference versus `optimiser`) is
reported alongside.

## Step 1 outcome (2026-10-21, before the v3 run)

Validation (v2, 120 scenarios), nominal kitchen versus `optimiser` (waste 723.1 g, 15.69 items, 72.0 % in band):

| Candidate | Waste | Items | Calorie band | Guards | Mean waste degradation, 1 d & 2 d early |
| --- | --- | --- | --- | --- | --- |
| `opt_margin1` | 723.6 g (+0.1 %) | 15.42 | 70.8 % (−1.2) | pass | (8.7 + 11.8) / 2 = 10.3 g |
| `opt_margin2` | 721.6 g (−0.2 %) | 15.63 | 70.2 % (−1.8) | pass | (6.4 + 10.4) / 2 = 8.4 g |

**Chosen: `opt_margin2`** (lower degradation by more than 1 g). Step 2 runs `greedy,optimiser,opt_margin2,opt_no_expiry`.
