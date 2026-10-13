"""Tests for nlp.quantities.extract_quantity. Pure text tests - no dataset needed except the unit-consistency one."""
import pytest

from nlp.quantities import PHYSICAL_UNITS, UNIT_ALIASES, extract_quantity, parse_number_token


def q(text):
    quantity, rest = extract_quantity(text)
    return quantity, rest


@pytest.mark.parametrize("text, value, unit, rest", [
    ("2 cups chopped baby spinach", 2, "cup", "chopped baby spinach"),
    ("four eggs", 4, None, "eggs"),
    ("1 1/2 lb ground beef", 1.5, "lb", "ground beef"),
    ("1/2 cup milk", 0.5, "cup", "milk"),
    ("3 cloves garlic", 3, "clove", "garlic"),
    ("1 tbsp. olive oil", 1, "tbsp", "olive oil"),
    ("10 fl oz cream", 10, "fl_oz", "cream"),
    ("one and a half cups flour", 1.5, "cup", "flour"),
    ("a bag of rice", 1, "bag", "rice"),
    ("a handful of kale", 1, "handful", "kale"),
    ("a large onion", 1, None, "onion"),
])
def test_numbers_and_units(text, value, unit, rest):
    quantity, remainder = q(text)
    assert (quantity.value, quantity.unit, remainder) == (value, unit, rest)


@pytest.mark.parametrize("text, value", [
    ("half a cabbage", 0.5),
    ("half an onion", 0.5),
    ("a quarter of an onion", 0.25),
    ("three quarters of a cup of sugar", 0.75),
    ("a dozen eggs", 12),
    ("half a dozen eggs", 6),
    ("2 dozen eggs", 24),
])
def test_fraction_and_dozen_words(text, value):
    assert q(text)[0].value == pytest.approx(value)


def test_range_uses_lower_bound():
    quantity, rest = q("2-3 carrots")
    assert quantity.value == 2 and quantity.is_range and rest == "carrots"


@pytest.mark.parametrize("text, grams", [
    ("500g chicken breast", 500),
    ("1.5kg potatoes", 1500),
    ("1 lb mince", 453.59),
    ("about 200g feta", 200),
])
def test_explicit_mass_is_converted(text, grams):
    assert q(text)[0].explicit_grams == pytest.approx(grams, abs=0.01)


def test_pack_multiplier_and_container_words():
    quantity, rest = q("2 x 400g tins chopped tomatoes")
    assert quantity.explicit_grams == 800 and rest == "chopped tomatoes"


def test_bracketed_weight_belongs_to_the_container():
    quantity, rest = q("1 can (400g) chickpeas")
    assert quantity.value == 1 and quantity.unit == "can" and quantity.explicit_grams == 400
    assert rest == "chickpeas"


@pytest.mark.parametrize("text, vague, value", [
    ("some spinach", "some", None),
    ("a little milk", "a little", None),
    ("a few carrots", "a few", 3),
    ("a couple of onions", "a couple of", 2),
    ("leftover rice", "leftover", None),
])
def test_vague_words_are_reported_not_resolved(text, vague, value):
    quantity, _ = q(text)
    assert quantity.vague_word == vague and quantity.value == value


@pytest.mark.parametrize("text, value, unit", [
    ("eggs x4", 4, None),
    ("milk 1l", 1, "l"),
    ("spinach - 3", 3, None),
    ("6 pcs sausages", 6, "piece"),
])
def test_trailing_quantities(text, value, unit):
    quantity, _ = q(text)
    assert (quantity.value, quantity.unit) == (value, unit)


@pytest.mark.parametrize("text", ["paneer", "5 spice powder", "2% milk", "7 up"])
def test_no_quantity_when_digits_are_part_of_the_name(text):
    quantity, rest = q(text)
    assert quantity is None and rest == text


def test_size_words_are_extracted():
    quantity, rest = q("2 medium potatoes")
    assert quantity.size == "medium" and quantity.value == 2 and rest == "potatoes"
    quantity, rest = q("large onion")
    assert quantity.size == "large" and quantity.value is None and rest == "onion"


def test_parse_number_token():
    assert parse_number_token("2") == (2.0, False)
    assert parse_number_token("1.5") == (1.5, False)
    assert parse_number_token("3/4") == (0.75, False)
    assert parse_number_token("2-3") == (2.0, True)
    assert parse_number_token("abc") is None
    assert parse_number_token("1/0") is None


def test_physical_units_match_the_reference_csv(store):
    """The parser's unit vocabulary and reference/unit_conversion.csv must not drift apart."""
    csv_units = {d.unit for d in store.unit_definitions.values()}
    assert set(PHYSICAL_UNITS) - {"fl_oz"} <= csv_units | {"fl_oz"}
    for alias, unit in UNIT_ALIASES.items():
        if unit in PHYSICAL_UNITS and alias in store.unit_definitions:
            assert store.unit_definitions[alias].unit == unit
