# `src/evaluation/weight_sweep.py`

## Purpose

Tune the optimiser's weights **the way the project's rules require**: on the validation split only, over a small
stated grid, with the choice rule written down (as code) before the numbers are seen, and compared on identical
scenarios. It exists because reading real explanations showed the hand-set preference weight was too weak to notice.

```bash
python src/evaluation/weight_sweep.py --limit 48 --workers 6 --save      # ~6 minutes (one process per candidate)

# re-measure one specific candidate on EVERY validation scenario against the fixed adoption criteria
python src/evaluation/weight_sweep.py --limit 0 --candidates "3:1,6:2" --confirm 6:2 --workers 3 --save
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
| `ADOPTION_CRITERIA`, `adoption_failures(summary, baseline, candidate)` | The *confirmation* criteria (below): what a candidate must show on the full validation split to be adopted |
| `parse_candidates("3:1,6:2")` | CLI candidates as `preference:nutrition` multipliers; the default is always first |

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

## Confirming a trade-off the owner chose

The guardrails above protect the grocery count (+0.5 items). The project owner may decide that a stronger setting is
worth more shopping — that is a *product* decision the data cannot make. Because such a decision comes after the sweep
has been seen, the exact candidate is **re-measured on every validation scenario** (including ones the sweep never
used) against `ADOPTION_CRITERIA`, which are fixed in code before the run:

| Criterion (candidate − start) | Threshold |
| --- | --- |
| liked-cuisine dinners | at least +10 points |
| dinners inside the calorie band | at least +8 points |
| extra grocery items | at most +3.5 (the owner's accepted cost) |
| waste | at most 5 % more |
| disliked meals | at most +2 points |
| rule violations, shorter weeks | none |

`--confirm PREF:NUTRITION` prints which criteria are met or missed. The test split is still not used.

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
- 2026-10-13 — Added the confirmation mode (`ADOPTION_CRITERIA`, `adoption_failures`, `parse_candidates`, `--candidates`,
  `--confirm`, `--limit 0` = all validation scenarios). Tooling only: `DEFAULT_WEIGHTS` is unchanged by this entry.
- 2026-10-13 — The first confirmation run adopted preference ×6 with nutrition ×2: `OptimizerWeights` preference 6.0,
  kcal 8.0, protein 4.0 (all criteria met on 120 validation scenarios).
