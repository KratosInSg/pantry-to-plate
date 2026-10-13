# `src/domain/` — the shared vocabulary of planning

## Purpose

The typed objects every stage agrees on: *who* is cooking (`UserProfile`), *what is in the kitchen*
(`PantryItem`), *one planning problem* (`Scenario`) and *the answer* (`WeekPlan`). It also holds the single place
that turns an NLP parse into planner-ready pantry items (`pantry_from_parse`).

It contains **data shapes and one translation; no planning logic.** That is what lets the NLP layer, the hard-rule
filter, the optimiser, the evaluator and the explainer all depend on `domain` without depending on each other.

## Files

| File | Role | Doc |
| --- | --- | --- |
| `models.py` | `Diet`, `UserProfile`, `PantryItem`, `Scenario`, `WeekPlan`, constants (`ALLERGENS`, `HORIZON_DAYS`) | [models.md](models.md) |
| `pantry.py` | NLP parse → `PantryItem`s: how much to believe about each deadline | [pantry.md](pantry.md) |

## Conventions that every consumer relies on

1. **Days are integers**, day 0 = the first dinner to plan. `last_use_day` is **inclusive**; `None` = no deadline
   inside the horizon.
2. **Known vs estimated expiry is explicit** (`expiry_known`). Known use-by dates are hard constraints; estimates are
   soft and weighted by `expiry_confidence`.
3. **Hidden truth** (`Scenario.true_last_use_day`) exists only in synthetic benchmark scenarios. Planners must not read
   it; only the evaluator's simulator does.

## Change log

- 2026-10-12 — Package created with the planning path (models, pantry conversion).
