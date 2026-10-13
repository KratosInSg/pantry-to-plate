"""Baseline planners: the comparison the optimiser has to beat.

Two baselines, chosen to mirror the evaluation design (docs/evaluation.md):

``RandomFeasiblePlanner``
    Seven distinct recipes drawn uniformly from those that pass the hard rules. The floor: any method that cannot beat
    this is not planning at all. It *is* safe (it only draws from the feasible set), so safety is not what separates it
    from the others - waste, groceries and fit are.

``GreedyIngredientMatchPlanner``
    "How most recipe apps work": day by day, cook the not-yet-used recipe that makes the most of what is currently in
    the pantry. It is myopic on purpose - it ignores expiry dates, nutrition targets, preferences and cooking time, and
    never looks ahead - which is exactly the single-meal behaviour the project's joint weekly planning is claimed to
    beat. It also respects the hard rules, so the comparison isolates *planning quality*, not safety.

Both are deterministic given the scenario (and, for random, the planner seed).
"""
from __future__ import annotations

import numpy as np

from domain.models import Scenario, WeekPlan
from optimizer.planning import PlanningContext, plan_from_indices, prepare


class RandomFeasiblePlanner:
    """Uniform random choice among feasible recipes."""

    name = "random"

    def __init__(self, ctx: PlanningContext, seed: int = 0) -> None:
        self._ctx = ctx
        self._seed = seed

    def plan(self, scenario: Scenario) -> WeekPlan:
        prepared = prepare(scenario, self._ctx)
        feasible = prepared.feasible_indices
        # seed from (planner seed, scenario seed) so a scenario always gets the same "random" week
        rng = np.random.default_rng([self._seed, scenario.seed, 99])
        k = min(scenario.horizon_days, len(feasible))
        chosen = rng.choice(feasible, size=k, replace=False).tolist() if k else []
        return plan_from_indices(self.name, self._ctx, chosen, scenario.horizon_days, n_feasible=len(feasible))


class GreedyIngredientMatchPlanner:
    """Myopic pantry matcher: each day, the unused feasible recipe with the largest share of mass already in stock."""

    name = "greedy"

    def __init__(self, ctx: PlanningContext) -> None:
        self._ctx = ctx

    def plan(self, scenario: Scenario) -> WeekPlan:
        ctx = self._ctx
        prepared = prepare(scenario, ctx)
        feasible = prepared.feasible_indices
        owner, ids, grams = ctx.catalog.flat

        size = int(ids.max()) + 1
        stock = np.zeros(size, dtype=np.float32)
        for item in scenario.pantry:
            if item.ingredient_id < size and item.ingredient_id not in ctx.ignore_ids:
                stock[item.ingredient_id] += item.grams
        counted = np.ones(size, dtype=bool)
        counted[[i for i in ctx.ignore_ids if i < size]] = False

        # per recipe: total counted mass, and each flat row's weight, restricted to feasible recipes for speed
        row_counted = grams * counted[ids]
        total = np.bincount(owner, weights=row_counted, minlength=ctx.catalog.n)
        popularity = np.nan_to_num(ctx.catalog.rating_mean, nan=0.0)

        used: set[int] = set()
        chosen: list[int] = []
        feasible_mask_rows = prepared.feasible[owner]
        for _ in range(min(scenario.horizon_days, len(feasible))):
            covered = np.minimum(grams, stock[ids]) * counted[ids] * feasible_mask_rows
            cov_sum = np.bincount(owner, weights=covered, minlength=ctx.catalog.n)
            with np.errstate(divide="ignore", invalid="ignore"):
                share = np.where(total > 0, cov_sum / total, 0.0)
            share[~prepared.feasible] = -1.0
            if used:
                share[list(used)] = -1.0
            # ties (very common when the pantry is empty) broken by popularity, then by lowest index: deterministic
            best = int(np.lexsort((np.arange(ctx.catalog.n), -popularity, -share))[0])
            if share[best] < 0:
                break
            chosen.append(best)
            used.add(best)
            r_ids, r_g = ctx.catalog.ingredients(best)
            for iid, g in zip(r_ids.tolist(), r_g.tolist()):          # use up stock so the next day sees less
                if iid < size:
                    stock[iid] = max(0.0, stock[iid] - g)
        return plan_from_indices(self.name, ctx, chosen, scenario.horizon_days, n_feasible=len(feasible))
