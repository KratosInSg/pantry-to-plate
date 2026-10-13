# `src/optimizer/candidates.py`

## Purpose

Shrink ~54K feasible recipes to the few hundred the solver can reason about, without starving it of the options it
needs to reduce waste.

## Why shortlist at all

Seven days × 54K recipes = 380K binaries plus the ingredient-balance structure: far too slow for an interactive app,
and almost entirely irrelevant — most recipes share nothing with this pantry. So: hard rules (remove) → shortlist
(rank, keep promising) → solver (choose the combination).

## Composite score (all parts in [0, 1])

```
composite = 0.5 * pantry_coverage + 0.3 * preference + 0.2 * nutrition_fit
```

* `pantry_coverage` — urgency-weighted share of the recipe's mass the pantry can supply. Stock about to expire counts
  up to 3× (`urgency_weight`); an *estimated* deadline counts in proportion to its confidence.
* `preference` — from `preference.scorer`.
* `nutrition_fit` — 1 at the dinner kcal target, falling linearly to 0 at ±100 %.

The composite is a **candidate generator**, not the decision; plan quality is decided by the solver's objective.

## Pantry-aware guarantees

After taking the top `size` recipes (with no cuisine above `max_cuisine_share` of the list), every pantry ingredient due
within `urgent_within_days` gets at least `per_urgent_ingredient` recipes using it, even if they ranked low. The solver
therefore always has a way to use urgent stock if any feasible recipe can.

## Public API

| Name | What |
| --- | --- |
| `shortlist(catalog, profile, pantry, feasible, preference, ignore_ids, config) -> int64[]` | Sorted catalogue row indices, all feasible |
| `ShortlistConfig` | `size`, `per_urgent_ingredient`, `urgent_within_days`, weights, `max_cuisine_share` |
| `pantry_coverage`, `nutrition_fit`, `urgency_weight` | The score's parts (also unit-tested) |

## Tuning note

`size` trades quality for time: with HiGHS, 250 candidates (1,750 binaries) took ~15–20 s per plan and often hit the
time limit; `WeeklyPlanner` defaults to 120 (~6 s). Plan quality was comparable at 100–250 on the draft benchmark.

## Limits

* Coverage is mass-based and ignores ingredient *importance* (a pinch of an herb counts like a gram of meat).
* Shortlist weights are hand-set; they affect *who is considered*, so they should be tuned on validation only.

## Tests

[`tests/optimizer/test_candidates.py`](../tests/optimizer/test_candidates.md)

## Change log

- 2026-10-12 — Created.
