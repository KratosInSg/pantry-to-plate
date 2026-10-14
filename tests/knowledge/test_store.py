"""Tests for knowledge.store.KnowledgeStore against the real data/canonical build."""
import pytest

from knowledge.store import KnowledgeStore


def _id(store, name):
    info = store.ingredient_by_name(name)
    assert info is not None, f"ingredient {name!r} missing from dataset"
    return info.ingredient_id


def test_missing_dataset_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        KnowledgeStore(tmp_path / "nope")


def test_ingredient_lookup_and_flags(store):
    cheddar = store.ingredient_by_name("cheddar cheese")
    assert cheddar.food_group == "dairy"
    assert "dairy" in cheddar.allergens
    assert cheddar.is_vegetarian and not cheddar.is_vegan
    assert store.ingredient(cheddar.ingredient_id) == cheddar
    chicken = store.ingredient_by_name("chicken breast")
    assert not chicken.is_vegetarian


@pytest.mark.parametrize("name", ["egg", "mayonnaise", "egg noodle", "salmon", "shrimp", "chicken breast"])
def test_vegetarian_means_no_meat_no_fish_no_eggs(store, name):
    # project definition (CLAUDE.md): eggs are NOT vegetarian; dairy is
    info = store.ingredient_by_name(name)
    assert info is not None and not info.is_vegetarian and not info.is_vegan


@pytest.mark.parametrize("name", ["milk", "paneer cheese", "butter", "eggplant", "spinach"])
def test_dairy_and_plants_are_vegetarian(store, name):
    info = store.ingredient_by_name(name)
    assert info is not None and info.is_vegetarian                   # "eggplant" is not an egg


def test_unknown_ingredient_returns_none(store):
    assert store.ingredient(-1) is None
    assert store.ingredient_by_name("zzz not a food") is None
    assert store.nutrition_per_100g(-1) is None
    assert store.default_shelf_life(-1) is None


def test_assumed_available_staples(store):
    assert store.ingredient_by_name("salt").is_assumed_available
    assert not store.ingredient_by_name("chicken breast").is_assumed_available


def test_alias_lookup_is_exact_and_lowercase(store):
    assert store.lookup_alias("eggs") == (_id(store, "egg"),)
    assert store.lookup_alias("EGGS") == ()            # callers normalise; the store does not guess
    assert store.lookup_alias("definitely not an alias") == ()


def test_salt_and_pepper_is_a_deliberate_split(store):
    ids = store.lookup_alias("salt and pepper")
    assert set(ids) == {_id(store, "salt"), _id(store, "black pepper")}
    assert "salt and pepper" in store.connector_phrases


def test_unit_weight_prefers_generic_then_medium(store):
    onion = _id(store, "onion")
    medium = store.unit_weight(onion, "each")            # no size given -> medium (USDA reference)
    large = store.unit_weight(onion, "each", "large")
    small = store.unit_weight(onion, "each", "small")
    assert small.grams < medium.grams < large.grams
    assert store.unit_weight(onion, "no-such-unit") is None


def test_whole_item_weight(store):
    assert store.whole_item_weight(_id(store, "cabbage")).unit == "head"
    assert store.whole_item_weight(_id(store, "egg")).unit == "each"


def test_unit_definitions_cover_physical_units(store):
    d = store.unit_definitions
    assert d["tablespoons"].unit == "tbsp" and d["tablespoons"].kind == "volume"
    assert d["lbs"].unit == "lb" and d["lbs"].kind == "mass"
    assert d["cups"].to_base == pytest.approx(236.588)


def test_nutrition_per_100g_matches_usda(store):
    n = store.nutrition_per_100g(_id(store, "egg"))
    assert n["energy_kcal"] == pytest.approx(143, abs=1)       # USDA "Egg, whole, raw, fresh"
    assert n["protein_g"] == pytest.approx(12.6, abs=0.3)


def test_default_shelf_life(store):
    spinach = store.default_shelf_life(_id(store, "spinach"))
    assert spinach.storage == "refrigerator"
    assert 1 <= spinach.min_days <= spinach.max_days <= 14
    salt = store.default_shelf_life(_id(store, "salt"))
    assert salt.is_indefinite


def test_fuzzy_candidates_are_parallel_and_filtered(store):
    names, ids = store.fuzzy_candidates
    assert len(names) == len(ids) > 1000
    assert "spinach" in names
