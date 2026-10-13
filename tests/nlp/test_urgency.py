"""Tests for nlp.urgency.find_urgency. 2026-10-12 is a Monday (see conftest.FIXED_TODAY)."""
import pytest

from nlp.schemas import Urgency
from nlp.urgency import find_urgency


@pytest.mark.parametrize("text, level, days, rest", [
    ("spinach getting old", Urgency.SOON, 3, "spinach"),
    ("spinach that's going bad", Urgency.URGENT, 1, "spinach"),
    ("lettuce is wilting", Urgency.URGENT, 1, "lettuce"),
    ("bananas very ripe", Urgency.SOON, 3, "bananas"),
    ("mushrooms - need using up", Urgency.SOON, 3, "mushrooms"),
])
def test_qualitative_cues(text, level, days, rest, today):
    cue, remainder = find_urgency(text, today)
    assert cue.level is level and cue.days_left == days and remainder == rest


@pytest.mark.parametrize("text, level, days", [
    ("milk expires tomorrow", Urgency.URGENT, 1),
    ("chicken must be used today", Urgency.URGENT, 0),
    ("eggs good for 3 days", Urgency.SOON, 3),
    ("yogurt use by friday", Urgency.SOON, 4),          # Monday -> Friday
    ("milk best before next friday", Urgency.SOON, 4),  # "next friday" = the coming friday (documented)
    ("bread expires in 2 weeks", Urgency.NONE, 14),     # reported, but not urgent
])
def test_explicit_dates(text, level, days, today):
    cue, _ = find_urgency(text, today)
    assert cue.level is level and cue.days_left == days


def test_remainder_has_no_dangling_words(today):
    assert find_urgency("must be used today chicken", today)[1] == "chicken"
    assert find_urgency("chicken must be used today", today)[1] == "chicken"


@pytest.mark.parametrize("text", ["carrots", "not going bad", "still fresh tomatoes", "isn't getting old"])
def test_no_cue_and_negation(text, today):
    cue, rest = find_urgency(text, today)
    assert cue is None and rest == text


def test_mouldy_is_flagged_unsafe(today):
    cue, rest = find_urgency("cheese has gone mouldy", today)
    assert cue.may_be_unsafe and cue.level is Urgency.URGENT and rest == "cheese"


def test_bare_cue_leaves_empty_remainder_and_scope(today):
    cue, rest = find_urgency("they're going bad", today)
    assert rest == "" and cue.scope == "item"
    cue, rest = find_urgency("both going bad", today)
    assert rest == "" and cue.scope == "both"
    cue, rest = find_urgency("they're all going bad", today)
    assert rest == "" and cue.scope == "all"


def test_explicit_flag_separates_known_dates_from_guesses(today):
    """A stated date is a known constraint; "getting old" is only our estimate (the planner treats them differently)."""
    assert find_urgency("milk expires tomorrow", today)[0].explicit is True
    assert find_urgency("eggs good for 3 days", today)[0].explicit is True
    assert find_urgency("spinach getting old", today)[0].explicit is False
    assert find_urgency("lettuce is wilting", today)[0].explicit is False
