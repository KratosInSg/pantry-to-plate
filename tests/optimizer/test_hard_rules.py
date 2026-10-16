"""Tests for ``optimizer/hard_rules.py``: nothing that breaks a rule is ever feasible.

These run against the real recipe flags, so they also guard the dataset build: a flag regression shows up here.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import Diet, UserProfile
from optimizer.hard_rules import (count_violations, feasible_mask, ingredient_violations, violated_rules,
                                  violation_masks)


def test_default_profile_allows_everything(catalog):
    assert feasible_mask(catalog, UserProfile()).all()
    assert violation_masks(catalog, UserProfile()) == {}


def test_vegan_keeps_exactly_the_vegan_recipes(catalog):
    ok = feasible_mask(catalog, UserProfile(diet=Diet.VEGAN))
    assert np.array_equal(ok, catalog.flag("is_vegan"))
    assert 0 < ok.sum() < catalog.n


def test_vegetarian_is_a_superset_of_vegan(catalog):
    veg = feasible_mask(catalog, UserProfile(diet=Diet.VEGETARIAN))
    vegan = feasible_mask(catalog, UserProfile(diet=Diet.VEGAN))
    assert np.all(veg[vegan]) and veg.sum() > vegan.sum()


def test_vegetarian_recipes_have_no_meat_fish_or_egg(catalog):
    ok = feasible_mask(catalog, UserProfile(diet=Diet.VEGETARIAN))
    for flag in ("contains_meat", "contains_poultry", "contains_fish", "contains_shellfish", "contains_egg"):
        assert not np.any(ok & catalog.flag(flag)), flag
    assert np.any(ok & catalog.flag("contains_dairy"))               # dairy stays allowed


def test_pescatarian_has_no_meat_or_poultry(catalog):
    ok = feasible_mask(catalog, UserProfile(diet=Diet.PESCATARIAN))
    assert not np.any(ok & (catalog.flag("contains_meat") | catalog.flag("contains_poultry")))
    # ...and it allows more than vegetarian (fish is fine)
    assert ok.sum() > feasible_mask(catalog, UserProfile(diet=Diet.VEGETARIAN)).sum()


@pytest.mark.parametrize("allergen", ["peanut", "dairy", "gluten", "shellfish"])
def test_allergen_recipes_are_never_feasible(catalog, allergen):
    ok = feasible_mask(catalog, UserProfile(allergens=frozenset({allergen})))
    assert not np.any(ok & catalog.flag(f"contains_{allergen}"))
    assert ok.sum() > 0


def test_pork_and_alcohol_rules_are_opt_in(catalog):
    assert feasible_mask(catalog, UserProfile()).sum() == catalog.n
    no_pork = feasible_mask(catalog, UserProfile(avoid_pork=True))
    assert not np.any(no_pork & catalog.flag("contains_pork"))
    no_alc = feasible_mask(catalog, UserProfile(avoid_alcohol=True))
    assert not np.any(no_alc & catalog.flag("contains_alcohol"))


def test_excluded_ingredient_is_never_used(catalog):
    ids, _ = catalog.ingredients(500)
    target = int(ids[0])
    ok = feasible_mask(catalog, UserProfile(excluded_ingredient_ids=frozenset({target})))
    assert not np.any(ok[catalog.recipes_using(target)])


def test_a_rejected_recipe_is_never_feasible_and_nothing_else_is_affected(catalog):
    rid = catalog.recipe_id_of(500)
    p = UserProfile(excluded_recipe_ids=frozenset({rid, 10**9}))        # 10**9 is not in the pool: ignored, no error
    ok = feasible_mask(catalog, p)
    assert not ok[500] and ok.sum() == catalog.n - 1
    assert [r.name for r in violated_rules(catalog, p, 500)] == ["excluded_recipe"]
    assert violation_masks(catalog, p)["excluded_recipe"].sum() == 1


def test_time_cap(catalog):
    ok = feasible_mask(catalog, UserProfile(max_total_minutes=30))
    assert np.all(catalog.minutes[ok] <= 30)
    assert ok.sum() > 0


def test_rules_combine_with_and(catalog):
    p = UserProfile(diet=Diet.VEGETARIAN, allergens=frozenset({"peanut"}), max_total_minutes=45)
    ok = feasible_mask(catalog, p)
    expected = catalog.flag("is_vegetarian") & ~catalog.flag("contains_peanut") & (catalog.minutes <= 45)
    assert np.array_equal(ok, expected)


def test_violated_rules_names_the_rule_and_explains_it(catalog):
    p = UserProfile(diet=Diet.VEGAN, allergens=frozenset({"peanut"}))
    both = np.flatnonzero(catalog.flag("contains_peanut") & ~catalog.flag("is_vegan"))
    assert len(both), "need a non-vegan peanut recipe for this test"
    rules = violated_rules(catalog, p, int(both[0]))
    assert {r.name for r in rules} == {"diet:vegan", "allergen:peanut"}
    assert any("peanut" in r.reason for r in rules)
    safe = int(np.flatnonzero(feasible_mask(catalog, p))[0])
    assert violated_rules(catalog, p, safe) == []


def test_count_violations_counts_meal_rule_pairs(catalog):
    p = UserProfile(diet=Diet.VEGAN, allergens=frozenset({"peanut"}))
    ok = np.flatnonzero(feasible_mask(catalog, p))[:3]
    assert count_violations(catalog, p, ok) == 0
    both = int(np.flatnonzero(catalog.flag("contains_peanut") & ~catalog.flag("is_vegan"))[0])
    assert count_violations(catalog, p, [int(ok[0]), both]) == 2        # one meal, two rules broken


def test_dinner_only_removes_breakfast_dough_and_batter_dishes_and_is_off_by_default(catalog):
    assert feasible_mask(catalog, UserProfile()).all()                       # the benchmark's profiles are unaffected
    ok = feasible_mask(catalog, UserProfile(dinner_only=True))
    removed = ~ok
    assert 0.02 < removed.mean() < 0.15, "a heuristic, not a purge: a few percent of the pool"
    names = [catalog.names[i].lower() for i in np.flatnonzero(removed)]
    assert any("dough" in n for n in names) and any("breakfast" in n for n in names)
    # real dinners the heuristic must leave alone
    for idx in np.flatnonzero(ok)[:2000]:
        assert not any(w in catalog.names[idx].lower() for w in ("dough", "batter", "frosting", "granola"))
    kept = {n.lower() for n in (catalog.names[i] for i in np.flatnonzero(ok))}
    assert any("crusted" in n for n in kept) and any("glazed" in n for n in kept)
    assert [r.name for r in violated_rules(catalog, UserProfile(dinner_only=True), int(np.flatnonzero(removed)[0]))] \
        == ["not_dinner"]


@pytest.mark.parametrize("group", ["meat","poultry","fish","shellfish","pork","egg","dairy","gluten","soy","sesame","peanut","tree_nut","alcohol"])
def test_food_group_exclusion_matches_recipe_flag(catalog, group):
    profile = UserProfile(excluded_food_groups=frozenset({group}))
    allowed = feasible_mask(catalog, profile)
    assert np.array_equal(allowed, ~catalog.flag(f"contains_{group}"))
    blocked = np.flatnonzero(catalog.flag(f"contains_{group}"))
    if len(blocked):
        reasons = violated_rules(catalog, profile, int(blocked[0]))
        assert reasons[0].name == f"food_group:{group}"
        assert group in reasons[0].reason


def test_unknown_food_group_rejected():
    with pytest.raises(ValueError, match="unknown food group"):
        UserProfile(excluded_food_groups=frozenset({"red_meat"}))


def test_multiple_food_group_exclusions(catalog):
    profile = UserProfile(excluded_food_groups=frozenset({"meat", "poultry", "fish"}))
    expected = ~(catalog.flag("contains_meat") | catalog.flag("contains_poultry") | catalog.flag("contains_fish"))
    assert np.array_equal(feasible_mask(catalog, profile), expected)


def test_ingredient_violations_use_the_same_rule_names_as_recipes(store):
    table = store.all_ingredients()
    butter, bacon, peanut = (store.ingredient_by_name(n).ingredient_id for n in ("butter", "bacon", "peanut butter"))
    assert ingredient_violations(table.loc[butter], butter, UserProfile()) == []
    assert ingredient_violations(table.loc[butter], butter, UserProfile(diet=Diet.VEGAN)) == ["diet:vegan"]
    assert ingredient_violations(table.loc[butter], butter, UserProfile(diet=Diet.VEGETARIAN)) == []
    assert ingredient_violations(table.loc[bacon], bacon, UserProfile(diet=Diet.PESCATARIAN)) == ["diet:pescatarian"]
    assert ingredient_violations(table.loc[bacon], bacon, UserProfile(avoid_pork=True)) == ["pork"]
    assert ingredient_violations(table.loc[peanut], peanut,
                                 UserProfile(allergens=frozenset({"peanut"}))) == ["allergen:peanut"]
    assert ingredient_violations(table.loc[butter], butter,
                                 UserProfile(excluded_food_groups=frozenset({"dairy"}))) == ["food_group:dairy"]
    assert ingredient_violations(table.loc[butter], butter,
                                 UserProfile(excluded_ingredient_ids=frozenset({butter}))) == ["excluded"]
