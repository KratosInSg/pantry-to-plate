# `src/optimizer/weekly.py`

## Purpose

Choose seven dinners that jointly minimise waste, groceries and penalties, subject to the hard rules. **This is the only
place in the system that decides the plan.** The explainer only reads the cost terms it returns.

## The model

Indices: recipe `k` in the shortlist, day `d`, ingredient `i`.

| Variable | Meaning |
| --- | --- |
| `x[k,d] ∈ {0,1}` | recipe `k` is cooked on day `d` |
| `u[i,d] ≥ 0` | grams of *pantry* stock of `i` used on day `d` (exists only for days the stock is still usable) |
| `g[i] ≥ 0`, `y[i] ∈ {0,1}` | grams of `i` to buy; `i` is on the shopping list |
| `lo[d]`, `hi[d]`, `pr[d] ≥ 0` | kcal below / above the dinner band, protein shortfall |
| `ex[c] ≥ 0` | meals beyond the cap in variety group `c` (cuisine / protein type) |

| Constraint | |
| --- | --- |
| one dinner per day; no repeated recipe | `Σ_k x[k,d] = 1`, `Σ_d x[k,d] ≤ 1` |
| use ≤ need, use ≤ stock | `u[i,d] ≤ Σ_k grams[k,i]·x[k,d]`, `Σ_d u[i,d] ≤ stock[i]` |
| **no use after the deadline** | `u[i,d]` simply does not exist for `d > last_use_day[i]` (known dates: HARD) |
| buy what the pantry cannot cover | `g[i] ≥ Σ demand − Σ_d u[i,d]`, `g[i] ≤ M[i]·y[i]` |
| nutrition band | `kcal[d] + lo[d] ≥ low`, `kcal[d] − hi[d] ≤ high`, `protein[d] + pr[d] ≥ minimum` |
| variety | `meals(c) − ex[c] ≤ cap[c]` |

### Objective (weights in `OptimizerWeights`)

| Term | Cost |
| --- | --- |
| waste | `w_waste · Σ factor[i]·(stock[i] − Σ_d u[i,d]) / 100` — only stock that can expire inside the week |
| groceries | `w_item · Σ y[i] + w_gram · Σ g[i] / 100` |
| nutrition | `w_kcal · Σ_d (lo+hi)/kcal_target + w_prot · Σ_d pr/protein_min` |
| preference | `w_pref · Σ x[k,d]·(1 − preference[k])` |
| cook time | `w_time · Σ x[k,d]·weekday[d]·max(0, minutes[k] − limit)/limit` |
| variety | `w_var · Σ ex[c]` |

`factor[i]` raises the cost of wasting stock that expires sooner and, for *estimated* deadlines, scales it by the
estimate's confidence (a guess is chased less hard than a stated date).

Defaults: waste 1.0 / 100 g, item 1.0, grocery 0.3 / 100 g, **kcal 8.0, protein 4.0, preference 6.0**, weekday time
1.5, variety 0.7 (cuisine cap 2, protein-type cap 4). Hand-set except the three in bold, which were doubled /
sextupled from 4.0 / 2.0 / 1.0 by a bounded sweep on the validation split and then confirmed on all 120 validation
scenarios against pre-declared criteria (`evaluation/weight_sweep.py`; results in `md docs/evaluation.md`). The price
is about +2.8 extra grocery items a week for +15 pts liked-cuisine dinners and +14 pts dinners in the calorie band.
Further tuning: **validation** only.

## Public API

| Name | What |
| --- | --- |
| `WeeklyPlanner(ctx, weights=DEFAULT_WEIGHTS, name="optimiser", shortlist_config=ShortlistConfig(size=120), time_limit_s=8.0, mip_rel_gap=0.02, backend="highs")` | `plan(scenario) -> WeekPlan`; `backend` is `"highs"` or `"cpsat"` (unknown → `ValueError`) |
| `OptimizerWeights`, `DEFAULT_WEIGHTS` | The cost weights + two ablation switches (`urgency_weighting`, `confidence_weighting`) |
| `ABLATIONS` | `no_expiry`, `no_nutrition`, `no_preference`: weights with one term zeroed |
| `make_planner(name, ctx, **kw)` | `"optimiser"` or `"opt_<ablation>"`; a `_cpsat` suffix (`optimiser_cpsat`, `opt_no_expiry_cpsat`) selects CP-SAT |

`WeekPlan.diagnostics` holds: `n_feasible`, `n_candidates`, `backend`, `solve_seconds`, `objective`, `mip_gap`, `model_waste_g`,
`model_grocery_items`, `model_grocery_g`, `model_kcal_dev`, `model_protein_dev_g`, `weights`, and
**`cost_<term>` for each of `COST_TERMS`** (`waste`, `groceries`, `nutrition`, `preference`, `cook_time`, `variety`):
each term's contribution to the objective at the chosen plan. They are non-negative and **sum to `objective`**
(tested). These are what the explainer cites ([`explain/`](../explain/README.md)).

## Decisions worth knowing

* **Stock is usable only up to its deadline — for known *and* estimated dates.** The difference between them is the cost
  weight (confidence), not feasibility: scheduling a meal on stock past an *estimated* date is not something we should
  recommend. (If an estimate is too pessimistic the plan buys fresh food; that cost is the price of safety.)
* **Hard rules are not in the model.** They were applied before the shortlist; the solver never sees a violating recipe.
* **The shortlist bounds the model** so solve time stays at seconds; it is pantry-aware so urgent ingredients always
  have options.
* **Ablations are weights**, so switching a term off cannot accidentally change anything else.
* **Honest status.** `optimal` only when the solver proved it within the gap; `feasible` = incumbent at the time limit.
* **The backend is a planner property, and part of the method name.** `optimiser` and `optimiser_cpsat` are separate
  rows in every results table, so a number can never be attributed to the wrong solver. Both build the identical model.

## Measured (frozen validation split, v1, seeds fixed)

See the results table in [`md docs/evaluation.md`](../../evaluation.md#results-so-far) — numbers live there, with the
date and the command that produced them, so they cannot drift from this file.

## Known limits

* HiGHS proves loose gaps on hard instances (big-M + day symmetry). Plans are good but not certified optimal.
* Pantry stock is aggregated per ingredient (one deadline each); the cost model has no notion of pack sizes.
* One user, one serving; leftovers from a recipe's extra servings are not carried to later days.
* The two-objective trade-off (e.g. nutrition vs groceries) is set by hand-chosen weights, not by user-elicited
  utilities.

## Tests

[`tests/optimizer/test_weekly.py`](../tests/optimizer/test_weekly.md)

## Logging

Logger `optimizer.weekly`. DEBUG: shortlist size, model size (variables, integers, constraints), backend; then status, seconds, objective, gap and every cost term at the chosen plan. INFO: too few feasible recipes to optimise. WARNING: no recipe passes the hard rules, or the solver returned no plan. Per-plan lines are DEBUG because the benchmark runner plans hundreds of scenarios; `app.service` writes the INFO line for the app.

## Change log

- 2026-10-12 — Created. Index bug fixed (shortlist position vs catalogue row). Speed tuned: shortlist 120, 8 s limit,
  2 % gap (≈6 s per plan).
- 2026-10-12 — Ablation results recorded in `md docs/evaluation.md`: the nutrition term is strong, the expiry term
  modest, and the preference term has almost no effect at the current weight (open item: re-scale on validation).
- 2026-10-12 — Removed an unused import (no behaviour change).
- 2026-10-13 — `backend` parameter (`highs` | `cpsat`), `_cpsat` planner-name suffix, `backend` in diagnostics.
  Default unchanged (HiGHS), so existing results are unaffected.
- 2026-10-13 — Per-term cost decomposition in diagnostics (`cost_<term>`, `COST_TERMS`) so the explainer can cite the
  solver's own objective terms. The model, constraints and objective are unchanged; no plan changes.
- 2026-10-13 — **Default `preference` weight 1.0 → 3.0** (bounded validation sweep; +7 pts liked-cuisine dinners for
  +0.4 grocery items). Earlier benchmark tables were produced with 1.0 and say so.
- 2026-10-13 — **Defaults changed again: preference 3.0 → 6.0, kcal deviation 4.0 → 8.0, protein deviation 2.0 → 4.0.** The
  project owner accepted about +3 grocery items for stronger likes and a better calorie fit; the exact combination
  met every pre-declared criterion on all 120 validation scenarios (+15.0 / +13.7 pts, +2.78 items, waste +1.7 %).
- 2026-10-14 — Logging: model size, solve outcome and cost terms at DEBUG; no-candidate / no-solution at WARNING.

- 2026-10-16 — Fixed constant waste accounting for expiring pantry ingredients absent from every shortlisted recipe. Their waste cannot be avoided by the solver, but must still be included in the reported objective. This adjusts objective reporting by a scenario-specific constant without changing recipe ranking. Motivated by GA-vs-MILP fixed-plan term audit.
