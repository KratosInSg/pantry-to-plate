"""Tests for ``preference/history.py``: likes are derived by declared counting rules, and the similarity score is a
proper cosine.

The counting rules use hand-made dishes (ingredient ids are arbitrary small numbers), so each threshold is visible in
the test. The similarity score runs on the real catalogue.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import UserProfile
from preference.history import (LIKE_MIN_RATING, HistoryConfig, NearestConfig, RatedDish, as_profile_fields,
                                base_rates, derive_likes, history_similarity, nearest_dish_scores)
from preference.scorer import score_recipes


def _dish(*ingredients: int, cuisines: tuple[str, ...] = (), rating: int = 5) -> RatedDish:
    return RatedDish(frozenset(ingredients), frozenset(cuisines), rating)


# A reference pool of 20 dishes: ingredient 1 is in all of them, 2 in two, 3 in four; "italian" on two.
POOL = ([_dish(1, 2, cuisines=("italian",))] * 2 + [_dish(1, 3)] * 4 + [_dish(1)] * 14)
RATES = base_rates(POOL)


def test_base_rates_are_shares_of_the_pool():
    assert RATES.n_dishes == 20
    assert RATES.ingredient == {1: pytest.approx(1.0), 2: pytest.approx(0.1), 3: pytest.approx(0.2)}
    assert RATES.cuisine == {"italian": pytest.approx(0.1)}
    assert base_rates([]).n_dishes == 0


def test_a_like_needs_support_and_lift():
    # 10 liked dishes: 2 in half of them (lift 5), 1 in all of them (lift 1: everyone has it), 3 in one (support 10 %)
    history = [_dish(1, 2)] * 5 + [_dish(1)] * 4 + [_dish(1, 3)]
    likes = derive_likes(history, RATES)
    assert likes.liked_ingredient_ids == {2}
    [ev] = likes.evidence
    assert (ev.kind, ev.key) == ("ingredient", 2)
    assert ev.support == pytest.approx(0.5) and ev.base_rate == pytest.approx(0.1) and ev.lift == pytest.approx(5.0)
    assert likes.n_liked_dishes == 10


def test_low_ratings_staples_and_unknown_ingredients_never_become_likes():
    history = [_dish(2, 7, 9)] * 10 + [_dish(3, rating=LIKE_MIN_RATING - 1)] * 10
    likes = derive_likes(history, RATES, ignore_ids={2})
    assert likes.liked_ingredient_ids == frozenset()      # 2 is a staple; 7 and 9 have no base rate; 3 rated low
    assert likes.n_liked_dishes == 10


def test_too_short_a_history_derives_nothing():
    likes = derive_likes([_dish(2)] * 5, RATES, config=HistoryConfig(min_dishes=10))
    assert likes.liked_ingredient_ids == frozenset() and likes.evidence == () and likes.n_liked_dishes == 5


def test_cuisines_must_be_in_the_catalogue_vocabulary():
    history = [_dish(1, cuisines=("italian", "martian"))] * 10
    rates = base_rates(POOL + [_dish(1, cuisines=("martian",))])
    assert derive_likes(history, rates, cuisine_vocabulary={"italian"}).liked_cuisines == {"italian"}
    assert derive_likes(history, rates, cuisine_vocabulary=None).liked_cuisines == {"italian", "martian"}


def test_the_strongest_likes_are_kept_and_the_order_is_deterministic():
    pool = [_dish(i) for i in range(10, 20)] * 2 + [_dish(1)] * 80          # every 10..19 has base rate 2 %
    history = [_dish(*range(10, 20))] * 10
    likes = derive_likes(history, base_rates(pool), config=HistoryConfig(max_liked_ingredients=3))
    assert likes.liked_ingredient_ids == {10, 11, 12}                       # all tie on support and lift: id order
    assert [e.key for e in likes.evidence] == [10, 11, 12]


def test_derived_likes_plug_into_the_existing_scorer(catalog, store):
    garlic = store.ingredient_by_name("garlic").ingredient_id
    likes = derive_likes([_dish(garlic)] * 10, base_rates([_dish(garlic)] + [_dish(1)] * 9))
    profile = UserProfile(**as_profile_fields(likes))
    assert profile.liked_ingredient_ids == {garlic}
    with_likes, without = score_recipes(catalog, profile), score_recipes(catalog, UserProfile())
    uses = catalog.recipes_using(garlic)
    assert (with_likes[uses] > without[uses]).all()


# ------------------------------------------------------------------------------------------------ similarity
def test_history_similarity_is_a_cosine_in_zero_one(catalog, ctx):
    idx = 500
    ids = frozenset(int(i) for i in catalog.ingredients(idx)[0] if int(i) not in ctx.ignore_ids)
    scores = history_similarity(catalog, [RatedDish(ids, frozenset(), 5)], ctx.ignore_ids)
    assert scores.shape == (catalog.n,) and scores.dtype == np.float32
    assert scores.min() >= 0.0 and scores.max() <= 1.0 + 1e-6
    assert scores[idx] == pytest.approx(1.0, abs=1e-5)                      # the same ingredients: cosine 1
    assert scores[idx] == scores.max()


def test_history_similarity_ignores_low_ratings_and_needs_known_ingredients(catalog, ctx):
    ids = frozenset(int(i) for i in catalog.ingredients(500)[0])
    assert not history_similarity(catalog, [RatedDish(ids, frozenset(), 2)], ctx.ignore_ids).any()
    assert not history_similarity(catalog, [], ctx.ignore_ids).any()
    staples_only = RatedDish(frozenset(list(ctx.ignore_ids)[:3]), frozenset(), 5)
    assert not history_similarity(catalog, [staples_only], ctx.ignore_ids).any()


# ------------------------------------------------------------------------------------------------ nearest dishes
def _as_dish(catalog, idx, ignore, rating=5):
    ids = frozenset(int(i) for i in catalog.ingredients(idx)[0] if int(i) not in ignore)
    return RatedDish(ids, frozenset(), rating, frozenset(catalog.tags[idx]))


def test_nearest_dishes_puts_a_recipe_identical_to_a_liked_dish_at_the_top(catalog, ctx):
    scores = nearest_dish_scores(catalog, [_as_dish(catalog, 500, ctx.ignore_ids)], ctx.ignore_ids)
    assert scores.shape == (catalog.n,) and scores.dtype == np.float32
    assert 0.0 < scores.min() and scores.max() <= 1.0
    assert scores[500] == scores.max()


def test_nearest_dishes_keeps_two_different_tastes_apart(catalog, ctx):
    # k = 1: each recipe is judged by its single closest liked dish, so both liked dishes reach the very top, however
    # different they are from each other (an average of the two would sit between them). "Top 0.1 %", not "the
    # maximum": recipes sharing a dish's exact tag set tie with it, and tied ranks are averaged.
    history = [_as_dish(catalog, 500, ctx.ignore_ids), _as_dish(catalog, 9000, ctx.ignore_ids)]
    scores = nearest_dish_scores(catalog, history, ctx.ignore_ids, NearestConfig(k=1))
    assert min(scores[500], scores[9000]) >= np.quantile(scores, 0.999)


def test_nearest_dishes_uses_whichever_evidence_exists(catalog, ctx):
    with_tags = _as_dish(catalog, 500, ctx.ignore_ids)
    tags_only = RatedDish(frozenset(), frozenset(), 5, with_tags.tags)
    ingredients_only = RatedDish(with_tags.ingredient_ids, frozenset(), 5)
    by_tags = nearest_dish_scores(catalog, [tags_only], ctx.ignore_ids)
    assert by_tags[500] == by_tags.max()
    # without tags, the ingredient part alone gives the score, exactly as with tag_weight = 0
    assert np.array_equal(nearest_dish_scores(catalog, [ingredients_only], ctx.ignore_ids),
                          nearest_dish_scores(catalog, [with_tags], ctx.ignore_ids, NearestConfig(tag_weight=0.0)))


def test_nearest_dishes_needs_liked_known_evidence(catalog, ctx):
    assert not nearest_dish_scores(catalog, [], ctx.ignore_ids).any()
    assert not nearest_dish_scores(catalog, [_as_dish(catalog, 500, ctx.ignore_ids, rating=2)], ctx.ignore_ids).any()
    unknown = RatedDish(frozenset({10**7}), frozenset(), 5, frozenset({"not-a-tag"}))
    assert not nearest_dish_scores(catalog, [unknown], ctx.ignore_ids).any()


def test_nearest_rated_names_the_closest_liked_dishes_first(catalog, ctx):
    from preference.history import nearest_rated
    history = [_as_dish(catalog, 9000, ctx.ignore_ids), _as_dish(catalog, 500, ctx.ignore_ids),
               _as_dish(catalog, 500, ctx.ignore_ids, rating=2)]                  # a low rating is never named
    closest = nearest_rated(catalog, history, 500, ctx.ignore_ids)
    assert closest[0][0] == 1 and closest[0][1] == pytest.approx(1.0, abs=1e-6)   # itself: both cosines are 1
    assert all(pos != 2 for pos, _ in closest) and len(closest) <= 2
    assert [s for _, s in closest] == sorted((s for _, s in closest), reverse=True)
    assert nearest_rated(catalog, [], 500, ctx.ignore_ids) == ()
