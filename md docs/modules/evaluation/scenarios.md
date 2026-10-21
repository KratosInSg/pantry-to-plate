# `src/evaluation/scenarios.py`

## Purpose

The synthetic benchmark: seeded simulated kitchens, a stratified validation/test split, and the freeze mechanism that
stops anyone tuning on the test set by accident.

## Why synthetic

Real household pantries with expiry dates are not public. The honest claim is therefore "better planning on realistic
**simulated** kitchens"; the generator exists to make that claim reproducible rather than anecdotal.

## The eight families

| Family | Stresses |
| --- | --- |
| `expiry_heavy` | many items about to expire, 40 % with known use-by dates → waste |
| `sparse_pantry` | 3–6 items → groceries |
| `well_stocked` | 25–40 items (3 kg cap) → utilisation, large search space |
| `restrictive_diet` | vegan/vegetarian + 2–3 allergens → hard rules shrink the pool |
| `conflicting_preferences` | disliked items sit in the pantry; liked cuisines fit it badly |
| `tight_time` | 15–25 min weekday limit → cook-time penalty |
| `nutrition_pressure` | 1,300–1,500 kcal target, 30–40 g protein minimum, ±10 % band |
| `infeasible_combo` | vegan + 4–6 allergens + 3–5 exclusions + 15–25 min hard cap → very few recipes (≥ 7 guaranteed in tests) |

## Planner-visible vs hidden truth

For perishable items the planner is told an **estimate** computed exactly as for a real user
(`domain.pantry.estimate_last_use_day`), while the scenario also stores the **true** last usable day sampled from the
FoodKeeper range (`true_last_use_day`). The evaluator uses the truth; planners never see it. A share of items carry a
*known* use-by date (the planner sees the truth, `expiry_known=True`). This is what lets the benchmark measure
sensitivity to wrong shelf-life estimates.

## Public API

| Name | What |
| --- | --- |
| `generate_scenario(family, seed, catalog, store)` | Pure function of `(family, seed)` and the dataset |
| `build_benchmark(catalog, store, n_per_family=30, base_seed)` | 240 scenarios by default |
| `split_benchmark(scenarios, validation_share=0.5, seed)` | Stratified by family → `{"validation": [...], "test": [...]}` |
| `freeze_benchmark(scenarios, out_dir, dataset_manifest)` | Write scenarios, split and `FROZEN.json` (hashes). Refuses to overwrite |
| `load_split(split, eval_dir)` | Verify hashes, return the scenarios of `"validation"` or `"test"` |
| `FAMILIES`, `SPECS`, `FamilySpec`, `BENCHMARK_VERSION` | The generator's knobs |

## Generator decisions

* Half of each pantry is seeded from real recipes' main ingredients (so it is *cookable*), half is random popular items.
* Stock is scaled to a cap (1.8 kg; 3 kg well-stocked): a week of **dinners** is about a third of one person's food, so
  a larger pantry would make waste unavoidable for every method and the comparison meaningless.
* Hard time caps are a separate knob (`hard_time_cap`) so `infeasible_combo` squeezes the pool without being
  impossible.

## Limits

* Synthetic: the distribution of pantries, ages and preferences is our assumption, not measured behaviour.
* Dinners-only pantries mean baselines waste 80–95 % of expiring stock; relative differences are what matter.

## Tests

[`tests/evaluation/test_scenarios.py`](../tests/evaluation/test_scenarios.md)

## Change log

- 2026-10-12 — Created; v1 frozen into `data/evaluation/` (SHA-256 recorded in `FROZEN.json`).

- 2026-10-15 — Default evaluation directory now points to `data/evaluation/v2/`, an audited byte-for-byte rebaseline of the original committed scenario and split files. The original v1 SHA-256 manifest did not match either committed file; v1 is retained unchanged. v2 does not represent independently regenerated scenarios or a new test set.
- 2026-10-21 — `freeze_benchmark` takes `version`, `validation_share` and `provenance` (defaults unchanged). Used to freeze **v3** (`data/evaluation/v3/`): 120 new scenarios, seeds 20261100–20261114 per family, all in the test split - a fresh held-out set for methods chosen after the v2 test split was used, and the source of the synthetic NLP messages.
