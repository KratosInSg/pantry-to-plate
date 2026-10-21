# `src/evaluation/` — measuring plans, never producing them

## Purpose

Everything needed to answer "is the optimiser better than the baselines, and why?": a seeded synthetic benchmark of
simulated kitchens, a frozen validation/test split, plan metrics computed by one shared replay, and a runner that
compares methods with paired statistics. It **measures plans; it never produces the app's plan**.

## Flow

```
scenarios.generate_scenario(family, seed)      8 families × N seeds   (pure function of the dataset)
        │
        ▼
scenarios.freeze_benchmark                      data/evaluation/{scenarios_v1.jsonl, split_v1.json, FROZEN.json}
        │                                       (SHA-256 verified on every load)
        ▼
runner.run(split, planners)                     plan each scenario with each method
        │
        ▼
metrics.evaluate_plan                           replay against the HIDDEN truth + same scoring for every method
        │
        ▼
metrics.summarise / paired_bootstrap            per-family and paired comparisons with 95 % CIs
```

## Files

| File | Role | Doc |
| --- | --- | --- |
| `scenarios.py` | Generator (8 families), split, freeze, verified load | [scenarios.md](scenarios.md) |
| `metrics.py` | `evaluate_plan`, `summarise`, `paired_bootstrap` | [metrics.md](metrics.md) |
| `runner.py` | Planner registry + CLI comparison | [runner.md](runner.md) |
| `build_benchmark.py` | One-shot freeze script | [build_benchmark.md](build_benchmark.md) |
| `taste_users.py` | Builds / freezes / loads the 100 MealRec real-taste users (`data/evaluation/taste_v2/`; v1 kept) | [taste_users.md](taste_users.md) |
| `taste_eval.py` | Real-taste preference check: do preferences from earlier ratings rank later liked dinners high (HR@K / NDCG@K with the MealRec paper's protocol, AUC) | [taste_eval.md](taste_eval.md) |
| `robustness.py` | Measure 8: replay each plan against perturbed realities (earlier spoilage, wrong amounts); signed degradation, paired vs `opt_no_expiry` | [robustness.md](robustness.md) |
| `pantry_messages.py` | Measure 7 data: the v3 kitchens written as pantry messages, with an answer key (synthetic labels), frozen | [pantry_messages.md](pantry_messages.md) |
| `nlp_eval.py` | Measure 7: parser precision/recall/F1, quantity and urgency accuracy; parse-then-plan | [nlp_eval.md](nlp_eval.md) |

## Discipline (project non-negotiable)

1. The split is frozen **before** any weight is tuned; `load_split` refuses a modified file.
2. Tune on `validation` only. Run `test` **once**, at the end, after weights are frozen (the runner prints a reminder).
3. Never change the generator without bumping `BENCHMARK_VERSION`; old numbers then no longer apply.

## Change log

- 2026-10-12 — Package created; benchmark v1 frozen (240 scenarios, 120 validation / 120 test).
- 2026-10-16 — Added `robustness.py` (measure 8: degradation under expiry / quantity perturbations).
- 2026-10-16 — Added `taste_users.py` and `taste_eval.py` (real-taste preference check on MealRec users).
- 2026-10-16 — Real-taste check: `taste_v2` (adds tags), paper-protocol HR/NDCG metrics; test users run once.
- 2026-10-21 — Added `pantry_messages.py` and `nlp_eval.py`; v3 benchmark.
