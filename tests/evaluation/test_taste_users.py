"""Tests for ``evaluation/taste_users.py``: the real-taste user set is built by stated rules, split by date, and frozen.

Building uses tiny hand-made MealRec-shaped tables (so each rule is visible) mapped with the real dataset; the last
test checks the frozen set in ``data/evaluation/taste_v1`` when it is present.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from evaluation.taste_users import (DEFAULT_TASTE_DIR, HISTORY_DISHES, MIN_HELDOUT_LINKED, N_USERS, TASTE_VERSION,
                                    TasteRating, TasteRecipe, TasteSet, TasteUser, build_recipes, catalogue_names,
                                    freeze_taste_set, linked_heldout, load_taste_recipes, load_taste_users,
                                    map_ingredient_texts, rated_dinners, rated_dishes, select_users, split_user,
                                    split_users)
from domain.models import UserProfile
from nlp.pantry_parser import PantryParser


def test_ingredient_text_maps_whole_names_first_then_parses(store, resolver):
    m = map_ingredient_texts(["cream cheese", "half-and-half cream", "chopped fresh parsley", "qzxqzx"], resolver,
                             PantryParser(store=store, resolver=resolver))
    name = lambda ids: [store.ingredient(i).canonical_name for i in ids]       # noqa: E731
    assert name(m["cream cheese"]) == ["cream cheese"]                         # not split into cream + cheese
    assert name(m["half-and-half cream"]) == ["half and half"]
    assert name(m["chopped fresh parsley"]) == ["parsley"]                     # preparation words dropped
    assert m["qzxqzx"] == ()


def test_catalogue_names_link_only_unambiguous_names(catalog):
    names = catalogue_names(catalog)
    assert names["chicken breasts lombardi"] == 49                            # exactly one recipe has this name
    assert names["cheesy chicken noodle casserole"] is None                   # several do: not linked


def test_build_recipes_keeps_main_dishes_and_maps_tags_and_names(store, catalog):
    raw = pd.DataFrame({
        "recipe_id": [1, 2, 3],
        "recipe_name": ["Chicken Breasts Lombardi", "Cheesy Chicken Noodle Casserole", "Chocolate Cake"],
        "category": ["main-dish", "main-dish", "dessert"],
        "ingredients": ["chicken breast^cream cheese^salt to taste", "egg noodles^cheddar cheese", "sugar"],
        "tags": ["italian;easy;main-dish", "north-american;martian", "desserts"]})
    recipes, stats = build_recipes(raw, store, catalog)
    assert recipes[0].tags == ["easy", "italian", "main-dish"] and recipes[1].tags == ["north-american"]
    assert [r.recipe_id for r in recipes] == [1, 2]                           # the dessert is not a dinner
    first, second = recipes
    assert first.catalogue_recipe_id == 49 and second.catalogue_recipe_id is None
    assert first.cuisines == ["italian"] and second.cuisines == ["north-american"]   # "easy"/"martian" are not cuisines
    assert store.ingredient_by_name("cream cheese").ingredient_id in first.ingredient_ids
    assert stats["n_main_dishes"] == 2 and stats["main_dishes_linked_to_catalogue"] == 1
    assert stats["main_dishes_with_ambiguous_catalogue_name"] == 1


def _ratings(user_id: int, recipe_ids: list[int], start_day: int = 1) -> pd.DataFrame:
    return pd.DataFrame({"user_id": user_id, "recipe_id": recipe_ids, "rating": 5,
                         "dateLastModified": [f"2010-01-{start_day + k:02d}T10:00:00\n" for k in range(len(recipe_ids))]})


def _recipes(n: int, linked_from: int) -> list[TasteRecipe]:
    """``n`` dinners; those with id >= ``linked_from`` exist in our catalogue (as catalogue id 1000 + id)."""
    return [TasteRecipe(recipe_id=i, name=f"dish {i}", ingredient_ids=[i],
                        catalogue_recipe_id=1000 + i if i >= linked_from else None) for i in range(n)]


def test_the_split_is_by_date_earliest_first():
    rows = _ratings(7, [5, 3, 9]).assign(date=lambda d: pd.to_datetime(d.dateLastModified.str.strip()))
    history, heldout = split_user(rows.iloc[[2, 0, 1]].sort_values("date"), history_dishes=2)
    assert [r.recipe_id for r in history] == [5, 3] and [r.recipe_id for r in heldout] == [9]


def test_select_users_needs_enough_dinners_and_checkable_later_ones():
    recipes = _recipes(30, linked_from=20)
    raw = pd.concat([_ratings(1, list(range(25))),                            # 25 dinners, 5 later, all linked
                     _ratings(2, list(range(5, 30)), start_day=2),            # qualifies too
                     _ratings(3, list(range(12))),                            # too few dinners
                     _ratings(4, list(range(25))[::-1])])                     # later dinners are unlinked ids 4..0
    users, stats = select_users(raw, recipes, n_users=2, min_main_ratings=25, history_dishes=20, min_heldout_linked=3)
    assert [u.user_id for u in users] == [1, 2]
    assert stats == {"users_with_enough_main_dishes": 3, "users_qualifying": 2}
    assert len(users[0].history) == 20 and [r.recipe_id for r in users[0].heldout] == [20, 21, 22, 23, 24]
    with pytest.raises(ValueError, match="only 2 users qualify"):
        select_users(raw, recipes, n_users=3, min_main_ratings=25, history_dishes=20, min_heldout_linked=3)
    with pytest.raises(ValueError, match="must leave held-out"):
        select_users(raw, recipes, n_users=1, min_main_ratings=20, history_dishes=20)


def test_held_out_dinners_already_linked_from_the_history_do_not_count():
    recipes = {r.recipe_id: r for r in _recipes(4, linked_from=0)}
    recipes[3] = recipes[3].model_copy(update={"catalogue_recipe_id": 1000})     # same catalogue recipe as dish 0
    user = TasteUser(user_id=1, history=[TasteRating(recipe_id=0, rating=5, date="2010")],
                     heldout=[TasteRating(recipe_id=i, rating=5, date="2011") for i in (1, 2, 3)])
    assert linked_heldout(user, recipes) == {1001, 1002}


def test_user_split_is_deterministic_and_disjoint():
    users = [TasteUser(user_id=i, history=[], heldout=[]) for i in range(10)]
    a, b = split_users(users), split_users(users)
    assert a == b and len(a["validation"]) == len(a["test"]) == 5
    assert not set(a["validation"]) & set(a["test"])


def test_freeze_and_load_round_trip_and_refuse_tampering(tmp_path):
    recipes = _recipes(3, linked_from=0)
    users = [TasteUser(user_id=i, history=[TasteRating(recipe_id=0, rating=5, date="2010")],
                       heldout=[TasteRating(recipe_id=1, rating=4, date="2011")]) for i in (1, 2)]
    taste = TasteSet(recipes, users, {"validation": [1], "test": [2]}, {"n_main_dishes": 3})
    frozen = freeze_taste_set(taste, tmp_path)
    assert json.loads(frozen.read_text(encoding="utf-8"))["stats"] == {"n_main_dishes": 3}
    assert [u.user_id for u in load_taste_users("validation", tmp_path)] == [1]
    assert load_taste_recipes(tmp_path)[1].catalogue_recipe_id == 1001
    assert rated_dishes(users[0].history, load_taste_recipes(tmp_path))[0].ingredient_ids == {0}
    with pytest.raises(FileExistsError):
        freeze_taste_set(taste, tmp_path)
    with pytest.raises(ValueError):
        load_taste_users("train", tmp_path)
    users_file = tmp_path / f"users_{TASTE_VERSION}.jsonl"
    users_file.write_text(users_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="has been modified"):
        load_taste_users("test", tmp_path)


@pytest.mark.skipif(not (DEFAULT_TASTE_DIR / "FROZEN.json").exists(), reason="frozen taste set not built here")
def test_the_frozen_taste_set():
    recipes = load_taste_recipes()
    val, test = load_taste_users("validation"), load_taste_users("test")
    assert len(val) + len(test) == N_USERS and abs(len(val) - len(test)) <= 1
    assert not {u.user_id for u in val} & {u.user_id for u in test}
    assert sum(bool(r.tags) for r in recipes.values()) > 0.95 * len(recipes)      # v2: dinners carry their tags
    for user in val + test:
        assert len(user.history) == HISTORY_DISHES and user.heldout
        assert max(r.date for r in user.history) <= min(r.date for r in user.heldout)   # past predicts future
        assert len(linked_heldout(user, recipes)) >= MIN_HELDOUT_LINKED


@pytest.mark.skipif(not all((DEFAULT_TASTE_DIR.parent / v / "FROZEN.json").exists() for v in ("taste_v1", "taste_v2")),
                    reason="both frozen taste sets are needed")
def test_v2_has_the_same_users_and_dinners_as_v1_plus_tags():
    v1, v2 = DEFAULT_TASTE_DIR.parent / "taste_v1", DEFAULT_TASTE_DIR.parent / "taste_v2"
    for split in ("validation", "test"):
        assert load_taste_users(split, v1) == load_taste_users(split, v2)
    r1, r2 = load_taste_recipes(v1), load_taste_recipes(v2)
    assert r1.keys() == r2.keys()
    assert all(r1[k] == r2[k].model_copy(update={"tags": []}) for k in r1)
    assert sum(bool(r.tags) for r in r2.values()) > 0.95 * len(r2)


def test_rated_dinners_are_what_a_profile_carries():
    recipes = {r.recipe_id: r for r in _recipes(3, linked_from=1)}
    ratings = [TasteRating(recipe_id=0, rating=5, date="2010"), TasteRating(recipe_id=2, rating=4, date="2011")]
    dinners = rated_dinners(ratings, recipes)
    assert [(d.recipe_id, d.rating, d.name) for d in dinners] == [(None, 5, "dish 0"), (1002, 4, "dish 2")]
    assert dinners[1].ingredient_ids == {2}
    assert UserProfile(rated_dinners=dinners).rated_dinners == dinners
