"""Tests for ``preference/scorer.py``: the score moves in the documented directions and never filters."""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import UserProfile
from preference.scorer import DEFAULT_WEIGHTS, disliked_mask, popularity, score_recipes


@pytest.fixture(scope="module")
def some_ingredient(catalog) -> int:
    """An ingredient used by a modest number of recipes (so the effect is visible and not clipped)."""
    ids, _ = catalog.ingredients(500)
    for iid in ids:
        n = len(catalog.recipes_using(int(iid)))
        if 20 <= n <= 5000:
            return int(iid)
    raise AssertionError("no suitable ingredient found in recipe 500")


@pytest.fixture(scope="module")
def baseline(catalog) -> np.ndarray:
    return score_recipes(catalog, UserProfile())


def test_scores_are_in_unit_interval_and_float32(baseline):
    assert baseline.dtype == np.float32
    assert baseline.min() >= 0.0 and baseline.max() <= 1.0


def test_neutral_user_only_sees_the_small_popularity_term(baseline):
    # 0.5 +/- W_POPULAR: nothing the user said can move it further.
    assert baseline.min() >= 0.5 - DEFAULT_WEIGHTS.popularity - 1e-6
    assert baseline.max() <= 0.5 + DEFAULT_WEIGHTS.popularity + 1e-6


def test_unrated_recipes_are_neutral(catalog):
    pop = popularity(catalog)
    unrated = catalog.n_ratings == 0
    assert unrated.any()
    assert np.all(pop[unrated] == 0.5)
    assert pop.min() >= 0.0 and pop.max() <= 1.0


def test_disliked_ingredient_lowers_the_score_but_does_not_remove_the_recipe(catalog, baseline, some_ingredient):
    profile = UserProfile(disliked_ingredient_ids=frozenset({some_ingredient}))
    s = score_recipes(catalog, profile)
    using = catalog.recipes_using(some_ingredient)
    assert np.allclose(baseline[using] - s[using], DEFAULT_WEIGHTS.disliked_ingredient, atol=1e-5)
    assert np.all(s[using] > 0.0)                                       # still scoreable => still eligible
    not_using = np.ones(catalog.n, dtype=bool)
    not_using[using] = False
    assert np.array_equal(s[not_using], baseline[not_using])


def test_liked_ingredient_raises_the_score_with_saturation(catalog, baseline, some_ingredient):
    s_one = score_recipes(catalog, UserProfile(liked_ingredient_ids=frozenset({some_ingredient})))
    using = catalog.recipes_using(some_ingredient)
    # one hit earns half of the bonus (saturation is at two liked ingredients)
    assert np.allclose(s_one[using] - baseline[using], DEFAULT_WEIGHTS.liked_ingredient / 2, atol=1e-5)


def test_staples_can_be_ignored_for_likes(catalog, baseline, some_ingredient):
    profile = UserProfile(liked_ingredient_ids=frozenset({some_ingredient}))
    s = score_recipes(catalog, profile, ignore_for_likes=[some_ingredient])
    assert np.array_equal(s, baseline)


def test_cuisine_preferences_shift_scores(catalog, baseline):
    cuisines = [c for c in catalog.cuisine if c]
    assert cuisines, "dataset has no cuisine labels"
    target = max(set(cuisines), key=cuisines.count)
    in_cuisine = np.array([c == target for c in catalog.cuisine])
    liked = score_recipes(catalog, UserProfile(liked_cuisines=frozenset({target})))
    disliked = score_recipes(catalog, UserProfile(disliked_cuisines=frozenset({target})))
    assert np.all(liked[in_cuisine] >= baseline[in_cuisine])
    assert np.all(disliked[in_cuisine] <= baseline[in_cuisine])
    assert liked[in_cuisine].mean() > baseline[in_cuisine].mean() > disliked[in_cuisine].mean()
    assert np.array_equal(liked[~in_cuisine], baseline[~in_cuisine])


def test_disliked_mask_matches_dislikes(catalog, some_ingredient):
    mask = disliked_mask(catalog, UserProfile(disliked_ingredient_ids=frozenset({some_ingredient})))
    assert np.array_equal(np.flatnonzero(mask), np.sort(catalog.recipes_using(some_ingredient)))
    assert not disliked_mask(catalog, UserProfile()).any()
