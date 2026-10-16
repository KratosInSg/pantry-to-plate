"""Tests for ``optimizer/weekly.py`` (the weekly MILP) on real scenarios from the benchmark generator.

These are integration tests: they solve real models (a few seconds each), so the shortlist is kept small. What they pin:
safety (no hard-rule violation), that the model's own cost terms agree with the independent inventory replay, that
known use-by dates structurally cannot be planned past, and that the optimiser really does pull expiring stock in.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import Diet, PantryItem, Scenario, UserProfile
from evaluation.scenarios import generate_scenario
from optimizer.baselines import RandomFeasiblePlanner
from optimizer.candidates import ShortlistConfig, shortlist
from optimizer.hard_rules import count_violations
from optimizer.inventory import account_inventory, deadlines_from_pantry
from optimizer.planning import prepare
from optimizer.weekly import ABLATIONS, COST_TERMS, DEFAULT_WEIGHTS, WeeklyPlanner, make_planner

SMALL = ShortlistConfig(size=50)


def _planner(ctx, **kw) -> WeeklyPlanner:
    kw.setdefault("shortlist_config", SMALL)
    kw.setdefault("time_limit_s", 20.0)
    kw.setdefault("mip_rel_gap", 1e-3)
    return WeeklyPlanner(ctx, **kw)


@pytest.fixture(scope="module")
def expiry_scenario(catalog, store) -> Scenario:
    return generate_scenario("expiry_heavy", 20261012, catalog, store)


@pytest.fixture(scope="module")
def solved(ctx, expiry_scenario):
    planner = _planner(ctx)
    return planner.plan(expiry_scenario)


def _idx(ctx, plan):
    return [ctx.catalog.index_of(r) for r in plan.recipe_ids]


def test_plan_is_a_complete_distinct_and_safe_week(ctx, expiry_scenario, solved):
    assert solved.status in ("optimal", "feasible") and solved.is_complete
    assert len(solved.recipe_ids) == expiry_scenario.horizon_days
    assert len(set(solved.recipe_ids)) == len(solved.recipe_ids)
    assert count_violations(ctx.catalog, expiry_scenario.profile, _idx(ctx, solved)) == 0


def test_model_cost_terms_agree_with_the_inventory_replay(ctx, expiry_scenario, solved):
    """The explainer reads the model's terms; the evaluation re-measures by replay. They must tell the same story."""
    sc = expiry_scenario
    rep = account_inventory(_idx(ctx, solved), sc.pantry, ctx.catalog, deadlines_from_pantry(sc.pantry),
                            ctx.ignore_ids, sc.horizon_days)
    d = solved.diagnostics
    assert d["model_waste_g"] == pytest.approx(rep.total_waste_g, abs=2.0)
    assert d["model_grocery_g"] == pytest.approx(rep.total_groceries_g, abs=2.0)
    assert abs(d["model_grocery_items"] - rep.n_grocery_items) <= 2      # sub-gram demands are not modelled


def test_diagnostics_record_how_the_plan_was_made(solved):
    for key in ("n_feasible", "n_candidates", "solve_seconds", "objective", "mip_gap", "weights"):
        assert key in solved.diagnostics
    assert solved.diagnostics["n_candidates"] >= 7                       # at least a week of options


def test_cost_terms_are_reported_and_sum_to_the_objective(solved):
    """The explainer cites these per-term costs, so they must be the objective's real decomposition: every term
    present, none negative, and together exactly the objective the solver minimised."""
    d = solved.diagnostics
    terms = {name: d[f"cost_{name}"] for name in COST_TERMS}
    assert all(v >= -1e-9 for v in terms.values())
    assert sum(terms.values()) == pytest.approx(d["objective"], abs=2e-3)


def test_stock_is_never_planned_past_its_deadline(ctx, store):
    """Known use-by dates are hard: the model has no use variable for a day after the deadline."""
    spinach = store.ingredient_by_name("spinach").ingredient_id
    sc = Scenario(scenario_id="deadline", pantry=[PantryItem(ingredient_id=spinach, grams=300, last_use_day=1,
                                                             expiry_known=True)])
    planner = _planner(ctx)
    prepared = prepare(sc, ctx)
    cand = shortlist(ctx.catalog, sc.profile, sc.pantry, prepared.feasible, prepared.preference, ctx.ignore_ids, SMALL)
    _, handles = planner._build(sc, cand, prepared.preference)
    uses = handles["use"].get(spinach)
    assert uses is not None, "the shortlist guarantees options for urgent stock"
    assert len(uses) == 2                   # day 0 and day 1 only (last_use_day is inclusive)


def test_expiring_stock_is_pulled_into_the_plan(ctx):
    """Give the kitchen exactly one recipe's ingredients, all about to expire: the optimiser should cook them up."""
    ids, grams = ctx.catalog.ingredients(500)
    pantry = [PantryItem(ingredient_id=int(i), grams=float(g) * 2, last_use_day=2, expiry_known=True)
              for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids and g > 1]
    sc = Scenario(scenario_id="use-it-up", pantry=pantry, profile=UserProfile(daily_kcal_target=2200))
    opt = _planner(ctx).plan(sc)
    rnd = RandomFeasiblePlanner(ctx).plan(sc)
    visible = deadlines_from_pantry(pantry)

    def waste(plan):
        return account_inventory(_idx(ctx, plan), pantry, ctx.catalog, visible, ctx.ignore_ids, 7).total_waste_g

    total = sum(p.grams for p in pantry)
    assert waste(opt) < 0.6 * total                 # most of it gets cooked
    assert waste(opt) < waste(rnd)


def test_make_planner_names(ctx):
    assert make_planner("optimiser", ctx).weights == DEFAULT_WEIGHTS
    assert make_planner("opt_no_expiry", ctx).weights == ABLATIONS["no_expiry"]
    assert make_planner("opt_no_expiry", ctx).name == "opt_no_expiry"
    with pytest.raises(ValueError):
        make_planner("opt_nonsense", ctx)


def test_cpsat_suffix_selects_the_backend_and_keeps_the_name(ctx):
    assert make_planner("optimiser", ctx).backend == "highs"
    p = make_planner("optimiser_cpsat", ctx)
    assert p.backend == "cpsat" and p.name == "optimiser_cpsat" and p.weights == DEFAULT_WEIGHTS
    q = make_planner("opt_no_expiry_cpsat", ctx)
    assert q.backend == "cpsat" and q.weights == ABLATIONS["no_expiry"]
    with pytest.raises(ValueError):
        make_planner("opt_nonsense_cpsat", ctx)
    with pytest.raises(ValueError, match="unknown solver backend"):
        WeeklyPlanner(ctx, backend="gurobi")


def test_cpsat_backend_plans_a_safe_week_that_matches_highs(ctx, expiry_scenario, solved, cpsat_available):
    """Same scenario, same model, other solver: still a complete, safe plan whose model terms match the replay, and an
    objective no worse than HiGHS's beyond the two gap tolerances. A scaling bug in the CP-SAT path once made it
    'prove optimal' for a model that excluded better plans; this is the cross-check that catches that."""
    if not cpsat_available:
        pytest.skip("OR-Tools CP-SAT cannot be loaded on this machine")
    sc = expiry_scenario
    plan = _planner(ctx, backend="cpsat").plan(sc)
    assert plan.status in ("optimal", "feasible") and plan.is_complete
    assert plan.diagnostics["backend"] == "cpsat" and solved.diagnostics["backend"] == "highs"
    assert count_violations(ctx.catalog, sc.profile, _idx(ctx, plan)) == 0
    rep = account_inventory(_idx(ctx, plan), sc.pantry, ctx.catalog, deadlines_from_pantry(sc.pantry),
                            ctx.ignore_ids, sc.horizon_days)
    assert plan.diagnostics["model_waste_g"] == pytest.approx(rep.total_waste_g, abs=2.0)
    assert plan.diagnostics["model_grocery_g"] == pytest.approx(rep.total_groceries_g, abs=2.0)
    ref = solved.diagnostics["objective"]
    assert plan.diagnostics["objective"] <= ref + 0.01 * abs(ref) + 0.05


def test_nothing_feasible_is_reported_not_solved(ctx):
    sc = Scenario(scenario_id="none", profile=UserProfile(max_total_minutes=4))     # shortest recipe is 5 minutes
    plan = _planner(ctx).plan(sc)
    assert plan.status == "no_candidates" and plan.recipe_ids == []


def test_hard_rules_hold_for_a_restricted_user(ctx):
    profile = UserProfile(diet=Diet.VEGAN, allergens=frozenset({"soy", "gluten"}))
    sc = Scenario(scenario_id="vegan", profile=profile)
    plan = _planner(ctx).plan(sc)
    assert plan.is_complete
    assert count_violations(ctx.catalog, profile, _idx(ctx, plan)) == 0
    assert np.all(ctx.catalog.flag("is_vegan")[_idx(ctx, plan)])


def test_unusable_expiring_stock_still_counts_in_model_waste(ctx):
    """An expiring ingredient absent from every shortlisted recipe is unavoidable waste."""
    from optimizer.planning import prepare
    from optimizer.candidates import shortlist
    from optimizer.weekly import _aggregate_pantry
    from optimizer.backends import solve_highs
    from optimizer.inventory import visible_deadlines
    from optimizer.weekly import COST_TERMS
    from optimizer.candidates import ShortlistConfig
    from domain.models import PantryItem, Scenario
    from optimizer.weekly import WeeklyPlanner

    sc = Scenario(scenario_id="absent-expiring-stock", seed=12,
                  pantry=[PantryItem(ingredient_id=99999999, grams=100.,
                                     last_use_day=0, expiry_known=True)])
    prepared = prepare(sc, ctx)
    config = ShortlistConfig(size=15)
    cand = shortlist(ctx.catalog, sc.profile, sc.pantry, prepared.feasible,
                     prepared.preference, ctx.ignore_ids, config)
    planner = WeeklyPlanner(ctx, shortlist_config=config)
    model, handles = planner._build(sc, cand, prepared.preference)
    stock = handles["stock"]
    assert 99999999 in stock
    assert 99999999 not in handles["use"]
    item = stock[99999999]
    expected = planner.weights.waste_per_100g * item.urgency_factor * item.confidence
    assert handles["constant_waste_cost"] >= expected - 1e-6
