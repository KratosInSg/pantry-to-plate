# `src/evaluation/metrics.py`

## Purpose

Replay any method's week against a scenario and measure what matters (`md docs/evaluation.md`). Every method goes
through the **same** `evaluate_plan`, which uses the same inventory replay and the same scoring functions: methods can
only differ in the plan they hand in, never in how they are judged.

## Metrics

| Metric | Meaning | Better |
| --- | --- | --- |
| `pantry_utilisation_pct` | share of starting (non-staple) pantry grams cooked with | higher |
| `expiring_utilisation_pct` | same, only for stock that truly expires inside the week | higher |
| `waste_g`, `waste_pct` | grams (and share of expiring stock) that spoiled unused — against the **hidden true** expiry | lower |
| `grocery_items`, `grocery_g` | what must be bought | lower |
| `violations` | hard-rule violations (diet, allergen, exclusion, time …) — **must be 0** | lower |
| `nutrition_in_range_pct` | share of dinners inside the kcal band | higher |
| `nutrition_dev_pct` | mean distance outside the band, % of the dinner target | lower |
| `protein_ok_pct` | share of dinners meeting the protein minimum | higher |
| `preference_mean`, `disliked_rate` | mean preference score; share of meals with a disliked ingredient/cuisine | higher / lower |
| `weekday_overtime_rate` | share of weekday dinners longer than the user's limit | lower |
| `distinct_cuisines` | variety | higher |
| `complete` | 1 if a full week was planned | higher |

## Public API

| Name | What |
| --- | --- |
| `evaluate_plan(scenario, plan, ctx, prepared=None) -> PlanMetrics` | Pass `prepared` to reuse preference scores across planners |
| `summarise(df, by=None)` | Mean of every metric, grouped (default: planner) |
| `paired_bootstrap(df, metric, a, b, n_boot=2000, seed=0)` | Mean difference `a − b` with a 95 % CI over the same scenarios, plus the share where `a` is strictly better |
| `HIGHER_IS_BETTER` | Direction of every metric |

## Things to read carefully

* **Waste is against the truth, not the belief.** A plan is judged by what really happens to the food.
* **`pantry_utilisation_pct` counts all pantry grams,** not only expiring ones. A method that cooks fewer *non-expiring*
  items (and buys less) scores lower here while wasting less — read it together with `expiring_utilisation_pct`,
  `waste_g` and `grocery_items`.
* **Preference / nutrition / cook-time metrics use the same definitions the optimiser minimises.** That is deliberate:
  the claim tested is that planning the week jointly beats one-meal-at-a-time on these costs. Independent checks are
  robustness, the frozen NLP set and ablations.
* **Constraint safety is relative to the knowledge base** (hidden allergens in branded products are not covered).

## Not implemented yet

* Robustness metric (plan degradation under perturbed expiry / quantities) — the scenario's hidden truth already
  supports the perturbation; the metric itself is still to write.
* Ingredient-NLP precision/recall/F1 needs a human-labelled set.

## Tests

[`tests/evaluation/test_metrics.py`](../tests/evaluation/test_metrics.md)

## Change log

- 2026-10-12 — Created. A `known_expiry_violation_g` metric was built and then removed: the replay can never schedule
  expired stock, so it flagged stranded stock rather than a constraint breach and would have shown a misleading
  "must be 0". The guarantee is tested structurally in `tests/optimizer/test_weekly.py`.
