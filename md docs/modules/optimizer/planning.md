# `src/optimizer/planning.py`

## Purpose

The shared plumbing that makes the comparison between methods fair: the `Planner` interface and the per-scenario
preparation every method reuses (hard-rule filter + preference scores + staples).

## Public API

| Name | What |
| --- | --- |
| `Planner` (Protocol) | `name: str` and `plan(scenario) -> WeekPlan` |
| `PlanningContext` | `catalog`, `store`, `ignore_ids` (assumed-available staples), `preference_weights`. Holds no scenario state |
| `make_context(catalog=None, store=None, preference_weights=...)` | Build a context from the default dataset |
| `prepare(scenario, ctx) -> Prepared` | `feasible` mask + `preference` scores (+ `feasible_indices`) |
| `plan_from_indices(planner, ctx, indices, horizon, status=None, **diagnostics) -> WeekPlan` | Convert catalogue rows to Food.com ids and pick the status (`ok` / `partial` / `no_candidates`) |

## Decisions

* **Contexts, not globals.** Planners are constructed with a `PlanningContext`, so tests and the benchmark can inject
  small or modified catalogues.
* **Staples are data, not code.** `ignore_ids` comes from the `is_assumed_available` column of the ingredient table
  (water, salt, pepper …), so changing the assumption is a reference-CSV edit and a rebuild.

## Tests

[`tests/optimizer/test_planning_and_baselines.py`](../tests/optimizer/test_planning_and_baselines.md)

## Change log

- 2026-10-12 — Created.
