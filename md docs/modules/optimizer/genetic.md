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

## Validation-only GA budget and seed experiments (2026-10-16)

The benchmark runner accepts `genetic_35_s0` through `genetic_35_sN` and `genetic_350_s0` through `genetic_350_sN`, with deterministic seeds. The `genetic` alias retains the original 35-generation, seed-42 behaviour. Longer runs retain the same initial population and 35-generation prefix as the corresponding short run; elitism ensures the **fitness score** cannot worsen for a fixed seed, but external evaluation metrics may change in either direction.

```bash
python -m pytest tests/optimizer/test_genetic.py -q
python src/evaluation/ga_objective_audit.py --limit 3 --planner genetic_35_s0
python src/evaluation/ga_multiseed.py --limit 24 --seeds 5 --generations 35,350
```

The audit builds the **actual** MILP model, fixes recipe/day binaries to the GA plan, then re-solves continuous inventory/slack variables. It prints GA replay fitness, the fixed-plan MILP objective, and their difference. A nonzero difference is evidence of nonidentical fitness accounting and must be reported or fixed before claiming identical objectives. The audit does not use hidden expiry truth.

The multiseed experiment runs the same 24 validation scenarios for greedy, MILP, and 5 independent seeds at each of 35 and 350 generations. It saves raw observations, per-seed means and across-seed mean/std/min/max CSVs. It also prints runtime. Because GA is stochastic, avoid claiming one seed is representative; compare means and variability. Do not tune on held-out test data. Tenfold more generations increases the evaluation budget; it does **not** guarantee GA beats MILP or improve every individual outcome.

## Change log

- 2026-10-16 — Created: GA weekly planner (benchmark comparison only).
- 2026-10-16 — Seed/generation variants (`genetic_35_sN`, `genetic_350_sN`); frozen configuration 350 generations, 20 % mutation (`md docs/evaluation_ga_frozen_v2.md`).
