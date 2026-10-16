# 07 · Genetic algorithm: how its configuration was chosen

The genetic algorithm (`src/optimizer/genetic.py`) is the proposal's alternative optimisation technique. It searches
over weeks of 7 distinct shortlisted recipes and minimises the same six cost terms as the MILP, using the same pantry
accounting and hard rules.

| | |
| --- | --- |
| Data | Frozen benchmark v2 · **validation split** · 24 scenarios × 5 seeds |
| Date / code | 2026-10-16 · `src/evaluation/ga_hyperparams.py`, `src/evaluation/ga_multiseed.py`, `src/evaluation/ga_objective_audit.py` |
| Commands | `python src/evaluation/ga_hyperparams.py --limit 24 --seeds 5 --generations 350` · `python src/evaluation/ga_multiseed.py --limit 24 --seeds 5 --generations 35,350` |
| Rows | The sweep's raw CSVs are not in this working copy, so they are not included. The decision and its numbers are recorded below and in `md docs/evaluation_ga_frozen_v2.md`. Re-run the commands above to regenerate them |

## Frozen configuration

| Setting | Value |
| --- | --- |
| Population | 48 |
| Generations | 350 |
| Mutation probability | 0.20 (probability of changing one gene per child) |
| Tournament size | 3 |
| Elitism | 3 |
| Default seed | 42 (other seeds supported for uncertainty analysis) |
| Shortlist | the MILP's 120-recipe shortlist |
| Objective weights | `optimizer.weekly.DEFAULT_WEIGHTS`, unchanged |

**Why this one.** It is a speed-oriented compromise with strong nutrition and food-waste results. Population 96 at 20 %
mutation reached a marginally better weighted fitness (51.294 vs 51.536; lower is better) but took almost twice as long
(0.884 vs 0.465 s per plan). Population 48 at 35 % mutation scored 51.383 but had worse nutrition and waste. The choice
weighs those outcomes and speed over the weighted score alone. The sweep compared mutation rates 0.10 / 0.20 / 0.35 and
populations 48 / 96, at 350 generations, on the same 24 scenarios and 5 seeds.

## Caveats

- The GA approximates the MILP's objective rather than replicating it: the MILP optimises pantry use jointly, while the
  GA's fitness takes pantry stock greedily day by day. `ga_objective_audit.py` measures the difference with the
  recipe-day choices fixed.
- The comparison with greedy and the MILP on all 120 validation scenarios, including 5-seed variability, is in
  [01_planner_comparison](../01_planner_comparison/README.md).
