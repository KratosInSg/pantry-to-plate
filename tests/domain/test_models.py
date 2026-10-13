"""Tests for ``domain/models.py``: validation rules and the small derived properties."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.models import Diet, PantryItem, Scenario, UserProfile, WeekPlan


def test_dinner_target_and_band_follow_the_profile():
    p = UserProfile()                                    # 2000 kcal/day, 30 % at dinner, +/- 20 %
    assert p.dinner_kcal_target == pytest.approx(600)
    lo, hi = p.dinner_kcal_range
    assert (lo, hi) == (pytest.approx(480), pytest.approx(720))


def test_profile_rejects_an_unknown_allergen():
    with pytest.raises(ValidationError):
        UserProfile(allergens=frozenset({"dairy", "kryptonite"}))


def test_profile_accepts_every_known_allergen():
    assert UserProfile(allergens=frozenset({"dairy", "tree_nut"})).allergens == {"dairy", "tree_nut"}


def test_profile_rejects_absurd_calorie_targets():
    with pytest.raises(ValidationError):
        UserProfile(daily_kcal_target=100)


def test_defaults_are_the_least_restrictive_profile():
    p = UserProfile()
    assert p.diet is Diet.OMNIVORE
    assert not p.allergens and not p.excluded_ingredient_ids and p.max_total_minutes is None


def test_pantry_item_needs_positive_grams():
    with pytest.raises(ValidationError):
        PantryItem(ingredient_id=1, grams=0)


def test_is_weekday_respects_the_start_weekday():
    monday_start = Scenario(scenario_id="a", start_weekday=0)
    assert [monday_start.is_weekday(d) for d in range(7)] == [True] * 5 + [False] * 2
    friday_start = Scenario(scenario_id="b", start_weekday=4)       # Fri, Sat, Sun, Mon, Tue ...
    assert [friday_start.is_weekday(d) for d in range(7)] == [True, False, False, True, True, True, True]


def test_scenario_horizon_is_bounded():
    with pytest.raises(ValidationError):
        Scenario(scenario_id="x", horizon_days=0)


def test_week_plan_completeness():
    assert WeekPlan(planner="p", recipe_ids=[1, 2], status="optimal").is_complete
    assert WeekPlan(planner="p", recipe_ids=[1], status="feasible").is_complete
    assert not WeekPlan(planner="p", recipe_ids=[], status="optimal").is_complete        # nothing planned
    assert not WeekPlan(planner="p", recipe_ids=[1], status="partial").is_complete
    assert not WeekPlan(planner="p", status="infeasible").is_complete
