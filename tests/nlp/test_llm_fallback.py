"""Tests for ``nlp/llm_fallback.py``: the model may normalise text, but only what the user's words support.

A scripted stub stands in for the LLM; the rules parser is the real one (so re-parsing, grams and labels are real).
"""
from __future__ import annotations

import pytest

from llm.client import LlmError
from nlp.llm_fallback import (WARNING, LlmPantryFallback, _numbers_in, extraction_schema, parser_with_llm,
                              unit_words_in)
from nlp.pantry_parser import PantryParser
from nlp.schemas import GramsSource, MatchStatus, Urgency


class StubLlm:
    """Returns a scripted answer (or raises) and records what it was asked."""

    def __init__(self, items=None, error: Exception | None = None, available: bool = True) -> None:
        self.items, self.error, self.available = items or [], error, available
        self.calls: list[tuple[list[dict], dict]] = []

    def complete_json(self, messages, schema):
        self.calls.append((messages, schema))
        if self.error:
            raise self.error
        return {"items": self.items}

    def is_available(self) -> bool:
        return self.available


def _item(name, quantity=None, unit="none"):
    return {"name": name, "has_quantity": quantity is not None, "quantity": quantity or 0, "unit": unit}


@pytest.fixture()
def rules(store, resolver) -> PantryParser:
    return PantryParser(store=store, resolver=resolver)


def _with_llm(rules, stub) -> PantryParser:
    return PantryParser(store=rules._store, resolver=rules._resolver,           # noqa: SLF001 - share the built index
                        llm_fallback=LlmPantryFallback(stub, rules))


def _unit_enum(source: str) -> list[str]:
    return extraction_schema(source)["properties"]["items"]["items"]["properties"]["unit"]["enum"]


def test_unit_enum_offers_only_the_unit_words_in_the_text():
    assert _unit_enum("two-ish pounds potatoes") == ["pounds", "none"]
    assert _unit_enum("3 cloves of garlic and 2 tbsp honey") == ["cloves", "tbsp", "none"]
    assert _unit_enum("some potatoes") == ["none"]
    assert unit_words_in("1.5kg flour, 2 TBSP oil") == ["kg", "tbsp"]


def test_no_problem_items_means_no_llm_call(rules):
    stub = StubLlm()
    result = _with_llm(rules, stub).parse("3 eggs, 2 onions")
    assert stub.calls == [] and len(result.items) == 2


def test_fragment_the_rules_could_not_read_is_fixed(rules):
    assert rules.parse("two-ish pounds potatoes").items[0].match_status is MatchStatus.UNKNOWN   # premise
    stub = StubLlm([_item("potatoes", 2, "pounds")])
    item = _with_llm(rules, stub).parse("two-ish pounds potatoes").items[0]
    assert item.match_status is MatchStatus.MATCHED and "potato" in item.canonical_name
    assert item.grams == pytest.approx(907.2, abs=1.0) and item.grams_source is GramsSource.EXPLICIT_MASS
    assert item.raw_text == "two-ish pounds potatoes"            # the user's words are preserved
    assert WARNING in item.warnings                              # and the UI can flag that a model re-read it


def test_the_model_is_only_shown_the_problem_fragments(rules):
    stub = StubLlm([_item("potatoes", 2, "pounds")])
    _with_llm(rules, stub).parse("3 eggs, two-ish pounds potatoes, 2 onions")
    sent = stub.calls[0][0][-1]["content"]
    assert "potatoes" in sent and "eggs" not in sent and "onions" not in sent


def test_good_items_are_untouched_and_order_is_kept(rules):
    text = "3 eggs, two-ish pounds potatoes, 2 onions"
    baseline = rules.parse(text)
    result = _with_llm(rules, StubLlm([_item("potatoes", 2, "pounds")])).parse(text)
    assert [i.raw_text for i in result.items] == [i.raw_text for i in baseline.items]
    assert result.items[0] == baseline.items[0] and result.items[2] == baseline.items[2]


def test_a_unit_that_is_not_in_the_text_drops_the_number_too(rules):
    """The live model once answered "pint" for "pounds": a number with an unconfirmed unit means nothing."""
    result = _with_llm(rules, StubLlm([_item("potatoes", 2, "pint")])).parse("two-ish pounds potatoes")
    item = result.items[0]
    assert item.match_status is MatchStatus.MATCHED and item.quantity_is_assumed
    assert item.quantity_value is None                           # neither "2" nor "pint" survived


def test_ignoring_a_unit_word_that_is_in_the_text_drops_the_number(rules):
    result = _with_llm(rules, StubLlm([_item("potatoes", 2, "none")])).parse("two-ish pounds potatoes")
    assert result.items[0].quantity_value is None                # "2 potatoes" would be wrong: it was pounds


def test_a_unit_from_another_fragment_is_not_accepted(rules):
    stub = StubLlm([_item("potatoes", 2, "jar")])
    result = _with_llm(rules, stub).parse("two-ish potatoes, a jar of that weird jam")
    potatoes = next(i for i in result.items if i.canonical_name and "potato" in i.canonical_name)
    assert potatoes.quantity_unit != "jar"


def test_a_food_the_user_never_mentioned_is_rejected(rules):
    baseline = rules.parse("two-ish pounds potatoes")
    result = _with_llm(rules, StubLlm([_item("saffron", 2, "lb")])).parse("two-ish pounds potatoes")
    assert result.items == baseline.items


def test_a_number_that_is_not_in_the_text_is_dropped_not_trusted(rules):
    result = _with_llm(rules, StubLlm([_item("potatoes", 5, "lb")])).parse("two-ish pounds potatoes")
    item = result.items[0]
    assert item.match_status is MatchStatus.MATCHED
    assert item.grams != pytest.approx(5 * 453.6, abs=5)         # never 5 lb: the user said two
    assert item.quantity_is_assumed                              # the rules' labelled default instead


@pytest.mark.parametrize("text, value", [
    ("half a kg of that flour thing", 0.5),
    ("a dozen of the large eggs", 12.0),
    ("half a dozen eggs", 6.0),
    ("one and a half pounds of potatoes", 1.5),
    ("1 1/2 cups of rice", 1.5),
    ("1½ cups of rice", 1.5),
    ("two-ish pounds potatoes", 2.0),
    ("~2.5kg onions", 2.5),
])
def test_numbers_the_user_could_have_meant_are_recognised(text, value):
    assert any(abs(n - value) < 1e-6 for n in _numbers_in(text))


def test_numbers_the_user_did_not_write_are_not_recognised():
    assert not any(abs(n - 5.0) < 1e-6 for n in _numbers_in("two-ish pounds potatoes"))


def test_llm_failure_keeps_the_rules_result(rules):
    baseline = rules.parse("two-ish pounds potatoes")
    stub = StubLlm(error=LlmError("server down"))
    assert _with_llm(rules, stub).parse("two-ish pounds potatoes").items == baseline.items


def test_garbage_answer_keeps_the_rules_result(rules):
    class Garbage(StubLlm):
        def complete_json(self, messages, schema):
            return {"items": "not a list"}

    baseline = rules.parse("two-ish pounds potatoes")
    assert _with_llm(rules, Garbage()).parse("two-ish pounds potatoes").items == baseline.items


def test_the_users_own_urgency_cue_is_kept(rules):
    text = "my last two carrots are getting old"
    assert rules.parse(text).items[0].urgency is Urgency.SOON            # premise: the rules read the cue
    result = _with_llm(rules, StubLlm([_item("carrots", 2)])).parse(text)
    item = result.items[0]
    assert item.urgency is Urgency.SOON and item.match_status is MatchStatus.MATCHED
    assert WARNING in item.warnings


def test_the_model_cannot_create_urgency(rules):
    result = _with_llm(rules, StubLlm([_item("potatoes", 2, "pounds")])).parse("two-ish pounds potatoes")
    assert result.items[0].urgency is Urgency.NONE


def test_parser_with_llm_degrades_to_rules_when_the_server_is_down(rules):
    down = StubLlm([_item("potatoes", 2, "pounds")], available=False)
    parser = parser_with_llm(down, store=rules._store, resolver=rules._resolver)       # noqa: SLF001
    result = parser.parse("two-ish pounds potatoes")
    assert down.calls == [] and result.items[0].match_status is MatchStatus.UNKNOWN


def test_parser_with_llm_attaches_the_fallback_when_available(rules):
    up = StubLlm([_item("potatoes", 2, "pounds")])
    parser = parser_with_llm(up, store=rules._store, resolver=rules._resolver)         # noqa: SLF001
    assert parser.parse("two-ish pounds potatoes").items[0].match_status is MatchStatus.MATCHED
