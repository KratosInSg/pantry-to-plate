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

## Additional completed evaluations

* **Robustness:** Expiry and pantry-quantity perturbations are evaluated in `src/evaluation/robustness.py`, including the two-day estimated-expiry safety-margin experiment on fresh v3 kitchens. See [Evaluation/03](../../../../Evaluation/03_robustness/README.md) and [Evaluation/09](../../../../Evaluation/09_expiry_safety_margin/README.md).
* **Ingredient NLP:** Precision, recall, F1 and field-level accuracy are evaluated in `src/evaluation/nlp_eval.py` on 120 synthetically generated, team-reviewed pantry messages (1,718 ingredient mentions). See [Evaluation/08](../../../../Evaluation/08_ingredient_nlp/README.md). These measurements use generated answer keys reviewed by the team, rather than independently collected real-user annotations.

## Tests

[`tests/evaluation/test_metrics.py`](../tests/evaluation/test_metrics.md)

## Avoidable vs unavoidable waste

`avoidable_waste_g` is the part of `waste_g` that some recipe **allowed for this user** could have used. `unavoidable_waste_g` is the rest: pantry stock that no recipe passing the user's hard rules contains (`unusable_ingredients(scenario, ctx, prepared)`), such as meat in a vegan pantry or an allergen. Every planner wastes that stock, so it only dilutes comparisons. Added after it turned out to be about 70 % of all waste in `restrictive_diet` (the generator seeds pantries from any recipe, ignoring the diet). `avoidable_waste_g` is in `HIGHER_IS_BETTER` (lower is better); `unavoidable_waste_g` is context only, identical across planners on a scenario.

## Change log

- 2026-10-12 — Created. A `known_expiry_violation_g` metric was built and then removed: the replay can never schedule
  expired stock, so it flagged stranded stock rather than a constraint breach and would have shown a misleading
  "must be 0". The guarantee is tested structurally in `tests/optimizer/test_weekly.py`.
- 2026-10-14 — Added `avoidable_waste_g` / `unavoidable_waste_g` and `unusable_ingredients`.
- 2026-10-16 — `paired_bootstrap(..., higher_is_better=None)`: override the direction for columns that are not plan metrics (robustness degradation). Plans are still scored without substitution rules (conservative).
