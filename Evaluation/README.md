# Pantry-to-Plate — Evaluation results

This folder is the results package for the report. Each sub-folder holds one evaluation: a README with the question,
the set-up, the tables (with 95 % confidence intervals), how to read them and the caveats, plus the raw per-scenario
CSV so every number can be recomputed. The design behind the evaluation is in [`md docs/evaluation.md`](../md%20docs/evaluation.md).

## Headline results

| # | Evaluation | Main result | Where |
| --- | --- | --- | --- |
| 01 | **Greedy vs Genetic algorithm vs MILP** | Planning the week jointly beats greedy one-meal-at-a-time planning. Both GA and MILP cut extra grocery items by a third (23.7 → 15.4) and raise dinners in the calorie band from 4 % to about 70 %. The MILP wastes 40 g less than greedy (GA 30 g less) and 10 g less than the GA, while the GA is 7.7× faster (0.6 s vs 4.7 s). Zero rule violations everywhere | [01_planner_comparison](01_planner_comparison/README.md) |
| 02 | Ablations of the MILP | Every cost term works and has a price. Without the expiry term, 32 g more food spoils. Without nutrition, calorie fit falls 45 points. Without preference, the taste match drops and disliked dinners more than double | [02_ablations](02_ablations/README.md) |
| 03 | Robustness to wrong expiry / quantities | The expiry-aware plan degrades slightly *more* than the plan without expiry awareness (the proposal's expectation is not supported), but still has the lowest real waste | [03_robustness](03_robustness/README.md) |
| 04 | **Real-taste preferences (100 MealRec users)** | Preferences learned from a person's past ratings pick the dinners they choose later at **2× the chance rate** (test users: HR@10 0.202 vs 0.10, AUC 0.622), beating today's popularity prior with every CI clear of zero. Now in the planner via the "Loved it" mark | [04_real_taste_preferences](04_real_taste_preferences/README.md) |
| 05 | Solver backends | HiGHS and OR-Tools CP-SAT give the same plans; HiGHS stays the default | [05_solver_backends](05_solver_backends/README.md) |
| 06 | Weight tuning | Adopted preference ×6 and nutrition ×2: liked-cuisine dinners 12.6 % → 27.6 % and calorie fit 57 % → 71 % for +2.8 grocery items. A waste ×2 setting passed its rule but awaits a decision | [06_weight_tuning](06_weight_tuning/README.md) |
| 07 | GA configuration | Population 48, 350 generations, mutation 0.20, chosen on validation data for speed with strong nutrition and waste results | [07_ga_configuration](07_ga_configuration/README.md) |

## Against the proposal's evaluation plan

| Proposal measure | Status | Result |
| --- | --- | --- |
| Pantry utilisation | done (01) | Optimisers use a smaller share of the whole pantry (17 % vs greedy 26 %) but more of the expiring stock |
| Food waste | done (01, 03) | MILP −40 g/week vs greedy [−64, −17]; GA −30 g |
| Additional groceries | done (01) | −8.3 items/week vs greedy, but about +0.9 kg by weight |
| Constraint safety | done (01) | 0 violations for every planner in every scenario |
| Nutrition adherence | done (01, 02) | Dinners in the calorie band 4 % → 71 %; protein minimum 12 % → 59 % |
| Preference quality | done (01, 02, 04) | +0.09 taste match vs greedy; validated on real people's ratings in 04 |
| Ingredient NLP (precision / recall / F1) | **not done** | Needs the hand-labelled sentence set, which has not been built |
| Optimisation robustness | done (03) | See 03; the proposal's expectation is not supported |
| Stage 1 · Gate the data | done | Coverage and consistency gates in `data/canonical/README.md` |
| Stage 2 · Beat the baselines | done (01) | Random and greedy, plus GA vs MILP |
| Stage 3 · Ablate components | done (02) | Expiry, nutrition and preference terms |

## What the numbers are (and are not)

- **Planning results (01–03, 05–07) are on the validation split** of the frozen synthetic benchmark: 120 scenarios in 8
  families, a seeded generator, no real households. The **test split has not been run yet**. It is reserved for one
  final run once the weights are frozen, and the waste-weight decision (06) is still open.
- **Real-taste results (04)** come from real people's ratings: the test users were run once, after the method was
  fixed on validation users.
- **Built-in advantage:** calorie fit, preference and cooking time are measured with the definitions the optimisers
  minimise, so they favour the optimisers by construction. The independent checks are waste and groceries (replayed
  against hidden true expiry dates), the ablations, robustness, and the real-taste check.
- **Read differences, not absolute values:** every comparison is paired on identical scenarios, with 95 % bootstrap
  confidence intervals.

## Reproduce

Requires the curated dataset in `data/canonical/` (tracked) and, for 04 only, the MealRec download.

```bash
python src/evaluation/runner.py --split validation --planners random,greedy,genetic,optimiser --baseline greedy --save          # 01
python src/evaluation/runner.py --split validation --planners genetic_350_s0,genetic_350_s1,genetic_350_s2,genetic_350_s3,genetic_350_s4 --save  # 01, GA seeds
python src/evaluation/runner.py --split validation --planners optimiser,opt_no_expiry,opt_no_nutrition,opt_no_preference --baseline optimiser --save  # 02
python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_no_expiry --baseline opt_no_expiry --limit 48 --save  # 03
python src/evaluation/taste_users.py && python src/evaluation/taste_eval.py --split validation                                  # 04
python src/evaluation/runner.py --split validation --planners greedy,optimiser,optimiser_cpsat --limit 48 --baseline greedy --save  # 05
# 06: four sweeps (preference / nutrition, confirmation, variety, waste); their exact commands are in
#     md docs/evaluation.md ("Weight sweep") and md docs/modules/evaluation/weight_sweep.md
```

Everything is seeded and deterministic, apart from the MILP's 8-second wall-clock limit, which makes a busier or quieter
machine find slightly different plans (about ±2 points on calorie fit).

## Data sources

Food.com recipes and interactions · USDA FoodData Central · USDA FoodKeeper · **MealRec** (Ming Li, Lin Li, Qing Xie,
Jingling Yuan, Xiaohui Tao. *MealRec: A Meal Recommendation Dataset.* arXiv:2205.12133, 2022), used for 04 only. MealRec
has no licence for redistribution, so its derived user sets are not in this repository.
