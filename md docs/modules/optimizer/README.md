# `src/optimizer/` — the only place that decides the weekly plan

## Purpose

Given a `Scenario` (profile + pantry + horizon), choose seven dinners. Everything upstream only *prepares* inputs
(NLP parse, preference scores); everything downstream only *reads* the result (explainer, evaluation). That is the
project's non-negotiable: **rules and the optimiser decide, the LLM never does**.

## Pipeline

```
Scenario
  │  hard_rules.feasible_mask        safety: diet, allergens, pork, alcohol, exclusions, time cap   (removes recipes)
  ▼
  │  preference.score_recipes        how much would this user like each recipe          (scores, never filters)
  ▼
  │  candidates.shortlist            54K → ~120 recipes, pantry-aware, urgent ingredients always represented
  ▼
  │  weekly.WeeklyPlanner            one mixed-integer linear model: which recipe on which day, and how the
  │                                  pantry stock is used / what must be bought
  ▼
WeekPlan (recipe_ids, status, diagnostics = the model's own cost terms)
  │
  └─ inventory.account_inventory     the same replay used by the app (grocery box) and by the evaluation (metrics)
```

## Files

| File | Role | Doc |
| --- | --- | --- |
| `hard_rules.py` | Which recipes are allowed at all; named rules with reasons | [hard_rules.md](hard_rules.md) |
| `inventory.py` | One definition of used / bought / wasted (replay) | [inventory.md](inventory.md) |
| `candidates.py` | Shortlist: from the whole catalogue to what the solver can reason about | [candidates.md](candidates.md) |
| `planning.py` | `Planner` interface, `PlanningContext`, per-scenario preparation shared by every method | [planning.md](planning.md) |
| `baselines.py` | Random and greedy planners — what the optimiser must beat | [baselines.md](baselines.md) |
| `linear_model.py` | Tiny solver-agnostic MILP builder | [linear_model.md](linear_model.md) |
| `backends.py` | Solver backends: HiGHS via SciPy (default) and OR-Tools CP-SAT (child process) | [backends.md](backends.md) |
| `cpsat_worker.py` | The CP-SAT solve itself: integer scaling + solve, run as a separate process | [cpsat_worker.md](cpsat_worker.md) |
| `weekly.py` | The weekly model: variables, constraints, cost terms, ablations | [weekly.md](weekly.md) |
| `replan.py` | Mid-week roll-forward: cooked / skipped days leave the pantry, the rest is planned again | [replan.md](replan.md) |
| `substitutions.py` | Substitution rules (buttermilk ← milk + lemon juice …) fired on the replay from spare, hard-rule-safe pantry stock | [substitutions.md](substitutions.md) |

## Design rules

1. **Fair comparison by construction.** Every method gets the same hard-rule filter, preference scores and staples
   assumption from `planning.prepare`, and is judged by the same `inventory` replay. Methods differ only in decision
   logic — the thing being measured.
2. **Safety is a filter, not a cost.** The solver never sees a recipe that violates a hard rule; no weight can buy a
   violation back.
3. **Ablations are weights,** not code branches (`weekly.ABLATIONS`), so switching a term off cannot change anything
   else.
4. **Explanations come from the model.** `WeekPlan.diagnostics` carries the cost terms the solver actually
   minimised; the explainer reads those, never rationalises.

## Solver note

The model is written against `linear_model.LinearModel`, so it is solver-agnostic. HiGHS (`scipy.optimize.milp`,
ships inside SciPy) is the default; OR-Tools CP-SAT, the stack's original choice, is available as a second backend and
runs in a child process because it cannot share a process with pyarrow on the development machine. Choose per planner:
`optimiser` (HiGHS) or `optimiser_cpsat`. See [backends.md](backends.md) and the measured comparison in
`md docs/evaluation.md`.

## Change log

- 2026-10-12 — Package created: hard rules, inventory, shortlist, baselines, MILP model + HiGHS backend, weekly planner.
- 2026-10-13 — CP-SAT backend added (`backends.solve_cpsat` + `cpsat_worker.py`), selectable per planner.
- 2026-10-13 — `replan.py` (mid-week roll-forward); hard rules `excluded_recipe` and opt-in `not_dinner`;
  `groceries_by_day` and skipped-day support in the inventory replay.
- 2026-10-16 — Added `substitutions.py` (ingredient substitution rules on the replay) and `hard_rules.ingredient_violations`; `replan.py` applies the rules.
