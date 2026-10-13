"""Tests for ``explain/facts.py``: every fact is read from the replay, the rules or the solver - never made up.

Plans are built by hand (``plan_from_indices``) where a test needs to know the answer in advance, and from the real
optimiser (``optimised_week``) where it needs the solver's own numbers.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import Diet, PantryItem, Scenario, UserProfile
from explain.facts import KCAL_ABOVE, KCAL_BELOW, KCAL_IN_RANGE, build_facts
from nlp.schemas import Urgency
from optimizer.baselines import RandomFeasiblePlanner
from optimizer.hard_rules import violation_masks
from optimizer.inventory import account_inventory, deadlines_from_pantry
from optimizer.planning import plan_from_indices
from optimizer.weekly import COST_TERMS

WEEK = [500, 501, 502, 503, 504, 505, 506]        # seven distinct, arbitrary catalogue rows


def _plan(ctx, indices=WEEK):
    return plan_from_indices("manual", ctx, list(indices), 7)


def _name(ctx, iid: int) -> str:
    return ctx.store.ingredient(int(iid)).canonical_name


def _stock_of(ctx, idx: int, factor: float = 2.0, **kw) -> list[PantryItem]:
    """Pantry holding ``factor`` x every (non-staple) ingredient of recipe ``idx``."""
    ids, grams = ctx.catalog.ingredients(idx)
    return [PantryItem(ingredient_id=int(i), grams=float(g) * factor, **kw)
            for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids and g > 1]


def _recipe_with_kcal(ctx, low: float, high: float) -> int:
    kcal = ctx.catalog.kcal
    return int(np.flatnonzero((kcal > low) & (kcal < high))[0])


# --------------------------------------------------------------------------------------------- pantry and groceries
def test_pantry_use_and_deadlines_are_read_from_the_replay(ctx):
    pantry = _stock_of(ctx, 500, factor=2, last_use_day=2, expiry_known=True, urgency=Urgency.URGENT)
    facts = build_facts(Scenario(scenario_id="t", pantry=pantry), _plan(ctx), ctx)
    day0 = facts.days[0]
    assert day0.recipe_id == ctx.catalog.recipe_id_of(500)
    assert day0.pantry_uses, "the whole recipe is in the pantry, so day 0 must use pantry stock"
    for use in day0.pantry_uses:
        assert use.last_use_day == 2 and use.deadline_known and use.said_urgent
    ids, grams = ctx.catalog.ingredients(500)
    wanted = {_name(ctx, i): float(g) for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids and g > 1}
    assert {u.name: u.grams for u in day0.pantry_uses} == pytest.approx(wanted, rel=1e-4)
    assert all(g.grams <= 1.0 + 1e-6 for g in day0.groceries)         # only sub-gram items were left out of the pantry


def test_week_totals_equal_the_inventory_replay_and_the_per_day_lists(ctx):
    """One definition of used / bought / wasted everywhere: the explainer must agree with the grocery box."""
    pantry = _stock_of(ctx, 500, factor=1.5, last_use_day=2, expiry_known=True) + \
        _stock_of(ctx, 503, factor=0.4, last_use_day=1, expiry_known=False, expiry_confidence=0.6)
    sc = Scenario(scenario_id="t", pantry=pantry)
    facts = build_facts(sc, _plan(ctx), ctx)
    rep = account_inventory(WEEK, pantry, ctx.catalog, {i: d if d is not None and d < 7 else None for i, d in
                                                        deadlines_from_pantry(pantry).items()}, ctx.ignore_ids, 7)
    assert facts.waste_g == pytest.approx(rep.total_waste_g)
    assert facts.pantry_consumed_g == pytest.approx(rep.total_consumed_g)
    assert facts.n_grocery_items == rep.n_grocery_items
    assert sum(g.grams for g in facts.groceries) == pytest.approx(rep.total_groceries_g)
    assert sum(g.grams for d in facts.days for g in d.groceries) == pytest.approx(rep.total_groceries_g)


def test_leftover_stock_that_will_expire_unused_is_reported(ctx):
    spinach = int(ctx.store.ingredient_by_name("spinach").ingredient_id)
    # precondition: none of the planned dinners uses spinach, so all of it must be left over (not a vacuous test)
    assert not set(WEEK) & set(ctx.catalog.recipes_using(spinach).tolist())
    pantry = [PantryItem(ingredient_id=spinach, grams=400, last_use_day=1, expiry_known=True)]
    facts = build_facts(Scenario(scenario_id="t", pantry=pantry), _plan(ctx), ctx)
    assert facts.waste_g == pytest.approx(400.0) and facts.expiring_stock_g == pytest.approx(400.0)
    assert len(facts.leftovers) == 1
    left = facts.leftovers[0]
    assert (left.name, left.grams, left.last_use_day, left.deadline_known) == ("spinach", pytest.approx(400.0), 1, True)


def test_stock_that_expires_before_a_dinner_needs_it_is_reported_as_rebought(ctx):
    """Own 100x the ingredients of recipe 500 but they expire today; the plan cooks 500 on day 3. The replay buys them
    again - the explainer must say so instead of leaving the user wondering why food they own is on the shopping list."""
    pantry = _stock_of(ctx, 500, factor=100, last_use_day=0, expiry_known=True)
    plan = _plan(ctx, [501, 502, 503, 500, 504, 505, 506])
    facts = build_facts(Scenario(scenario_id="t", pantry=pantry), plan, ctx)
    ids, _ = ctx.catalog.ingredients(500)
    on_day3 = {g.name for g in facts.days[3].groceries}
    stranded = {s.name for s in facts.stranded}
    assert stranded, "stock that expired before its dinner must be listed"
    assert stranded <= on_day3 | {g.name for d in facts.days for g in d.groceries}
    assert all(s.last_use_day == 0 and s.deadline_known for s in facts.stranded)


def test_estimated_deadlines_are_listed_but_stated_ones_are_not(ctx):
    spinach = ctx.store.ingredient_by_name("spinach").ingredient_id
    milk = ctx.store.ingredient_by_name("milk").ingredient_id
    pantry = [PantryItem(ingredient_id=int(spinach), grams=100, last_use_day=2, expiry_known=False,
                         expiry_confidence=0.5),
              PantryItem(ingredient_id=int(milk), grams=100, last_use_day=3, expiry_known=True)]
    facts = build_facts(Scenario(scenario_id="t", pantry=pantry), _plan(ctx), ctx)
    assert facts.estimated_deadline_items == ("spinach",)


def test_deadlines_beyond_the_plan_are_not_deadlines(ctx):
    spinach = ctx.store.ingredient_by_name("spinach").ingredient_id
    pantry = [PantryItem(ingredient_id=int(spinach), grams=100, last_use_day=20, expiry_known=False)]
    facts = build_facts(Scenario(scenario_id="t", pantry=pantry), _plan(ctx), ctx)
    assert facts.estimated_deadline_items == () and facts.waste_g == 0 and not facts.stranded


# --------------------------------------------------------------------------------------------- nutrition and time
@pytest.mark.parametrize("scale, status", [(1.0, KCAL_IN_RANGE), (2.0, KCAL_BELOW), (0.5, KCAL_ABOVE)])
def test_kcal_status_is_measured_against_the_users_own_band(ctx, scale, status):
    idx = _recipe_with_kcal(ctx, 400, 800)
    kcal = float(ctx.catalog.kcal[idx])
    profile = UserProfile(daily_kcal_target=kcal * scale / 0.30)       # dinner target = kcal * scale (30 % share)
    facts = build_facts(Scenario(scenario_id="t", profile=profile), _plan(ctx, [idx]), ctx)
    day = facts.days[0]
    low, high = profile.dinner_kcal_range
    assert day.kcal_status == status
    expected_gap = 0.0 if status == KCAL_IN_RANGE else (low - kcal if status == KCAL_BELOW else kcal - high)
    assert day.kcal_gap == pytest.approx(expected_gap, abs=1e-3)


def test_protein_shortfall_is_the_distance_to_the_minimum(ctx):
    idx = _recipe_with_kcal(ctx, 400, 800)
    protein = float(ctx.catalog.protein_g[idx])
    short = build_facts(Scenario(scenario_id="t", profile=UserProfile(min_protein_g_per_dinner=protein + 10)),
                        _plan(ctx, [idx]), ctx).days[0]
    met = build_facts(Scenario(scenario_id="t", profile=UserProfile(min_protein_g_per_dinner=max(0.0, protein - 1))),
                      _plan(ctx, [idx]), ctx).days[0]
    assert short.protein_gap_g == pytest.approx(10.0, abs=1e-3)
    assert met.protein_gap_g == 0.0


def test_weekday_time_limit_applies_to_weekdays_only(ctx):
    idx = int(np.flatnonzero(ctx.catalog.minutes >= 40)[0])
    minutes = int(ctx.catalog.minutes[idx])
    profile = UserProfile(max_weekday_minutes=minutes - 10)
    monday = build_facts(Scenario(scenario_id="t", profile=profile, start_weekday=0), _plan(ctx, [idx]), ctx).days[0]
    saturday = build_facts(Scenario(scenario_id="t", profile=profile, start_weekday=5), _plan(ctx, [idx]), ctx).days[0]
    assert monday.weekday == "Monday" and monday.is_weekday and monday.minutes_over == 10
    assert saturday.weekday == "Saturday" and not saturday.is_weekday and saturday.minutes_over == 0


# --------------------------------------------------------------------------------------------- preference
def test_preference_reasons_are_the_scorers_own_components(ctx):
    cat = ctx.catalog
    idx = next(i for i in range(500, 3000) if cat.cuisine[i] is not None)
    ids, _ = cat.ingredients(idx)
    food = next(int(i) for i in ids if int(i) not in ctx.ignore_ids)
    other = next(int(i) for i in ids if int(i) not in ctx.ignore_ids and int(i) != food)
    profile = UserProfile(liked_cuisines=frozenset({cat.cuisine[idx]}), liked_ingredient_ids=frozenset({food}),
                          disliked_ingredient_ids=frozenset({other}))
    day = build_facts(Scenario(scenario_id="t", profile=profile), _plan(ctx, [idx]), ctx).days[0]
    assert day.liked_cuisine and not day.disliked_cuisine
    assert day.liked_ingredients == (_name(ctx, food),)
    assert day.disliked_ingredients == (_name(ctx, other),)
    flipped = UserProfile(disliked_cuisines=frozenset({cat.cuisine[idx]}))
    day = build_facts(Scenario(scenario_id="t", profile=flipped), _plan(ctx, [idx]), ctx).days[0]
    assert day.disliked_cuisine and not day.liked_cuisine


# --------------------------------------------------------------------------------------------- rules
def test_rule_counts_come_from_the_hard_rule_masks(ctx):
    profile = UserProfile(diet=Diet.VEGAN, allergens=frozenset({"peanut"}), avoid_alcohol=True)
    masks = violation_masks(ctx.catalog, profile)
    allowed = np.flatnonzero(~np.any(np.vstack(list(masks.values())), axis=0))[:7].tolist()
    facts = build_facts(Scenario(scenario_id="t", profile=profile), _plan(ctx, allowed), ctx)
    assert [r.name for r in facts.rules] == list(masks)
    assert [r.n_excluded for r in facts.rules] == [int(m.sum()) for m in masks.values()]
    assert facts.n_allowed == int((~np.any(np.vstack(list(masks.values())), axis=0)).sum())
    assert facts.n_catalogue == ctx.catalog.n and facts.violations == 0


def test_a_plan_that_breaks_a_rule_is_reported_as_such(ctx):
    meat = int(np.flatnonzero(ctx.catalog.flag("contains_meat"))[0])
    profile = UserProfile(diet=Diet.VEGAN)
    facts = build_facts(Scenario(scenario_id="t", profile=profile), _plan(ctx, [meat]), ctx)
    assert facts.violations >= 1


def test_no_plan_still_explains_the_rules(ctx):
    profile = UserProfile(max_total_minutes=1)                        # no dinner takes one minute
    facts = build_facts(Scenario(scenario_id="t", profile=profile), _plan(ctx, []), ctx)
    assert facts.days == () and not facts.complete and facts.status == "no_candidates"
    assert facts.n_allowed == 0 and facts.rules[0].name == "time" and facts.rules[0].n_excluded == ctx.catalog.n


# --------------------------------------------------------------------------------------------- solver
def test_solver_facts_carry_the_optimisers_cost_terms(ctx, optimised_week):
    scenario, plan = optimised_week
    solver = build_facts(scenario, plan, ctx).solver
    assert solver is not None and solver.status in ("optimal", "feasible")
    assert set(solver.terms) == set(COST_TERMS)
    assert sum(solver.terms.values()) == pytest.approx(solver.objective, abs=2e-3)
    assert solver.backend == "highs"


def test_baselines_have_no_solver_facts(ctx):
    sc = Scenario(scenario_id="t")
    plan = RandomFeasiblePlanner(ctx).plan(sc)
    facts = build_facts(sc, plan, ctx)
    assert facts.solver is None and facts.complete


def test_optimiser_plan_facts_are_complete_and_safe(ctx, optimised_week):
    scenario, plan = optimised_week
    facts = build_facts(scenario, plan, ctx)
    assert facts.complete and facts.n_dinners == scenario.horizon_days and facts.violations == 0
    assert [d.recipe_id for d in facts.days] == plan.recipe_ids


def test_assumed_quantities_are_listed_but_stated_ones_are_not(ctx):
    spinach = int(ctx.store.ingredient_by_name("spinach").ingredient_id)
    milk = int(ctx.store.ingredient_by_name("milk").ingredient_id)
    pantry = [PantryItem(ingredient_id=spinach, grams=250, quantity_assumed=True),
              PantryItem(ingredient_id=milk, grams=500)]
    facts = build_facts(Scenario(scenario_id="t", pantry=pantry), _plan(ctx), ctx)
    assert [(a.name, a.grams) for a in facts.assumed_quantities] == [("spinach", 250.0)]
