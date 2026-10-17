"""Tests for ``ui/theme.py``: the HTML building blocks escape what they are given, and the stylesheet keeps the
promises the design makes (reduced motion honoured, staggered entrance, the palette in use)."""
from __future__ import annotations

import pytest

from ui import theme

EVIL = '<img src=x onerror="alert(1)">'


@pytest.mark.parametrize("render", [
    lambda s: theme.hero_html(s, s, [s]),
    lambda s: theme.section_html(s, s),
    lambda s: theme.chips_html([(s, "good")]),
    lambda s: theme.day_label_html(s),
    lambda s: theme.empty_state_html(s, s, s),
    lambda s: theme.stepper_html(0, [s, "b", "c"]),
    lambda s: theme.food_icon_html(s),
])
def test_every_building_block_escapes_its_text(render):
    out = render(EVIL)
    assert "<img" not in out and "&lt;img" in out


def test_stepper_marks_past_current_and_future_steps():
    out = theme.stepper_html(1)
    assert out.count("p2p-step done") == 1 and out.count("p2p-step now") == 1
    assert "✓" in out and ">3<" in out
    with pytest.raises(ValueError):
        theme.stepper_html(3)


def test_chip_tones_are_a_closed_set():
    assert 'class="p2p-chip warn"' in theme.chips_html([("x", "warn")])
    with pytest.raises(ValueError):
        theme.chips_html([("x", "red")])


def test_unknown_food_groups_get_the_basket():
    assert theme.group_icon("vegetable") == "🥦"
    assert theme.group_icon("mystery") == theme.group_icon(None) == "🧺"


def test_every_dataset_food_group_has_its_own_icon(store):
    groups = set(store.all_ingredients().food_group.dropna())
    assert groups - set(theme.GROUP_ICONS) == set()                     # a new group in a rebuild needs an icon


def test_item_icons_name_real_ingredients(store):
    names = set(store.all_ingredients().canonical_name)
    assert set(theme.ITEM_ICONS) - names == set()                       # a typo would silently never match


def test_food_icon_prefers_the_item_then_the_group_then_the_basket():
    assert theme.food_icon("rice", "grain_pasta") == "🍚"                # not the pasta of its group
    assert theme.food_icon("Spinach ", "vegetable") == "🥬"              # tolerant of case and spaces
    assert theme.food_icon("egg noodles", "grain_pasta") == "🍝"         # exact names only: no egg on noodles
    assert theme.food_icon(None, None) == "🧺"


def test_the_stylesheet_honours_reduced_motion_and_staggers_cards():
    css = theme.css()
    assert css.startswith("<style>") and css.rstrip().endswith("</style>")
    assert "prefers-reduced-motion: reduce" in css and "animation: none !important" in css
    assert 'st-key-daycard_0"]' in css and 'st-key-daycard_6"]' in css      # a whole week has entrance delays
    assert theme.GREEN in css and theme.TERRACOTTA in css


def test_the_stylesheet_has_balanced_braces():
    """An unbalanced brace in a 200-line f-string silently drops every rule after it."""
    body = theme.css()[len("<style>"):-len("</style>")]
    assert body.count("{") == body.count("}")
