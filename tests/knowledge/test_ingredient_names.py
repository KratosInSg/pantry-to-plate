"""Tests for knowledge.ingredient_names.core_name - the normaliser shared by the build and the NLP layer."""
import pytest

from knowledge.ingredient_names import core_name


@pytest.mark.parametrize("raw, expected", [
    ("fresh ground black pepper", "black pepper"),     # prep/quality words are stripped, "ground" too (a spice)
    ("diced tomato", "tomato"),
    ("large eggs", "eggs"),
    ("garlic cloves", "garlic"),                       # "clove" after garlic is a unit, not the spice
    ("minced garlic clove", "garlic"),
    ("cloves", "cloves"),                              # the spice stays
    ("ground beef", "ground beef"),                    # "ground" is identity-changing for meat
    ("ground turkey", "ground turkey"),
    ("flmy", "flour"),                                 # Food.com lemmatiser corruption is repaired
    ("all-purpose flmy", "all-purpose flour"),
    ("olife oil", "olive oil"),
    ("dried basil", "dried basil"),                    # "dried" changes the food, so it is kept
])
def test_core_name(raw, expected):
    assert core_name(raw) == expected


def test_core_name_is_idempotent():
    for raw in ["fresh ground black pepper", "diced tomato", "ground beef", "flmy"]:
        once = core_name(raw)
        assert core_name(once) == once
