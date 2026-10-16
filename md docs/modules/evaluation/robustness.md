# `src/evaluation/robustness.py`

## Purpose

Evaluation measure 8, **optimisation robustness**: how much a week's plan degrades when the kitchen is not what the
planner was told. Food can spoil earlier than its estimate, or the stock can differ from the stated amount. The slide
compares this against the planner without expiry awareness (`opt_no_expiry`); less degradation is better.

## How it measures

1. Each planner plans each scenario **once**, from the unchanged, planner-visible scenario.
2. The plan is judged by `evaluation.metrics.evaluate_plan` (the same judge as every other metric) against each
   *perturbed reality* from `perturb_reality`. A perturbed reality has the same user, plan and visible deadlines, but
   a different hidden truth (`true_last_use_day`, pantry grams).
3. **Degradation** = perturbed − nominal for each metric, signed so that **positive = worse** whichever way the metric
   points. It is computed per (scenario, planner) and then compared across planners with the paired bootstrap.

The plan is not re-planned: this measures how well a week chosen in advance holds up. Re-planning
(`optimizer/replan.py`) is the remedy.

## Public API

| Name | What |
| --- | --- |
| `Perturbation` | `name`, `expiry_shift_days` (spoils earlier), `expiry_jitter_days` (± uniform), `quantity_scale`, `quantity_sigma` (log-normal per item); `is_nominal` |
| `NOMINAL`, `PERTURBATIONS` | The unchanged kitchen, and the standard set (1 and 2 days early, ±2-day jitter, −30 %, +30 %, 30 % noise, combined) |
| `perturb_reality(scenario, perturbation, seed=0) -> Scenario` | The kitchen as it really is. Pure. Use only to judge, never to plan |
| `run_robustness(split, planner_names, perturbations, limit, eval_dir, ctx, seed) -> DataFrame` | One row per (scenario, planner, perturbation): every `PlanMetrics` field + `perturbation` |
| `degradation(df) -> DataFrame` | `deg_<metric>` per non-nominal row (positive = worse) |
| `summarise_degradation(deg)` | Mean degradation per (perturbation, planner) |
| `compare_degradation(deg, planner, baseline)` | Paired difference in degradation with a 95 % bootstrap CI, one row per perturbation (negative = `planner` more robust) |
| `report(df, baseline)` | Prints the three tables |
| `ROBUSTNESS_METRICS`, `DEFAULT_BASELINE` | Waste, avoidable waste, grocery items and grams, expiring and overall utilisation; `opt_no_expiry` |

CLI:

```bash
python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_no_expiry --limit 48 --save
```

`--save` writes `<eval-dir>/runs/<timestamp>_robustness_<split>.csv`.

## Decisions

* **Only estimated deadlines inside the week move.** Known use-by dates are the truth by definition (hard constraints),
  and food with no deadline this week does not start spoiling because an estimate was off. Deadlines are clamped at
  day 0, because the user has just said the food is there.
* **Sizes are plausible errors, not stress tests.** 1–2 days is inside a typical FoodKeeper min–max spread for fridge
  produce, and ±30 % is how far a guessed amount, or the NLP layer's group-median default, easily is from the real one.
* **Nutrition, preference, time and safety are not reported:** they depend only on the recipes chosen, which do not
  change when reality does.
* **Deterministic:** each perturbation's random draws are seeded by (seed, CRC32 of the scenario id, CRC32 of the
  perturbation name), so every planner faces the same reality.

## How to read the numbers

* Compare planners, not absolute degradation. With 30 % less stock, *waste* falls for every plan simply because there
  is less food to waste; what matters is the paired difference, and for quantity perturbations the grocery columns.
* `expiry_jitter_2d` is not symmetric in effect: a deadline pushed beyond the week stops being waste, and one pulled
  before day 0 is clamped.

## Limits

* The perturbed realities are synthetic, like the scenarios they perturb.
* Deadlines and quantities are perturbed independently of food type (spinach and rice get the same rule).

## Tests

[`tests/evaluation/test_robustness.py`](../tests/evaluation/test_robustness.md)

## Logging

Logger `evaluation.robustness`. INFO: progress every 20 scenarios. Only `main()` configures logging.

## Change log

- 2026-10-16 — Created: perturbations, perturbed-reality replay, signed degradation, paired comparison, CLI.
