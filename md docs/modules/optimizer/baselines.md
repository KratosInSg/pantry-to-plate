# `src/optimizer/baselines.py`

## Purpose

The comparison the optimiser has to beat (`md docs/evaluation.md`). Both baselines respect the hard rules, so the
comparison isolates **planning quality**, not safety.

| Planner | Behaviour | Why it is the right baseline |
| --- | --- | --- |
| `RandomFeasiblePlanner` | Seven distinct recipes drawn uniformly from the feasible set | The floor: a method that cannot beat this is not planning |
| `GreedyIngredientMatchPlanner` | Each day: the unused feasible recipe with the largest share of its mass already in the pantry; stock is reduced after each choice; ties broken by popularity then index | "How most recipe apps work": myopic, one meal at a time. It ignores expiry, nutrition, preferences and cooking time — exactly the behaviour joint weekly planning is claimed to beat |

Both are deterministic given the scenario (random also takes a planner seed combined with the scenario's seed, so a
scenario always receives the same "random" week).

## Public API

`RandomFeasiblePlanner(ctx, seed=0)`, `GreedyIngredientMatchPlanner(ctx)`; both implement `Planner`.

## Limits

* Greedy is a strong-ish baseline on pantry utilisation: it chases pantry overlap with no regard for anything else.
  That is intentional; beating it on waste, groceries *and* nutrition together is the claim.
* They plan 7 distinct dinners (no repeats), the same rule the optimiser uses.

## Tests

[`tests/optimizer/test_planning_and_baselines.py`](../tests/optimizer/test_planning_and_baselines.md)

## Change log

- 2026-10-12 — Created.
