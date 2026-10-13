"""Tests for ``optimizer/candidates.py``: the shortlist keeps the promising recipes and never drops the urgent options."""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import PantryItem, UserProfile
from optimizer.candidates import ShortlistConfig, nutrition_fit, pantry_coverage, shortlist, urgency_weight


class FakeCatalog:
    """The subset of ``RecipeCatalog`` the shortlist reads: n, flat, kcal, cuisine, recipes_using."""

    def __init__(self, recipes: list[dict[int, float]], kcal=None, cuisine=None) -> None:
        self._recipes = recipes
        self.n = len(recipes)
        owner, ids, grams = [], [], []
        for i, r in enumerate(recipes):
            for iid, g in r.items():
                owner.append(i), ids.append(iid), grams.append(g)
        self.flat = (np.array(owner, np.int32), np.array(ids, np.int32), np.array(grams, np.float32))
        self.kcal = np.array(kcal if kcal is not None else [600.0] * self.n, np.float32)   # = default dinner target
        self.cuisine = cuisine or [None] * self.n

    def recipes_using(self, iid: int) -> np.ndarray:
        return np.array([i for i, r in enumerate(self._recipes) if iid in r], dtype=np.int32)


def _item(iid, grams=100.0, last_use_day=None, known=False, conf=1.0) -> PantryItem:
    return PantryItem(ingredient_id=iid, grams=grams, last_use_day=last_use_day, expiry_known=known,
                      expiry_confidence=conf)


# ------------------------------------------------------------------------------------------------ urgency weight
def test_urgency_weight_scale():
    assert urgency_weight(_item(1)) == 1.0                                          # no deadline
    assert urgency_weight(_item(1, last_use_day=0, known=True)) == pytest.approx(3.0)   # known, today
    assert urgency_weight(_item(1, last_use_day=0, conf=0.5)) == pytest.approx(2.0)     # a guess is worth chasing less
    assert urgency_weight(_item(1, last_use_day=1, known=True)) == pytest.approx(2.5)
    assert urgency_weight(_item(1, last_use_day=6, known=True)) == 1.0               # far away


# ----------------------------------------------------------------------------------------------- pantry coverage
def test_coverage_is_the_share_of_mass_the_pantry_supplies():
    cat = FakeCatalog([{1: 100.0, 2: 100.0}, {3: 200.0}])
    cov = pantry_coverage(cat, [_item(1, 100)])
    assert cov[0] == pytest.approx(0.5) and cov[1] == 0.0


def test_coverage_is_capped_by_available_stock():
    cat = FakeCatalog([{1: 100.0}])
    assert pantry_coverage(cat, [_item(1, 40)])[0] == pytest.approx(0.4)
    assert pantry_coverage(cat, [_item(1, 4000)])[0] == pytest.approx(1.0)


def test_urgent_stock_counts_more_than_ordinary_stock():
    # two recipes, each half-covered by the pantry, but only recipe 0's covered half is about to expire
    cat = FakeCatalog([{1: 100.0, 9: 100.0}, {2: 100.0, 9: 100.0}])
    cov = pantry_coverage(cat, [_item(1, 100, last_use_day=0, known=True), _item(2, 100)])
    assert cov[0] > cov[1]


def test_ignored_ingredients_do_not_inflate_coverage():
    salt = 9
    cat = FakeCatalog([{1: 100.0, salt: 100.0}])
    assert pantry_coverage(cat, [_item(1, 100)], ignore_ids={salt})[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------------------------- nutrition fit
def test_nutrition_fit_peaks_at_the_target():
    cat = FakeCatalog([{1: 1.0}] * 4, kcal=[600, 300, 1200, 2400])
    fit = nutrition_fit(cat, UserProfile())
    assert fit[0] == pytest.approx(1.0) and fit[1] == pytest.approx(0.5)
    assert fit[2] == pytest.approx(0.0) and fit[3] == 0.0


# --------------------------------------------------------------------------------------------------- shortlist
def test_small_feasible_set_is_returned_whole():
    cat = FakeCatalog([{1: 10.0}] * 5)
    feasible = np.array([True, False, True, True, False])
    out = shortlist(cat, UserProfile(), [], feasible, np.full(5, 0.5, np.float32),
                    config=ShortlistConfig(size=10))
    assert out.tolist() == [0, 2, 3]


def test_shortlist_takes_the_best_and_never_an_infeasible_recipe():
    cat = FakeCatalog([{10: 500.0}] * 6)
    pref = np.array([1.0, 0.9, 0.8, 0.2, 0.1, 0.0], np.float32)
    feasible = np.array([False, True, True, True, True, True])        # the best-scoring recipe is not allowed
    out = shortlist(cat, UserProfile(), [], feasible, pref, config=ShortlistConfig(size=2))
    assert out.tolist() == [1, 2]


def test_urgent_ingredient_always_has_options_even_if_they_rank_low():
    recipes = [{10: 500.0}] * 6 + [{1: 50.0, 11: 450.0}]          # recipe 6 is the only user of ingredient 1
    cat = FakeCatalog(recipes)
    pref = np.array([1.0, 0.9, 0.8, 0.1, 0.1, 0.1, 0.0], np.float32)
    pantry = [_item(1, 50, last_use_day=0, known=True)]
    cfg = ShortlistConfig(size=3, per_urgent_ingredient=1)
    out = shortlist(cat, UserProfile(), pantry, np.ones(7, bool), pref, config=cfg)
    assert out.tolist() == [0, 1, 2, 6]


def test_no_cuisine_floods_the_shortlist():
    cat = FakeCatalog([{10: 500.0}] * 8, cuisine=["italian"] * 4 + ["thai"] * 4)
    pref = np.array([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3], np.float32)
    cfg = ShortlistConfig(size=4, max_cuisine_share=0.5)           # at most 2 per cuisine
    out = shortlist(cat, UserProfile(), [], np.ones(8, bool), pref, config=cfg)
    assert out.tolist() == [0, 1, 4, 5]
