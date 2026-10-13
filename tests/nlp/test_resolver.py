"""Tests for nlp.resolver.IngredientResolver against the real alias table."""
import pytest

from nlp.schemas import MatchStatus


def name_of(store, res):
    return store.ingredient(res.ingredient_ids[0]).canonical_name


@pytest.mark.parametrize("text, canonical, method", [
    ("spinach", "spinach", "exact"),
    ("eggs", "egg", "exact"),
    ("baby spinach", "spinach", None),                  # method may be exact (alias) or normalised
    ("all purpose flour", "all-purpose flour", None),   # hyphen-less spelling
    ("paneer", "paneer cheese", "exact"),
    ("scallions", "scallion", None),
    ("chicken breasts", "chicken breast", None),
    ("tomatoes", "tomato", None),
    ("kosher salt", "salt", None),
])
def test_known_names(store, resolver, text, canonical, method):
    res = resolver.resolve(text)
    assert res.status is MatchStatus.MATCHED
    assert name_of(store, res) == canonical
    if method:
        assert res.method == method


def test_modifier_words_are_dropped_only_when_safe(store, resolver):
    res = resolver.resolve("organic free range eggs")
    assert res.status is MatchStatus.MATCHED and name_of(store, res) == "egg"
    res = resolver.resolve("spinach leaves washed")
    assert res.status is MatchStatus.MATCHED and name_of(store, res) == "spinach"


def test_compound_names_never_degrade_to_their_head_noun(store, resolver):
    """'peanut butter' is not butter; an unknown 'kimchi paste' must not become 'tomato paste'."""
    pb = resolver.resolve("peanut butter")
    assert name_of(store, pb) == "peanut butter"
    kp = resolver.resolve("kimchi paste")
    assert kp.status is not MatchStatus.MATCHED or name_of(store, kp) not in {"paste", "tomato paste", "butter"}


@pytest.mark.parametrize("typo, canonical", [("spinich", "spinach"), ("brocoli", "broccoli"), ("cheddr cheese", "cheddar cheese")])
def test_typos_are_accepted_with_method_fuzzy(store, resolver, typo, canonical):
    res = resolver.resolve(typo)
    assert res.status is MatchStatus.MATCHED and res.method == "fuzzy"
    assert name_of(store, res) == canonical


def test_unknown_food_is_reported_not_guessed(resolver):
    res = resolver.resolve("dragonfruit kombucha scoby")
    assert res.status is MatchStatus.UNKNOWN and res.ingredient_ids == ()


def test_short_names_are_not_fuzzy_matched(resolver):
    res = resolver.resolve("xq")
    assert res.status is MatchStatus.UNKNOWN


def test_deliberate_split_returns_two_ids(store, resolver):
    res = resolver.resolve("salt and pepper")
    assert res.status is MatchStatus.MATCHED and len(res.ingredient_ids) == 2


def test_empty_input(resolver):
    assert resolver.resolve("").status is MatchStatus.UNKNOWN
    assert resolver.resolve("   ").status is MatchStatus.UNKNOWN
