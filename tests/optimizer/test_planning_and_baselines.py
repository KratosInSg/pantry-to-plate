"""Tests for ``optimizer/planning.py`` and ``optimizer/baselines.py`` against the real dataset.

The baselines are what the optimiser is measured against, so their own contracts are pinned here: deterministic,
hard-rule-safe, seven distinct dinners, and (for greedy) actually driven by the pantry.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import Diet, PantryItem, Scenario, UserProfile
from optimizer.baselines import GreedyIngredientMatchPlanner, RandomFeasiblePlanner
from optimizer.hard_rules import count_violations, feasible_mask
from optimizer.planning import plan_from_indices, prepare


def _indices(ctx, plan):
    return [ctx.catalog.index_of(r) for r in plan.recipe_ids]


# ----------------------------------------------------------------------------------------------------- planning
def test_context_knows_the_assumed_available_staples(ctx, store):
    tbl = store.all_ingredients()
    expected = set(int(i) for i in tbl.loc[tbl.is_assumed_available, "ingredient_id"])
    assert expected and set(ctx.ignore_ids) == expected


def test_prepare_applies_the_hard_rules_and_scores_preferences(ctx):
    sc = Scenario(scenario_id="t", profile=UserProfile(diet=Diet.VEGAN))
    prepared = prepare(sc, ctx)
    assert np.array_equal(prepared.feasible, feasible_mask(ctx.catalog, sc.profile))
    assert prepared.preference.shape == (ctx.catalog.n,)
    assert len(prepared.feasible_indices) == int(prepared.feasible.sum())


def test_plan_from_indices_statuses(ctx):
    full = plan_from_indices("x", ctx, [0, 1, 2, 3, 4, 5, 6], 7)
    assert full.status == "ok" and full.is_complete
    assert full.recipe_ids == [ctx.catalog.recipe_id_of(i) for i in range(7)]       # converted to Food.com ids
    assert plan_from_indices("x", ctx, [0, 1], 7).status == "partial"
    assert plan_from_indices("x", ctx, [], 7).status == "no_candidates"
    assert plan_from_indices("x", ctx, [0], 7, status="optimal", gap=0.01).diagnostics == {"gap": 0.01}


# ----------------------------------------------------------------------------------------------------- baselines
@pytest.mark.parametrize("make", [lambda c: RandomFeasiblePlanner(c, seed=1), GreedyIngredientMatchPlanner])
def test_baselines_are_deterministic_distinct_and_safe(ctx, make):
    profile = UserProfile(diet=Diet.VEGETARIAN, allergens=frozenset({"peanut", "dairy"}))
    sc = Scenario(scenario_id="s", seed=7, profile=profile)
    p1, p2 = make(ctx).plan(sc), make(ctx).plan(sc)
    assert p1.recipe_ids == p2.recipe_ids
    assert len(p1.recipe_ids) == 7 and len(set(p1.recipe_ids)) == 7
    assert p1.status == "ok"
    assert count_violations(ctx.catalog, profile, _indices(ctx, p1)) == 0


def test_random_planner_varies_with_the_scenario_seed(ctx):
    planner = RandomFeasiblePlanner(ctx, seed=0)
    a = planner.plan(Scenario(scenario_id="a", seed=1))
    b = planner.plan(Scenario(scenario_id="b", seed=2))
    assert a.recipe_ids != b.recipe_ids


def test_greedy_cooks_what_the_pantry_covers(ctx):
    ids, grams = ctx.catalog.ingredients(500)
    counted = [(int(i), float(g)) for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids and g > 0]
    assert counted
    pantry = [PantryItem(ingredient_id=i, grams=g * 10) for i, g in counted]
    sc = Scenario(scenario_id="g", pantry=pantry)
    plan = GreedyIngredientMatchPlanner(ctx).plan(sc)
    first = ctx.catalog.index_of(plan.recipe_ids[0])
    first_ids, _ = ctx.catalog.ingredients(first)
    stocked = {i for i, _ in counted} | set(ctx.ignore_ids)
    assert set(first_ids.tolist()) <= stocked          # day 0 uses nothing it would have to buy


def test_empty_feasible_set_is_reported_as_no_candidates(ctx):
    # the shortest recipe in the dataset takes 5 minutes, so a 4-minute cap leaves nothing
    sc = Scenario(scenario_id="none", profile=UserProfile(max_total_minutes=4))
    for planner in (RandomFeasiblePlanner(ctx), GreedyIngredientMatchPlanner(ctx)):
        plan = planner.plan(sc)
        assert plan.recipe_ids == [] and plan.status == "no_candidates" and not plan.is_complete


def test_fewer_than_a_week_of_options_is_reported_as_partial(ctx):
    base = UserProfile(diet=Diet.VEGAN, max_total_minutes=5)
    ok = np.flatnonzero(feasible_mask(ctx.catalog, base))
    keep, rest = ok[:3], ok[3:]
    keep_ingredients = {int(i) for r in keep for i in ctx.catalog.ingredients(int(r))[0]}
    banned = {int(i) for r in rest for i in ctx.catalog.ingredients(int(r))[0]} - keep_ingredients
    profile = base.model_copy(update={"excluded_ingredient_ids": frozenset(banned)})
    n_ok = int(feasible_mask(ctx.catalog, profile).sum())
    assert 3 <= n_ok < 7                                    # the construction above must leave a handful
    for planner in (RandomFeasiblePlanner(ctx), GreedyIngredientMatchPlanner(ctx)):
        plan = planner.plan(Scenario(scenario_id="few", profile=profile))
        assert len(plan.recipe_ids) == n_ok and plan.status == "partial"
