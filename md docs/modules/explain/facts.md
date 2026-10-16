# `src/explain/facts.py`

## Purpose

Extract, as typed immutable data, every fact that can honestly be stated about a plan. `render.py` turns facts into
sentences; nothing else in `explain` looks anywhere else. This is where "never a rationalisation" is enforced: a fact
either comes from the replay, the hard rules, the user's own profile, or the optimiser's own cost terms — or it is not
in `PlanFacts` and so cannot be said.

## Public API

| Name | What |
| --- | --- |
| `build_facts(scenario, plan, ctx) -> PlanFacts` | Pure and deterministic. Works for any planner's plan; `solver` is `None` for plans without cost terms |
| `PlanFacts` | Week totals, rule counts, `days: tuple[DayFacts]`, `leftovers`, `stranded`, `groceries`, `solver`, … |
| `DayFacts` | One dinner: name, minutes, kcal and protein, kcal status/gap, protein gap, time over the weekday limit, `pantry_uses`, `groceries`, preference reasons |
| `PantryUse`, `GroceryNeed`, `Leftover`, `Stranded`, `RuleFact`, `SolverFacts` | The leaf facts |
| `SubstitutionFact` | A fired substitution rule on one dinner: `rule_key`, `replaced`, `replaced_g`, `uses` (name, grams), `note`; in `DayFacts.substitutions` |
| `KCAL_IN_RANGE` / `KCAL_BELOW` / `KCAL_ABOVE`, `WEEKDAY_NAMES` | Constants |

## Where each fact comes from

| Fact | Source |
| --- | --- |
| pantry used per dinner, groceries per dinner, week totals, waste | `optimizer.substitutions.replay_with_substitutions` with the *planner-visible* deadlines: the evaluation's replay (`account_inventory`) plus the substitution rules that fired, the same call as the app's grocery box. The benchmark scores plans without substitutions, which can only lower groceries and waste |
| substitutions | the fired rule (`optimizer.substitutions.Substitution`) |
| `Stranded` | the replay's `expired_demand_g`: stock you own that is past its deadline on the day a dinner needs it, so that dinner buys it again |
| kcal / protein / minutes | the catalogue's computed per-serving nutrition against the user's own band, minimum and weekday limit |
| liked / disliked cuisine and ingredients | the preference scorer's own components (staples do not count as "liked") |
| rules, `n_allowed`, `violations` | `optimizer.hard_rules.violation_masks` / `count_violations` |
| `SolverFacts.terms` | `WeekPlan.diagnostics["cost_<term>"]`, whose sum is the objective the solver minimised |
| `estimated_deadline_items` | pantry items whose deadline inside the plan was estimated, not stated |
| `assumed_quantities` | pantry items whose *amount* is our estimate (`PantryItem.quantity_assumed`, set by the parser) |

## Decisions

* **The replay, not the solver's `use` variables, supplies per-dinner pantry use.** One definition of "used" across
  app, evaluation and explanation; a test cross-checks the totals against the model's (≤ 2 g).
* **Deadlines at or beyond the horizon are no deadline** (the model does the same), so they create no waste and no
  "expires" sentence.
* **Stock with several deadlines uses the earliest; it counts as "stated" only if every item at that deadline was
  stated** — one guess makes the date a guess (mirrors the optimiser's confidence rule).

## Limits

* **A gap below `GAP_TOLERANCE` (0.05 kcal / g) is float noise, not a miss**; larger gaps are reported even if tiny, and printed with a decimal ("0.4 g short") so a miss never reads as "0".
* **It cannot say why a rejected recipe lost.** The solver does not record that; inventing it would be exactly the
  rationalisation the project forbids.
* Per-dinner pantry allocation is the replay's (greedy by day). The solver may have allocated the same stock to a
  different day at equal cost; totals agree, individual days can differ.
* Cost-term shares depend on the optimiser's hand-set weights.

## Tests

[`tests/explain/test_facts.py`](../tests/explain/test_facts.md)

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Added assumed quantities (`PantryItem.quantity_assumed`), `GAP_TOLERANCE`, and `groceries_by_day` from the replay instead of recomputing shortfalls here.
- 2026-10-16 — Facts come from `replay_with_substitutions`; added `SubstitutionFact` / `DayFacts.substitutions`.
