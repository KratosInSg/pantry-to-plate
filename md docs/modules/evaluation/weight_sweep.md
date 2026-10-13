# `src/evaluation/weight_sweep.py`

## Purpose

Tune the optimiser's weights **the way the project's rules require**: on the validation split only, over a small
stated grid, with the choice rule written down (as code) before the numbers are seen, and compared on identical
scenarios. It exists because reading real explanations showed the hand-set preference weight was too weak to notice.

```bash
python src/evaluation/weight_sweep.py --limit 48 --workers 6 --save      # ~6 minutes (one process per candidate)
```

## Public API

| Name | What |
| --- | --- |
| `GRID` | 6 candidates: preference ×{1, 3, 6} × nutrition ×{1, 2} (kcal and protein deviation together) |
| `SweepConfig`, `SWEEP_BASE`, `weights_for(config)` | A candidate and the starting weights its multipliers apply to |
| `run_sweep(split="validation", limit, workers, configs)` | One row per (scenario, candidate); **raises for any other split** |
| `summarise(df)`, `guardrail_failures(summary, baseline)`, `choose(summary, baseline)` | The decision rule (pure functions of a table) |
| `liked_cuisine_rate(cuisines, liked)` | The "visible effect" metric: share of dinners in a cuisine the user likes |
| `GUARDRAILS` | The limits a candidate must respect |

## The rule (fixed before running)

Among candidates that pass **every** guardrail relative to the default, take the one with the largest
`liked_cuisine_rate`; equal rates (3 d.p.) go to the smaller change; if none beats the default, the default is kept.

| Guardrail | Limit vs default |
| --- | --- |
| waste | at most 5 % worse |
| extra grocery items | at most 0.5 worse |
| dinners in kcal band | at most 3 points worse |
| disliked meals | at most 2 points more |
| rule violations / incomplete weeks | none |

## Decisions

* **Multipliers, not values.** Every candidate is "the start × k", so a result reads as "preference ×3" and the number
  of comparisons (the room to overfit) is six.
* **Relative to `SWEEP_BASE`, not to `DEFAULT_WEIGHTS`.** Once a candidate is adopted `DEFAULT_WEIGHTS` moves; if the
  sweep multiplied *that*, "×3" would become ×9 and the sweep would stop being reproducible (tested).
* **Guardrails dominate the target.** A candidate that makes the visible effect larger but costs more shopping is
  rejected, however good it looks; the user can still choose it as a product decision (see `evaluation.md`).
* **Validation only.** The test split is run once, after weights are frozen; this module refuses it.

## Limits

* 48 scenarios (6 per family): enough for the pooled differences reported, not for per-family claims.
* `liked_cuisine_rate` measures the *scorer's* liked-cuisine signal, which is a proxy for "what a user would notice";
  there is no user panel.
* The grid ignores the other weights (waste, groceries, variety, cook time) and interactions beyond the two axes.

## Tests

[`tests/evaluation/test_weight_sweep.py`](../tests/evaluation/test_weight_sweep.md)

## Change log

- 2026-10-13 — Created. First (and recorded) run adopted preference ×3: `OptimizerWeights.preference` 1.0 → 3.0.
