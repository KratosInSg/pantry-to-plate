"""Tests for ``app/grocery.py``: the grocery box is the inventory replay, presented."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.grocery import UNKNOWN_GROUP, build_grocery_box
from app.models import MINOR_GROCERY_G
from domain.models import PantryItem
from optimizer.inventory import account_inventory


class FakeCatalog:
    def __init__(self, recipes):
        self._recipes = recipes

    def ingredients(self, idx):
        r = self._recipes[idx]
        return np.array(list(r), dtype=np.int32), np.array(list(r.values()), dtype=np.float32)


class FakeStore:
    GROUPS = {1: ("chicken", "meat"), 2: ("spinach", "vegetable"), 3: ("cumin", "herb_spice"), 4: ("rice", "")}

    def ingredient(self, iid):
        if iid not in self.GROUPS:
            return None
        name, group = self.GROUPS[iid]
        return SimpleNamespace(canonical_name=name, food_group=group)


def _report(recipes, pantry=()):
    return account_inventory(list(range(len(recipes))), list(pantry), FakeCatalog(recipes), last_use_day={})


def test_items_match_the_replay_exactly():
    rep = _report([{1: 200.0, 2: 50.0}, {2: 30.0, 3: 2.0}], [PantryItem(ingredient_id=2, grams=60)])
    box = build_grocery_box(rep, FakeStore())
    assert {i.ingredient_id: i.grams for i in box.items} == pytest.approx(rep.groceries_g)
    assert box.n_items == rep.n_grocery_items
    assert box.total_g == pytest.approx(rep.total_groceries_g)


def test_first_needed_day_and_weekday_name():
    rep = _report([{2: 10.0}, {1: 100.0}, {1: 100.0, 3: 1.0}])
    box = build_grocery_box(rep, FakeStore(), start_weekday=4)       # day 0 is a Friday
    by = {i.name: i for i in box.items}
    assert (by["spinach"].first_needed_day, by["spinach"].weekday) == (0, "Friday")
    assert (by["chicken"].first_needed_day, by["chicken"].weekday) == (1, "Saturday")
    assert (by["cumin"].first_needed_day, by["cumin"].weekday) == (2, "Sunday")
    assert [i.name for i in box.items][0] == "spinach"                # soonest first


def test_pinches_are_flagged_minor_but_still_listed():
    rep = _report([{1: 200.0, 3: MINOR_GROCERY_G - 0.5}])
    box = build_grocery_box(rep, FakeStore())
    assert {i.name: i.minor for i in box.items} == {"chicken": False, "cumin": True}
    assert box.n_items == 2


def test_grouping_is_by_food_group_with_a_default_for_unknown():
    rep = _report([{1: 100.0, 2: 100.0, 4: 100.0, 99: 10.0}])
    groups = build_grocery_box(rep, FakeStore()).by_group()
    assert list(groups) == sorted(groups)
    assert {i.name for i in groups["meat"]} == {"chicken"} and {i.name for i in groups["vegetable"]} == {"spinach"}
    assert {i.name for i in groups[UNKNOWN_GROUP]} == {"rice", "ingredient 99"}


def test_a_plan_that_needs_nothing_has_an_empty_box():
    rep = _report([{2: 10.0}], [PantryItem(ingredient_id=2, grams=50)])
    box = build_grocery_box(rep, FakeStore())
    assert box.items == () and box.n_items == 0 and box.total_g == 0 and box.by_group() == {}
