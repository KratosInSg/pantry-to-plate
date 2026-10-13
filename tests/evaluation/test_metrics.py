"""Tests for ``evaluation/metrics.py``: hand-checkable plans, and the paired comparison."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domain.models import PantryItem, Scenario, UserProfile, WeekPlan
from evaluation.metrics import HIGHER_IS_BETTER, evaluate_plan, paired_bootstrap, summarise


def _plan(ctx, *row_indices) -> WeekPlan:
    return WeekPlan(planner="hand", recipe_ids=[ctx.catalog.recipe_id_of(i) for i in row_indices], status="ok")


def _stock_for(ctx, idx, factor=1.0, **kw) -> list[PantryItem]:
    ids, grams = ctx.catalog.ingredients(idx)
    return [PantryItem(ingredient_id=int(i), grams=float(g) * factor, **kw)
            for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids and g > 0]


def test_a_fully_stocked_dinner_needs_nothing_and_wastes_nothing(ctx):
    sc = Scenario(scenario_id="m1", horizon_days=1, pantry=_stock_for(ctx, 500))
    m = evaluate_plan(sc, _plan(ctx, 500), ctx)
    assert m.complete == 1.0 and m.n_meals == 1
    assert m.pantry_utilisation_pct == pytest.approx(100.0, abs=0.01)
    assert m.grocery_items == 0 and m.grocery_g == pytest.approx(0, abs=1e-3)
    assert m.waste_g == 0 and m.violations == 0


def test_an_empty_pantry_means_everything_is_bought(ctx):
    sc = Scenario(scenario_id="m2", horizon_days=1)
    m = evaluate_plan(sc, _plan(ctx, 500), ctx)
    assert m.pantry_utilisation_pct == 0.0
    assert m.grocery_items > 0 and m.grocery_g > 0


def test_waste_is_measured_against_the_hidden_truth_not_the_planners_belief(ctx):
    used = {int(i) for r in (10, 20) for i in ctx.catalog.ingredients(r)[0]}
    never_cooked = next(int(i) for i in ctx.catalog.flat[1] if int(i) not in used and int(i) not in ctx.ignore_ids)
    # the planner was told "no deadline"; in truth the stock is only good on day 0
    item = PantryItem(ingredient_id=never_cooked, grams=400.0, last_use_day=None)
    sc = Scenario(scenario_id="m3", horizon_days=2, pantry=[item], true_last_use_day={never_cooked: 0})
    m = evaluate_plan(sc, _plan(ctx, 10, 20), ctx)
    assert m.waste_g == pytest.approx(400.0)
    assert m.waste_pct == pytest.approx(100.0)
    # ...whereas with no hidden truth the same stock merely keeps
    no_truth = Scenario(scenario_id="m3b", horizon_days=2, pantry=[item])
    assert evaluate_plan(no_truth, _plan(ctx, 10, 20), ctx).waste_g == 0.0


def test_violations_are_counted(ctx):
    vegan_violator = int(np.flatnonzero(~ctx.catalog.flag("is_vegan"))[0])
    from domain.models import Diet
    sc = Scenario(scenario_id="m4", horizon_days=1, profile=UserProfile(diet=Diet.VEGAN))
    assert evaluate_plan(sc, _plan(ctx, vegan_violator), ctx).violations >= 1


def test_disliked_rate_and_preference(ctx):
    ids, _ = ctx.catalog.ingredients(500)
    disliked = int(ids[0])
    sc = Scenario(scenario_id="m5", horizon_days=1, profile=UserProfile(disliked_ingredient_ids=frozenset({disliked})))
    m = evaluate_plan(sc, _plan(ctx, 500), ctx)
    assert m.disliked_rate == 1.0 and 0.0 <= m.preference_mean <= 1.0


def test_weekend_dinners_do_not_count_as_weekday_overtime(ctx):
    slow = int(np.argmax(ctx.catalog.minutes))
    profile = UserProfile(max_weekday_minutes=30)
    weekend = Scenario(scenario_id="m6", horizon_days=1, start_weekday=5, profile=profile)    # Saturday
    weekday = Scenario(scenario_id="m6b", horizon_days=1, start_weekday=0, profile=profile)   # Monday
    assert evaluate_plan(weekend, _plan(ctx, slow), ctx).weekday_overtime_rate == 0.0
    assert evaluate_plan(weekday, _plan(ctx, slow), ctx).weekday_overtime_rate == 1.0


def test_incomplete_plans_are_flagged(ctx):
    sc = Scenario(scenario_id="m7", horizon_days=7)
    assert evaluate_plan(sc, _plan(ctx, 1, 2, 3), ctx).complete == 0.0


def test_nutrition_band_metrics(ctx):
    kcal = ctx.catalog.kcal
    profile = UserProfile()                                   # band 480..720 kcal
    inside = int(np.flatnonzero((kcal > 520) & (kcal < 680))[0])
    outside = int(np.flatnonzero(kcal > 1500)[0])
    sc = Scenario(scenario_id="m8", horizon_days=2, profile=profile)
    m = evaluate_plan(sc, _plan(ctx, inside, outside), ctx)
    assert m.nutrition_in_range_pct == pytest.approx(50.0)
    assert m.nutrition_dev_pct > 0


# ------------------------------------------------------------------------------------------- paired comparison
def _frame(a_values, b_values, metric="waste_g") -> pd.DataFrame:
    rows = []
    for k, (a, b) in enumerate(zip(a_values, b_values)):
        rows.append({"scenario_id": f"s{k}", "planner": "A", metric: a})
        rows.append({"scenario_id": f"s{k}", "planner": "B", metric: b})
    return pd.DataFrame(rows)


def test_paired_bootstrap_reports_direction_and_interval():
    df = _frame([8, 9, 10, 11, 12], [10, 11, 12, 13, 14])          # A wastes 2 g less in every scenario
    r = paired_bootstrap(df, "waste_g", "A", "B")
    assert r["n"] == 5 and r["mean_diff"] == pytest.approx(-2.0)
    assert r["ci_low"] <= -2.0 <= r["ci_high"]
    assert r["share_a_better"] == 1.0                                # lower waste is better


def test_paired_bootstrap_respects_metric_direction():
    df = _frame([60, 70], [50, 50], metric="nutrition_in_range_pct")
    assert HIGHER_IS_BETTER["nutrition_in_range_pct"]
    assert paired_bootstrap(df, "nutrition_in_range_pct", "A", "B")["share_a_better"] == 1.0


def test_paired_bootstrap_only_uses_shared_scenarios():
    df = pd.concat([_frame([1, 2, 3], [2, 3, 4]),
                    pd.DataFrame([{"scenario_id": "only-a", "planner": "A", "waste_g": 99}])])
    assert paired_bootstrap(df, "waste_g", "A", "B")["n"] == 3


def test_summarise_groups_by_planner():
    full = {m: 0.0 for m in HIGHER_IS_BETTER}
    df = pd.DataFrame([{**full, "planner": "A", "waste_g": 10.0}, {**full, "planner": "A", "waste_g": 20.0},
                       {**full, "planner": "B", "waste_g": 5.0}])
    s = summarise(df)
    assert s.loc["A", "waste_g"] == 15.0 and s.loc["B", "waste_g"] == 5.0
