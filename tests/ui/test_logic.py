"""Tests for ``ui/logic.py``: what marks on the week mean, and how a use-by choice is applied. No Streamlit."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytest

from app.models import ENTRY_ASSUMED, ENTRY_CHOOSE, ENTRY_NO_AMOUNT, ENTRY_OK, ENTRY_UNKNOWN, ENTRY_UNSAFE, PantryEntry
from ui.logic import (DAY_COOKED, display_name, DAY_MARKS, DAY_PLANNED, DAY_REJECTED, DAY_SKIPPED, apply_use_by, build_replan_request,
                      current_use_by_index, local_today, md_escape, needs_choice, status_label, use_by_choices,
                      weekday_label)

IDS = [101, 102, 103, 104, 105, 106, 107]


def _marks(**by_day: str) -> list[str]:
    """``_marks(d0=DAY_COOKED, d3=DAY_REJECTED)`` -> 7 marks, the rest planned."""
    out = [DAY_PLANNED] * 7
    for key, mark in by_day.items():
        out[int(key[1:])] = mark
    return out


# ---------------------------------------------------------------------------------------------------- replanning
def test_nothing_marked_means_nothing_to_do():
    r = build_replan_request(IDS, [DAY_PLANNED] * 7)
    assert not r.changed and not r.ok and r.problem == "" and r.remaining_days == 7
    assert "Mark a day" in r.describe()


def test_a_leading_run_of_cooked_and_skipped_days_is_the_past():
    r = build_replan_request(IDS, _marks(d0=DAY_COOKED, d1=DAY_SKIPPED))
    assert r.ok and r.cooked == (101, None) and r.rejected == () and r.remaining_days == 5


def test_a_rejected_dinner_is_excluded_and_does_not_end_the_past():
    r = build_replan_request(IDS, _marks(d0=DAY_COOKED, d4=DAY_REJECTED))
    assert r.cooked == (101,) and r.rejected == (105,) and r.remaining_days == 6


def test_rejecting_todays_dinner_replans_the_whole_week_without_it():
    r = build_replan_request(IDS, _marks(d0=DAY_REJECTED))
    assert r.ok and r.cooked == () and r.rejected == (101,) and r.remaining_days == 7


def test_a_cooked_day_after_an_unresolved_one_is_a_contradiction_not_a_guess():
    r = build_replan_request(IDS, _marks(d2=DAY_COOKED))
    assert not r.ok and "Mark days in order" in r.problem and r.problem == r.describe()
    r = build_replan_request(IDS, _marks(d0=DAY_REJECTED, d1=DAY_COOKED))
    assert not r.ok and "day 2" in r.problem.lower()


def test_marking_every_day_done_leaves_nothing_to_plan():
    r = build_replan_request(IDS, [DAY_COOKED] * 7)
    assert not r.ok and "nothing left to plan" in r.problem


def test_the_description_says_what_will_happen():
    r = build_replan_request(IDS, _marks(d0=DAY_COOKED, d1=DAY_SKIPPED, d3=DAY_REJECTED))
    text = r.describe(["Lemon chicken"])
    assert "2 days will count as past (1 cooked, 1 skipped)" in text
    assert "Lemon chicken will not come back" in text and "remaining 5 days" in text and text.endswith(".")


def test_bad_input_is_rejected_loudly():
    with pytest.raises(ValueError):
        build_replan_request(IDS, [DAY_PLANNED] * 6)
    with pytest.raises(ValueError, match="unknown day mark"):
        build_replan_request(IDS, ["Eaten"] + [DAY_PLANNED] * 6)


def test_the_marks_the_ui_offers_are_exactly_the_ones_the_logic_understands():
    assert set(DAY_MARKS) == {DAY_PLANNED, DAY_COOKED, DAY_SKIPPED, DAY_REJECTED}


# ---------------------------------------------------------------------------------------------------- use-by
def _entry(**kw) -> PantryEntry:
    base = dict(raw_text="spinach", ingredient_id=1, name="spinach", grams=200.0, last_use_day=2, expiry_known=False,
                expiry_confidence=0.6, status=ENTRY_OK)
    base.update(kw)
    return PantryEntry(**base)


def test_the_choices_start_with_our_estimate_and_end_with_never():
    choices = use_by_choices(start_weekday=2, horizon_days=7, original=_entry(last_use_day=2))
    assert choices[0].kind == "estimate" and "use by Friday" in choices[0].label          # Wed + 2
    assert [c.label for c in choices[1:3]] == ["Today", "Tomorrow"]
    assert choices[3].label == "Friday (in 2 days)"
    assert choices[-1].kind == "never" and len(choices) == 1 + 7 + 1


def test_the_estimate_label_says_when_there_is_no_deadline():
    c = use_by_choices(0, 7, _entry(last_use_day=None))
    assert "keeps this week" in c[0].label


def test_the_current_choice_follows_the_entry():
    original = _entry()
    choices = use_by_choices(0, 7, original)
    assert current_use_by_index(original, choices) == 0                               # an estimate
    stated = original.with_days_left(3)
    assert choices[current_use_by_index(stated, choices)].days == 3
    never = original.with_days_left(None)
    assert choices[current_use_by_index(never, choices)].kind == "never"


def test_picking_a_day_states_a_hard_deadline_and_picking_not_sure_restores_the_estimate():
    original = _entry(last_use_day=4, expiry_known=False, expiry_confidence=0.5)
    choices = use_by_choices(0, 7, original)
    stated = apply_use_by(original, original, choices[2], 7)                           # "Tomorrow"
    assert (stated.last_use_day, stated.expiry_known, stated.expiry_confidence) == (1, True, 1.0)
    back = apply_use_by(stated, original, choices[0], 7)
    assert (back.last_use_day, back.expiry_known, back.expiry_confidence) == (4, False, 0.5)
    never = apply_use_by(original, original, choices[-1], 7)
    assert never.last_use_day is None and never.expiry_known


# ---------------------------------------------------------------------------------------------------- labels
@pytest.mark.parametrize("status, kind", [(ENTRY_OK, "ok"), (ENTRY_ASSUMED, "assumed"), (ENTRY_CHOOSE, "choose"),
                                          (ENTRY_UNKNOWN, "unknown"), (ENTRY_NO_AMOUNT, "amount"),
                                          (ENTRY_UNSAFE, "unsafe")])
def test_every_status_has_a_label(status, kind):
    k, text = status_label(_entry(status=status))
    assert k == kind and text


def test_only_unresolved_rows_ask_for_a_choice():
    assert needs_choice(_entry(ingredient_id=None, name=None, status=ENTRY_UNKNOWN))
    assert needs_choice(_entry(ingredient_id=None, name=None, status=ENTRY_CHOOSE))
    assert not needs_choice(_entry())
    assert not needs_choice(_entry(status=ENTRY_NO_AMOUNT))               # known ingredient, amount missing


def test_weekday_label_with_an_offset():
    assert weekday_label(2, 0) == "Wednesday"
    assert weekday_label(2, 0, day_offset=-2) == "Monday"
    assert weekday_label(6, 1) == "Monday"


def test_display_name_restores_the_possessive_food_com_dropped():
    assert display_name("julie s salsa chicken") == "Julie's Salsa Chicken"
    assert display_name("grandma s apple pie") == "Grandma's Apple Pie"
    assert display_name("all-purpose flour") == "All-Purpose Flour"
    assert display_name("easy mac and cheese") == "Easy Mac And Cheese"           # no lone "s": untouched
    assert display_name("  spinach  ") == "Spinach"


# ---------------------------------------------------------------------------------------------------- markdown safety
@pytest.mark.parametrize("payload", [
    "![x](https://attacker.example/p.png)",                # image: would load an outside URL
    "[click](javascript:alert(1))",                        # link
    ":red[big] text",                                      # Streamlit colour directive
    "**bold** _it_",
    "$x^2$",                                               # LaTeX
    "<b>tag</b> `code` # heading",
])
def test_md_escape_neutralises_markdown(payload):
    # every character Markdown could act on is preceded by a backslash (an even run of backslashes would not count)
    unescaped = re.findall(r"(?<!\\)(?:\\\\)*[\[\]()*_:$`<>#!]", md_escape(payload))
    assert unescaped == []


def test_md_escape_keeps_the_visible_text_and_flattens_lines():
    typed = "line one\n# heading \\ end [x](y)"
    out = md_escape(typed)
    assert "\n" not in out and "\\#" in out                # no new block can start; "#" is literal
    # removing one backslash before each escaped character gives back what was typed (newline folded to a space)
    assert re.sub(r"\\(.)", r"\1", out) == "line one # heading \\ end [x](y)"


# ---------------------------------------------------------------------------------------------------- the user's today
# 20:30 UTC on Wednesday 14 Oct 2026 = 04:30 on Thursday 15 Oct in Singapore: the hours where the server's UTC date was
# a day behind the user.
LATE_UTC = datetime(2026, 10, 14, 20, 30, tzinfo=timezone.utc)


def test_today_is_the_browsers_date_not_the_servers():
    assert local_today("Asia/Singapore", LATE_UTC) == (date(2026, 10, 15), "browser")
    assert local_today("America/New_York", LATE_UTC) == (date(2026, 10, 14), "browser")


@pytest.mark.parametrize("bad", ["Mars/Olympus_Mons", "../../etc/passwd", "", None])
def test_an_unusable_browser_timezone_falls_back_to_the_configured_one(bad):
    # the browser's value is client-supplied: anything unknown or malformed is ignored, never an error
    assert local_today(bad, LATE_UTC, configured_timezone="Asia/Singapore") == (date(2026, 10, 15), "configured")


def test_without_any_timezone_the_server_date_is_used_and_says_so():
    day, source = local_today(None, LATE_UTC, configured_timezone="Not/AZone")
    assert source == "server" and day == LATE_UTC.astimezone().date()
