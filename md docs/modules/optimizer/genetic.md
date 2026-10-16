# Genetic weekly planner

Implementation: `src/optimizer/genetic.py`; tests: `tests/optimizer/test_genetic.py`.

The `genetic` planner is an independent heuristic comparison to the existing greedy and HiGHS MILP methods. It shares `prepare()` hard-rule filtering, preference scores, the MILP's 120-recipe shortlist, default objective weights, and the same pantry accounting definitions. No new package is required (NumPy).

Each chromosome contains one distinct feasible recipe index per day. Initialization samples without replacement. Tournament selection, two-point crossover, duplicate repair, random replacement mutation and elitism evolve weekly plans. Seed 42 combined with the scenario seed makes each run reproducible. Defaults: population 48, 35 generations, 3 elites, tournament size 3, mutation probability 0.20.

Fitness minimises the MILP's six objective categories: urgency/confidence-weighted expiring waste, grocery item count and grams, kcal/protein deviations, preference penalty, weekday overtime and variety excess. It uses only visible expiry dates, not the evaluation's hidden true dates. Fitness uses actual day-by-day pantry replay. This is a heuristic approximation of the MILP model, **not** an exact identical formulation or an optimality certificate. In particular, the MILP optimises pantry use variables jointly; GA fitness consumes available pantry stock greedily by day. Evaluation metrics are recomputed by the shared evaluator for all planners.

Run the 24-scenario validation comparison:

```bash
python -m pytest tests/optimizer/test_genetic.py -q
python src/evaluation/runner.py --split validation --planners greedy,optimiser,genetic --baseline greedy --limit 24 --save
```

Results are saved in `data/evaluation/v2/runs/`. Do not tune on the held-out test split. For stochastic variability experiments, repeat GA with different `GAConfig(seed=...)` values and report distributions, not just the best run. The runner's default `genetic` is one fixed seed.

The GA does not currently replace the Streamlit application's MILP planner; this first iteration is for benchmark comparison.
