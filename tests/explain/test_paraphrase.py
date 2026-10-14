"""Tests for ``explain/paraphrase.py``: the validator accepts a faithful rewording and rejects every kind of change the
facts cannot support; the paraphraser degrades to the template on any failure; safety sections never reach the model."""
from __future__ import annotations

import logging

import pytest

from explain.paraphrase import (GENERIC_WORDS, Paraphraser, build_paraphraser, check_paraphrase,
                                ingredient_vocabulary, numbers_in, paraphrase_explanation, stem)
from explain.render import Explanation, Section, Statement, render
from explain.facts import build_facts

VOCAB = frozenset({"chicken", "spinach", "rice", "salmon", "bacon"})
FACTS = ("Chicken pasta takes 35 min and has about 640 kcal and 38 g protein per serving. "
         "Uses 300 g spinach (use by Tuesday, estimated) from your pantry. You need to buy chicken (200 g). "
         "At 410 kcal it is 70 kcal below your dinner range (480-720 kcal).")
TITLE = "Monday: Chicken pasta"


def _problems(candidate: str, facts: str = FACTS, title: str = TITLE, vocab: frozenset[str] = VOCAB) -> list[str]:
    return check_paraphrase(candidate, title, facts, vocab)


# --------------------------------------------------------------------------------------------- the validator
def test_a_faithful_rewording_is_accepted():
    ok = ("Chicken pasta takes 35 min, with about 640 kcal and 38 g protein a serving. It uses up 300 g spinach from "
          "your pantry, which should be used by Tuesday (an estimate), and you buy chicken (200 g). At 410 kcal it "
          "is 70 kcal under your dinner range of 480-720 kcal.")
    assert _problems(ok) == []


def test_the_facts_themselves_always_pass():
    assert _problems(FACTS) == []


def test_number_words_count_as_numbers():
    assert numbers_in("seven dinners and twelve items") == {7.0, 12.0}
    assert numbers_in("1,200 g") == {1200.0}
    assert 1.0 not in numbers_in("this one is good", loose=False) and 1.0 in numbers_in("this one", loose=True)
    assert 0.0 in numbers_in("no protein", loose=True) and 0.0 not in numbers_in("no protein", loose=False)


def test_an_invented_number_is_rejected():
    assert any("invented number" in p for p in _problems(FACTS + " It also has 999 g of fibre."))


def test_a_dropped_number_is_rejected():
    dropped = FACTS.replace("38 g protein ", "")
    assert any("dropped number" in p and "38" in p for p in _problems(dropped))


def test_seven_written_out_matches_7():
    facts = "These 7 dinners need 3 extra items."
    assert _problems("These seven dinners need three extra items.", facts, "Your week") == []


def test_an_invented_food_is_rejected():
    assert any("food(s) not in the facts: salmon" in p for p in _problems(FACTS + " Serve it with salmon."))


def test_a_dropped_food_is_rejected():
    assert any("dropped food(s): spinach" in p for p in _problems(FACTS.replace("spinach", "greens")))


def test_plural_and_singular_are_the_same_food():
    assert _problems(FACTS.replace("buy chicken", "buy chickens")) == []        # not "invented" / "dropped"
    assert stem("tomatoes") == stem("tomato") == "tomato"
    assert stem("eggs") == "egg" and stem("rice") == "rice"


def test_an_invented_weekday_is_rejected_and_the_headings_weekday_is_allowed():
    assert any("weekday(s) not in the facts: friday" in p for p in _problems(FACTS + " Save it for Friday."))
    assert _problems(FACTS + " That is Monday's dinner.") == []             # Monday is in the heading


def test_a_dropped_deadline_day_is_rejected():
    assert any("dropped weekday" in p for p in _problems(FACTS.replace("(use by Tuesday, estimated)", "(estimated)")))


def test_relative_days_are_never_allowed():
    assert any("relative day" in p for p in _problems(FACTS + " Cook it tomorrow."))


def test_a_dropped_warning_is_rejected():
    assert any("'below' no longer expressed" in p for p in
               _problems(FACTS.replace("70 kcal below your dinner range", "70 kcal off your dinner range")))
    assert any("'estimated' no longer expressed" in p for p in
               _problems(FACTS.replace(", estimated", "")))


def test_a_synonym_keeps_the_warning():
    assert _problems(FACTS.replace("below", "under")) == []


@pytest.mark.parametrize("claim", ["It is a healthy choice.", "A delicious dinner.", "This is the perfect meal."])
def test_unsupported_claims_are_rejected(claim):
    assert any("unsupported claim" in p for p in _problems(FACTS + " " + claim))


def test_markup_and_line_breaks_are_rejected():
    assert any("markup" in p for p in _problems("- " + FACTS.replace(". ", ".\n- ")))
    assert any("markup" in p for p in _problems("**" + FACTS + "**"))


def test_padding_is_rejected():
    assert any("longer" in p for p in _problems(FACTS + " " + "Cooking at home is always a good idea. " * 12))


def test_empty_answer_is_rejected():
    assert _problems("   ") == ["empty answer"]


# --------------------------------------------------------------------------------------------- vocabulary
def test_vocabulary_has_real_foods_and_excludes_ordinary_english(store):
    vocab = ingredient_vocabulary(store)
    assert {"chicken", "spinach", "rice", "garlic"} <= vocab
    assert not {stem(w) for w in GENERIC_WORDS} & vocab
    assert len(vocab) > 400


# --------------------------------------------------------------------------------------------- the paraphraser
class _Stub:
    """Fake LLM. ``reply`` maps the user message to an answer; an Exception instance is raised."""

    def __init__(self, reply):
        self.reply, self.calls, self.sent = reply, 0, []

    def complete_text(self, messages, max_tokens=None):
        self.calls += 1
        user = messages[-1]["content"]
        self.sent.append(user)
        out = self.reply(user) if callable(self.reply) else self.reply
        if isinstance(out, Exception):
            raise out
        return out


def _facts_of(user_message: str) -> str:
    return " ".join(line[2:] for line in user_message.splitlines() if line.startswith("- "))


def _section() -> Section:
    sts = tuple(Statement(t, "overview", "replay") for t in (
        "Chicken pasta takes 35 min and has about 640 kcal and 38 g protein per serving.",
        "Uses 300 g spinach (use by Tuesday, estimated) from your pantry."))
    return Section("day:0", TITLE, sts, text=" ".join(s.text for s in sts))


def test_a_valid_rewrite_is_used():
    p = Paraphraser(_Stub(_facts_of), VOCAB)
    result = p.rewrite(_section())
    assert result.text == _section().template_text and result.problems == ()


def test_an_invalid_rewrite_is_not_used_and_says_why():
    p = Paraphraser(_Stub(lambda u: _facts_of(u) + " It has 999 g fibre."), VOCAB)
    result = p.rewrite(_section())
    assert result.text is None and any("invented number" in x for x in result.problems)


def test_the_prompt_contains_only_the_sections_own_facts():
    stub = _Stub(_facts_of)
    Paraphraser(stub, VOCAB).rewrite(_section())
    assert "Uses 300 g spinach" in stub.sent[0] and TITLE in stub.sent[0]


def test_after_a_transport_failure_the_model_is_not_called_again(caplog):
    stub = _Stub(RuntimeError("connection refused"))
    p = Paraphraser(stub, VOCAB)
    with caplog.at_level(logging.WARNING, logger="explain.paraphrase"):
        assert p.rewrite(_section()).text is None
        assert p.rewrite(_section()).problems == ("language model unavailable",)
    assert stub.calls == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "template text kept" in warnings[0].getMessage()   # one line, not one per section


def test_safety_sections_are_never_sent_to_the_model(ctx, optimised_week):
    scenario, plan = optimised_week
    stub = _Stub(_facts_of)
    explanation = render(build_facts(scenario, plan, ctx))
    out = paraphrase_explanation(explanation, Paraphraser(stub, ingredient_vocabulary(ctx.store)))
    keys = [s.key for s in explanation.sections]
    assert stub.calls == sum(1 for k in keys if k == "overview" or k.startswith("day:"))
    for key in ("rules", "caveats"):
        before, after = explanation.section(key), out.section(key)
        if before is not None:
            assert after.text == before.text and after.source == "template"
    assert all(s.source == "llm" for s in out.sections if s.key == "overview" or s.key.startswith("day:"))


def test_rejected_sections_keep_their_template_and_carry_a_note(ctx, optimised_week):
    scenario, plan = optimised_week
    explanation = render(build_facts(scenario, plan, ctx))
    out = paraphrase_explanation(explanation, Paraphraser(_Stub(lambda u: "Healthy and delicious."),
                                                          ingredient_vocabulary(ctx.store)))
    for before, after in zip(explanation.sections, out.sections):
        assert after.text == before.text and after.source == "template"
        if before.key == "overview" or before.key.startswith("day:"):
            assert after.note.startswith("paraphrase not used")


def test_build_paraphraser_is_none_when_the_model_is_unreachable(store):
    class Down:
        def is_available(self):
            return False

        def complete_text(self, messages, max_tokens=None):
            raise AssertionError("must not be called")

    assert build_paraphraser(None, store) is None
    assert build_paraphraser(Down(), store) is None
    assert isinstance(build_paraphraser(_Stub("x"), store), Paraphraser)
