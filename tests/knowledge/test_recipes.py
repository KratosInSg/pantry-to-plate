"""Tests for ``knowledge/recipes.py`` (RecipeCatalog) against the real ``data/canonical`` build."""
from __future__ import annotations

import numpy as np
import pytest

from knowledge.recipes import FLAG_COLUMNS, RecipeInfo


def test_catalog_is_sorted_and_arrays_are_aligned(catalog):
    n = catalog.n
    assert n > 10_000                                                    # the dinner pool (54k at the time of writing)
    assert np.all(np.diff(catalog.recipe_ids) > 0)                       # strictly ascending => row index is stable
    for arr in (catalog.minutes, catalog.kcal, catalog.protein_g, catalog.fat_g, catalog.carbohydrate_g,
                catalog.rating_mean, catalog.n_ratings):
        assert len(arr) == n
    assert len(catalog.cuisine) == len(catalog.tags) == len(catalog.names) == n


def test_index_round_trip_and_unknown_id(catalog):
    for idx in (0, 1234, catalog.n - 1):
        assert catalog.index_of(catalog.recipe_id_of(idx)) == idx
    with pytest.raises(KeyError):
        catalog.index_of(-1)


def test_every_documented_flag_is_available(catalog):
    for name in FLAG_COLUMNS:
        flag = catalog.flag(name)
        assert flag.dtype == bool and len(flag) == catalog.n
    with pytest.raises(KeyError):
        catalog.flag("contains_unobtainium")


def test_vegan_implies_vegetarian(catalog):
    assert not np.any(catalog.flag("is_vegan") & ~catalog.flag("is_vegetarian"))


def test_ingredients_are_parallel_and_unique(catalog):
    ids, grams = catalog.ingredients(0)
    assert len(ids) == len(grams) > 0
    assert len(set(ids.tolist())) == len(ids)                           # one row per ingredient per recipe
    assert np.all(grams >= 0)


def test_flat_arrays_agree_with_per_recipe_slices(catalog):
    owner, ids, grams = catalog.flat
    assert len(owner) == len(ids) == len(grams)
    for idx in (0, 777, catalog.n // 2):
        sel = owner == idx
        slice_ids, slice_grams = catalog.ingredients(idx)
        assert np.array_equal(ids[sel], slice_ids) and np.array_equal(grams[sel], slice_grams)


def test_inverted_index_matches_the_ingredient_lists(catalog):
    ids, _ = catalog.ingredients(500)
    target = int(ids[0])
    using = catalog.recipes_using(target)
    assert 500 in using
    for idx in using[:25]:
        assert target in catalog.ingredients(int(idx))[0]
    assert len(catalog.recipes_using(-12345)) == 0


def test_mask_using_any_is_the_union(catalog):
    ids, _ = catalog.ingredients(10)
    a, b = int(ids[0]), int(ids[1])
    mask = catalog.mask_using_any([a, b])
    expected = np.zeros(catalog.n, dtype=bool)
    expected[catalog.recipes_using(a)] = True
    expected[catalog.recipes_using(b)] = True
    assert np.array_equal(mask, expected)


def test_info_returns_display_fields(catalog):
    info = catalog.info(0)
    assert isinstance(info, RecipeInfo)
    assert info.recipe_id == catalog.recipe_id_of(0) and info.name == catalog.names[0]
    assert info.rating_mean is None or 0 <= info.rating_mean <= 5


def test_every_recipe_has_cooking_steps_of_the_stated_length(catalog):
    """Steps are display-only but a plan is not cookable without them; the build keeps them for every recipe."""
    import pandas as pd

    n_steps = pd.read_parquet(catalog.data_dir / "recipes" / "recipe.parquet",
                              columns=["recipe_id", "n_steps"]).set_index("recipe_id").n_steps
    for idx in (0, 500, catalog.n - 1):
        steps = catalog.steps(idx)
        assert steps and all(isinstance(s, str) and s for s in steps)
        assert len(steps) == int(n_steps.loc[catalog.recipe_id_of(idx)])


def test_steps_for_a_recipe_without_a_step_table_are_empty_not_an_error(tmp_path, catalog):
    """A data directory built before steps were kept still works; the UI simply has nothing to show."""
    import shutil

    from knowledge.recipes import RecipeCatalog

    (tmp_path / "recipes").mkdir()
    shutil.copy(catalog.data_dir / "recipes" / "recipe.parquet", tmp_path / "recipes" / "recipe.parquet")
    assert RecipeCatalog(tmp_path).steps(0) == ()
