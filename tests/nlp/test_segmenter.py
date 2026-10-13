"""Tests for nlp.segmenter. The tricky cases are the connectors that live *inside* names and quantities."""
from nlp.segmenter import normalise_input, split_items

PROTECTED = ["salt and pepper", "half and half", "macaroni and cheese", "salt and black pepper"]


def test_basic_list_with_lead_in():
    assert split_items("I have half a cabbage, paneer, four eggs and spinach getting old") == [
        "half a cabbage", "paneer", "four eggs", "spinach getting old"]


def test_connectors_inside_known_names_are_protected():
    assert split_items("salt and pepper, half and half & 2 limes", PROTECTED) == [
        "salt and pepper", "half and half", "2 limes"]


def test_longest_protected_phrase_wins():
    assert split_items("salt and black pepper and rice", PROTECTED) == ["salt and black pepper", "rice"]


def test_and_a_half_is_a_quantity_not_two_items():
    assert split_items("1 and a half cups of milk and 3 eggs") == ["1 1/2 cups of milk", "3 eggs"]
    assert split_items("two and a half pounds of potatoes") == ["2 1/2 pounds of potatoes"]


def test_numbers_are_not_split():
    assert split_items("1,000 g flour and sugar") == ["1,000 g flour", "sugar"]
    assert split_items("1.5 kg potatoes; 2.5 l milk") == ["1.5 kg potatoes", "2.5 l milk"]


def test_brackets_stay_whole():
    assert split_items("spinach (going bad, a bit slimy), milk") == ["spinach (going bad, a bit slimy)", "milk"]


def test_bullets_newlines_and_fridge_prefix():
    text = "In my fridge: milk\n- 2 eggs\n* 1 lb ground beef"
    assert split_items(text) == ["milk", "2 eggs", "1 lb ground beef"]


def test_also_and_plus_are_separators():
    assert split_items("chicken, rice and also some broccoli plus eggs") == ["chicken", "rice", "some broccoli", "eggs"]


def test_empty_and_filler_input():
    assert split_items("") == []
    assert split_items("  ,  and  ") == []


def test_normalise_input_handles_unicode_fractions_and_case():
    assert normalise_input("½ Cup Milk") == "1/2 cup milk"
    assert normalise_input("1½ cups flour") == "1 1/2 cups flour"
    assert normalise_input("It’s  FRESH") == "it's fresh"
