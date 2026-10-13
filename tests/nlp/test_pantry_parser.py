"""Integration tests for nlp.pantry_parser.PantryParser (segment -> urgency -> quantity -> resolve -> grams)."""
import pytest

from nlp import PantryParser
from nlp.schemas import GramsSource, MatchStatus, ParseResult, Urgency

DEMO = "half a cabbage, paneer, four eggs and spinach getting old"   # the sentence from the project proposal


def by_name(result, name):
    matches = [i for i in result.items if i.canonical_name == name]
    assert matches, f"{name!r} not parsed; got {[i.canonical_name for i in result.items]}"
    return matches[0]


def test_demo_sentence_from_the_proposal(parser, today):
    r = parser.parse(DEMO, today)
    assert [i.canonical_name for i in r.items] == ["cabbage", "paneer cheese", "egg", "spinach"]
    assert r.unparsed == []
    assert all(i.match_status is MatchStatus.MATCHED for i in r.items)

    spinach = by_name(r, "spinach")
    assert spinach.urgency is Urgency.SOON and spinach.days_left_hint == 3
    assert spinach.quantity_is_assumed and spinach.grams_source is GramsSource.ASSUMED_DEFAULT
    # nothing else carries urgency
    assert all(i.urgency is Urgency.NONE for i in r.items if i.canonical_name != "spinach")


def test_half_a_cabbage_and_four_eggs_use_dataset_weights(parser, store, today):
    r = parser.parse(DEMO, today)
    head = store.whole_item_weight(store.ingredient_by_name("cabbage").ingredient_id)
    assert by_name(r, "cabbage").grams == pytest.approx(0.5 * head.grams, abs=0.1)
    assert by_name(r, "cabbage").grams_source is GramsSource.ITEM_UNIT_WEIGHT
    egg = store.unit_weight(store.ingredient_by_name("egg").ingredient_id, "each", "large")
    assert by_name(r, "egg").grams == pytest.approx(4 * egg.grams, abs=0.1)   # "large" is the everyday egg


def test_explicit_mass_is_exact_and_trusted(parser, today):
    r = parser.parse("500g chicken breast, 1 lb ground beef, 1 can (400g) chickpeas, 2 x 400g tins chopped tomatoes", today)
    assert by_name(r, "chicken breast").grams == 500
    assert by_name(r, "ground beef").grams == pytest.approx(453.6, abs=0.1)
    assert by_name(r, "chickpea").grams == 400
    assert by_name(r, "tomato").grams == 800
    for i in r.items:
        assert i.grams_source is GramsSource.EXPLICIT_MASS and not i.quantity_is_assumed and i.confidence == 1.0


def test_volume_uses_ingredient_specific_weight(parser, store, today):
    r = parser.parse("2 cups flour", today)
    flour = store.ingredient_by_name("all-purpose flour").ingredient_id
    expected = 2 * store.unit_weight(flour, "cup").grams
    item = r.items[0]
    assert item.grams == pytest.approx(expected, abs=0.1) and item.grams_source is GramsSource.VOLUME_UNIT_WEIGHT


def test_assumptions_are_labelled_never_silent(parser, today):
    item = parser.parse("paneer", today).items[0]
    assert item.quantity_is_assumed and item.grams_source is GramsSource.ASSUMED_DEFAULT
    assert any("no quantity" in w for w in item.warnings)
    assert item.confidence < 1.0


def test_unknown_ingredient_is_kept_and_flagged(parser, today):
    r = parser.parse("dragonfruit kombucha scoby, 2 eggs", today)
    unknown = r.items[0]
    assert unknown.match_status is MatchStatus.UNKNOWN and unknown.ingredient_id is None
    assert any("unknown ingredient" in w for w in unknown.warnings)
    assert r.items[1].canonical_name == "egg"
    assert unknown in r.needs_attention and len(r.resolved_items) == 1


def test_bare_cue_attaches_to_previous_item(parser, today):
    r = parser.parse("eggs, they expire tomorrow", today)
    egg = by_name(r, "egg")
    assert egg.urgency is Urgency.URGENT and egg.days_left_hint == 1
    assert len(r.items) == 1 and r.unparsed == []


def test_cue_scope_both_and_all(parser, today):
    r = parser.parse("milk, eggs, spinach, they're all going bad", today)
    assert all(i.urgency is Urgency.URGENT for i in r.items)
    r = parser.parse("milk, eggs, spinach, both going bad", today)
    assert [i.urgency for i in r.items] == [Urgency.NONE, Urgency.URGENT, Urgency.URGENT]


def test_mouldy_food_carries_a_safety_warning(parser, today):
    item = parser.parse("cheddar cheese has gone mouldy", today).items[0]
    assert item.urgency is Urgency.URGENT
    assert any("unsafe" in w for w in item.warnings)


def test_salt_and_pepper_becomes_two_items(parser, today):
    r = parser.parse("salt and pepper", today)
    assert sorted(i.canonical_name for i in r.items) == ["black pepper", "salt"]


def test_state_modifiers_set_storage_hint(parser, today):
    item = parser.parse("2 cups frozen peas", today).items[0]
    assert "frozen" in item.modifiers and item.storage_hint == "freezer"
    item = parser.parse("some leftover rice", today).items[0]
    assert item.storage_hint == "refrigerator"


def test_prepositional_tail_is_not_part_of_the_name(parser, today):
    item = parser.parse("1 can tuna in olive oil", today).items[0]
    assert item.canonical_name == "tuna"


def test_empty_and_junk_input(parser, today):
    assert parser.parse("", today).items == []
    r = parser.parse("2 cups", today)
    assert r.items == [] and r.unparsed == ["2 cups"]


def test_result_is_json_serialisable(parser, today):
    r = parser.parse(DEMO, today)
    data = r.model_dump(mode="json")
    assert data["items"][0]["canonical_name"] == "cabbage"
    assert ParseResult.model_validate(data) == r


def test_llm_fallback_is_called_only_when_needed(store, resolver, today):
    calls = []

    class FakeLlm:
        def refine(self, text, result):
            calls.append(text)
            return result

    p = PantryParser(store=store, resolver=resolver, llm_fallback=FakeLlm())
    p.parse("2 eggs and 500g chicken breast", today)
    assert calls == []                                   # everything confident -> no LLM
    p.parse("2 eggs and dragonfruit kombucha scoby", today)
    assert len(calls) == 1                               # an unknown item triggers the fallback


def test_days_left_explicit_is_carried_to_the_item(parser, today):
    known = parser.parse("milk expires tomorrow", today).items[0]
    assert known.days_left_hint == 1 and known.days_left_explicit is True
    guess = parser.parse("spinach getting old", today).items[0]
    assert guess.days_left_hint == 3 and guess.days_left_explicit is False
    attached = parser.parse("eggs, they expire tomorrow", today).items[0]      # bare cue attached to previous item
    assert attached.days_left_explicit is True
