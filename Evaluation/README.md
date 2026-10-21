# Pantry-to-Plate — Evaluation results

This folder is the results package for the report. Each sub-folder holds one evaluation: a README with the question,
the set-up, the tables (with 95 % confidence intervals), how to read them and the caveats, plus the raw per-scenario
CSV so every number can be recomputed. The design behind the evaluation is in [`md docs/evaluation.md`](../md%20docs/evaluation.md).

**The held-out test split has been run once (2026-10-16)**, with the weights frozen beforehand. The headline numbers
below are test results. Validation results are kept in each folder as the development record.

## Headline results (test split unless stated)

| # | Evaluation | Main result | Where |
| --- | --- | --- | --- |
| 01 | **Greedy vs Genetic algorithm vs MILP** | Planning the week jointly beats greedy one-meal-at-a-time planning. Both GA and MILP cut extra grocery items by a third (23.7 → 15.3) and raise dinners in the calorie band from 3.5 % to 66–68 %. The MILP wastes 61 g a week less than greedy (GA 47 g) and 14 g less than the GA; the GA is about 7× faster (0.6 s vs 4.0 s). Zero rule violations everywhere, and validation agrees | [01_planner_comparison](01_planner_comparison/README.md) |
| 02 | Ablations of the MILP | Every cost term works and has a price. Without the expiry term, 37 g more food spoils. Without nutrition, calorie fit falls 46 points. Without preference, the taste match drops and dinners with a disliked food rise from 0.5 % to 1.7 % | [02_ablations](02_ablations/README.md) |
| 03 | Robustness to wrong expiry / quantities | The expiry-aware MILP degrades the most when estimates are wrong (+15 to +19 g vs the planner without expiry awareness), so the proposal's expectation is not supported. It still wastes the least in every perturbed kitchen | [03_robustness](03_robustness/README.md) |
| 04 | **Real-taste preferences (100 MealRec users)** | Preferences learned from a person's past ratings pick the dinners they choose later at **2× the chance rate** (test users: HR@10 0.202 vs 0.10, AUC 0.622), beating today's popularity prior with every CI clear of zero. Now in the planner via the "Loved it" mark | [04_real_taste_preferences](04_real_taste_preferences/README.md) |
| 05 | Solver backends (validation) | HiGHS and OR-Tools CP-SAT give the same plans; HiGHS stays the default | [05_solver_backends](05_solver_backends/README.md) |
| 06 | Weight tuning (validation) | Adopted preference ×6 and nutrition ×2: liked-cuisine dinners 12.6 % → 27.6 % and calorie fit 57 % → 71 % for +2.8 grocery items. A waste ×2 setting passed its rule but was not adopted before the test run | [06_weight_tuning](06_weight_tuning/README.md) |
| 07 | GA configuration (validation) | Population 48, 350 generations, mutation 0.20, chosen for speed with strong nutrition and waste results | [07_ga_configuration](07_ga_configuration/README.md) |
| 08 | **Ingredient NLP (synthetic messages, fresh v3)** | Rules-only parser on 120 synthetic pantry messages (1,718 items): precision 0.98, recall 0.82, F1 0.90 [0.86, 0.92]; amounts and urgency almost always right once an item is found. Main gaps: " + " separators, unknown cue wording, regional names. Planning from the typed messages costs +49 g waste a week | [08_ingredient_nlp](08_ingredient_nlp/README.md) |
| 09 | **Expiry safety margin (validation, then fresh v3)** | Planning estimated expiry dates 2 days early fixes 03: on 120 new kitchens it degrades no more than the planner without expiry awareness (−5.4 g and −4.4 g at 1 and 2 days early) and 8–10 g less than today's MILP, at no nominal cost. Not yet the app default | [09_expiry_safety_margin](09_expiry_safety_margin/README.md) |

## Against the proposal's evaluation plan

| Proposal measure | Status | Result (test split) |
| --- | --- | --- |
| Pantry utilisation | done (01) | Optimisers use a smaller share of the whole pantry (19 % vs greedy 27 %) but more of the stock that is about to expire (22.5 % vs 14.8 %) |
| Food waste | done (01, 03) | MILP −61 g/week vs greedy [−83, −41]; GA −47 g [−68, −29] |
| Additional groceries | done (01) | −8.4 items/week vs greedy, but about +0.9 kg by weight |
| Constraint safety | done (01) | 0 violations for every planner in every scenario |
| Nutrition adherence | done (01, 02) | Dinners in the calorie band 3.5 % → 68 %; protein minimum 14 % → 58 % |
| Preference quality | done (01, 02, 04) | +0.065 taste match vs greedy; validated on real people's ratings in 04 |
| Ingredient NLP (precision / recall / F1) | done on a **synthetic** set (08) | P 0.98, R 0.82, F1 0.90 on 120 generator-labelled messages; the hand-labelled set has not been built |
| Optimisation robustness | done (03, 09) | 03: not supported by the deployed MILP; 09: met by the safety-margin variant on the fresh v3 benchmark |
| Stage 1 · Gate the data | done | Coverage and consistency gates in `data/canonical/README.md` |
| Stage 2 · Beat the baselines | done (01) | Random and greedy, plus GA vs MILP |
| Stage 3 · Ablate components | done (02) | Expiry, nutrition and preference terms |

## What the numbers are (and are not)

- **Synthetic benchmark (01–03, 05–07):** 240 scenarios in 8 families from a seeded generator (no real households),
  split 120 validation / 120 test and frozen with SHA-256 hashes before any tuning.
  - Methods and weights were developed on validation only.
  - The test split was run **once**, on 2026-10-16, for 01–03. Any later change of method or weights needs a new
    benchmark version to give an unbiased number again.
- **Real-taste results (04)** come from real people's ratings. The test users were run once, after the method was
  fixed on validation users.
- **Built-in advantage:** calorie fit, preference and cooking time are measured with the definitions the optimisers
  minimise, so they favour the optimisers by construction. The independent checks are waste and groceries (replayed
  against hidden true expiry dates), the ablations, robustness, and the real-taste check.
- **Read differences, not absolute values:** every comparison is paired on identical scenarios, with 95 % bootstrap
  confidence intervals.

## Reproduce

Requires the curated dataset in `data/canonical/` (tracked) and, for 04 only, the MealRec download.

```bash
python src/evaluation/runner.py --split test --planners random,greedy,genetic,optimiser --baseline greedy --save          # 01 (also --split validation)
python src/evaluation/runner.py --split test --planners genetic_350_s0,genetic_350_s1,genetic_350_s2,genetic_350_s3,genetic_350_s4 --save  # 01, GA seeds
python src/evaluation/runner.py --split test --planners optimiser,opt_no_expiry,opt_no_nutrition,opt_no_preference --baseline optimiser --save  # 02
python src/evaluation/robustness.py --split test --planners greedy,optimiser,opt_no_expiry --baseline opt_no_expiry --limit 48 --save  # 03
python src/evaluation/taste_users.py && python src/evaluation/taste_eval.py --split test                                        # 04
python src/evaluation/runner.py --split validation --planners greedy,optimiser,optimiser_cpsat --limit 48 --baseline greedy --save  # 05
# 06: four sweeps (preference / nutrition, confirmation, variety, waste); their exact commands are in
#     md docs/evaluation.md ("Weight sweep") and md docs/modules/evaluation/weight_sweep.md
```

Everything is seeded and deterministic, apart from the MILP's 8-second wall-clock limit, which makes a busier or quieter
machine find slightly different plans (about ±2 points on calorie fit). The runner prints a reminder when the test
split is used.

## Data sources

Food.com recipes and interactions · USDA FoodData Central · USDA FoodKeeper · **MealRec** (Ming Li, Lin Li, Qing Xie,
Jingling Yuan, Xiaohui Tao. *MealRec: A Meal Recommendation Dataset.* arXiv:2205.12133, 2022), used for 04 only. MealRec
has no licence for redistribution, so its derived user sets are not in this repository.
