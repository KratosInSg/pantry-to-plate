"""Tests for ``optimizer/inventory.py``: the single definition of used / bought / wasted.

A tiny fake catalogue is used on purpose - each test then states its numbers by hand, so a failure reads as a broken
rule, not as a changed dataset.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import PantryItem
from optimizer.inventory import account_inventory, deadlines_from_pantry


class FakeCatalog:
    """Just enough of ``RecipeCatalog`` for the replay: ``ingredients(idx)``."""

    def __init__(self, recipes: list[dict[int, float]]) -> None:
        self._recipes = recipes

    def ingredients(self, idx: int):
        r = self._recipes[idx]
        return np.array(list(r), dtype=np.int32), np.array(list(r.values()), dtype=np.float32)


def _stock(iid: int, grams: float, last_use_day: int | None = None) -> PantryItem:
    return PantryItem(ingredient_id=iid, grams=grams, last_use_day=last_use_day)


def test_pantry_is_used_first_then_the_rest_is_bought():
    cat = FakeCatalog([{1: 60.0}, {1: 60.0}])
    rep = account_inventory([0, 1], [_stock(1, 100)], cat, last_use_day={})
    assert rep.consumed_g == {1: pytest.approx(100)}
    assert rep.groceries_g == {1: pytest.approx(20)}
    assert rep.total_waste_g == 0 and rep.unused_g == {}
    assert rep.n_grocery_items == 1


def test_stock_that_expires_unused_is_waste():
    cat = FakeCatalog([{2: 10.0}, {2: 10.0}, {2: 10.0}])
    rep = account_inventory([0, 1, 2], [_stock(1, 100, last_use_day=1)], cat, last_use_day={1: 1})
    assert rep.waste_g == {1: pytest.approx(100)}
    assert rep.unused_g == {}
    assert 1 in rep.expiring_ids and rep.expiring_pantry_g == pytest.approx(100)


def test_stock_with_a_deadline_beyond_the_horizon_is_unused_not_waste():
    cat = FakeCatalog([{2: 10.0}, {2: 10.0}])
    rep = account_inventory([0, 1], [_stock(1, 100, last_use_day=5)], cat, last_use_day={1: 5})
    assert rep.total_waste_g == 0
    assert rep.unused_g == {1: pytest.approx(100)}
    assert not rep.expiring_ids


def test_demand_after_the_deadline_is_bought_and_reported():
    # day 0 cooks something else; on day 1 the dinner wants ingredient 1 but the stock expired after day 0
    cat = FakeCatalog([{2: 10.0}, {1: 50.0}])
    rep = account_inventory([0, 1], [_stock(1, 100, last_use_day=0)], cat, last_use_day={1: 0})
    assert rep.groceries_g[1] == pytest.approx(50)
    assert rep.expired_demand_g == {1: pytest.approx(50)}
    assert rep.consumed_g.get(1, 0) == 0
    assert rep.waste_g == {1: pytest.approx(100)}


def test_deadline_day_is_inclusive():
    cat = FakeCatalog([{2: 10.0}, {1: 50.0}])
    rep = account_inventory([0, 1], [_stock(1, 100, last_use_day=1)], cat, last_use_day={1: 1})
    assert rep.consumed_g == {1: pytest.approx(50)}          # day 1 == last_use_day: still usable
    assert rep.expired_demand_g == {}
    assert rep.waste_g == {1: pytest.approx(50)}             # the half nobody cooked spoils (deadline 1 < horizon 2)


def test_ignored_staples_never_count():
    salt = 99
    cat = FakeCatalog([{1: 50.0, salt: 5.0}])
    rep = account_inventory([0], [_stock(1, 50), _stock(salt, 500)], cat, last_use_day={}, ignore_ids={salt})
    assert salt not in rep.pantry_g and salt not in rep.groceries_g and salt not in rep.consumed_g
    assert rep.total_pantry_g == pytest.approx(50)


def test_duplicate_stocks_are_summed():
    cat = FakeCatalog([{1: 150.0}])
    rep = account_inventory([0], [_stock(1, 100), _stock(1, 60)], cat, last_use_day={})
    assert rep.consumed_g == {1: pytest.approx(150)} and rep.unused_g == {1: pytest.approx(10)}


def test_uses_by_day_records_where_stock_went():
    cat = FakeCatalog([{1: 30.0}, {2: 5.0}, {1: 30.0}])
    rep = account_inventory([0, 1, 2], [_stock(1, 100)], cat, last_use_day={})
    assert rep.uses_by_day == [{1: pytest.approx(30)}, {}, {1: pytest.approx(30)}]


def test_a_skipped_day_uses_nothing_but_still_counts_down_deadlines():
    cat = FakeCatalog([{1: 50.0}])
    # day 0 skipped, day 1 cooks with stock whose deadline was day 0 -> the stock is already expired
    rep = account_inventory([None, 0], [_stock(1, 100, last_use_day=0)], cat, last_use_day={1: 0})
    assert rep.uses_by_day == [{}, {}] and rep.groceries_by_day == [{}, {1: pytest.approx(50)}]
    assert rep.expired_demand_g == {1: pytest.approx(50)} and rep.waste_g == {1: pytest.approx(100)}


def test_groceries_by_day_records_where_the_shortfall_arises_and_sums_to_the_total():
    cat = FakeCatalog([{1: 60.0, 2: 10.0}, {1: 60.0}, {3: 5.0}])
    rep = account_inventory([0, 1, 2], [_stock(1, 100)], cat, last_use_day={})
    assert rep.groceries_by_day == [{2: pytest.approx(10)}, {1: pytest.approx(20)}, {3: pytest.approx(5)}]
    summed: dict[int, float] = {}
    for day in rep.groceries_by_day:
        for iid, g in day.items():
            summed[iid] = summed.get(iid, 0.0) + g
    assert summed == pytest.approx(rep.groceries_g)


def test_mass_balance():
    """Everything that entered the kitchen is accounted for: pantry = consumed + waste + unused."""
    cat = FakeCatalog([{1: 70.0, 2: 20.0}, {1: 40.0}, {3: 15.0}])
    pantry = [_stock(1, 90, last_use_day=1), _stock(2, 100), _stock(3, 10, last_use_day=0)]
    rep = account_inventory([0, 1, 2], pantry, cat, last_use_day=deadlines_from_pantry(pantry))
    assert rep.total_pantry_g == pytest.approx(rep.total_consumed_g + rep.total_waste_g + sum(rep.unused_g.values()))


def test_deadlines_from_pantry_earliest_wins_and_none_means_never():
    pantry = [_stock(1, 10, 4), _stock(1, 10, 2), _stock(2, 10, None), _stock(3, 10, None), _stock(3, 10, 5)]
    assert deadlines_from_pantry(pantry) == {1: 2, 2: None, 3: 5}
