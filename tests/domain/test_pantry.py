"""Tests for ``domain/pantry.py``: how much the planner is told to believe about each deadline."""
from __future__ import annotations

import pytest

from domain.pantry import LEFTOVER_DAYS, estimate_last_use_day, pantry_from_parse
from knowledge.store import ShelfLife
from nlp.schemas import GramsSource, MatchStatus, ParsedItem, ParseResult, Urgency


def _shelf(lo, hi, confidence="high", indefinite=False) -> ShelfLife:
    return ShelfLife(storage="refrigerator", min_days=lo, max_days=hi, confidence=confidence,
                     source="foodkeeper", is_indefinite=indefinite)


def _item(store, name="spinach", grams=200.0, **kw) -> ParsedItem:
    info = store.ingredient_by_name(name)
    assert info is not None, f"{name!r} missing from the dataset"
    base = dict(raw_text=name, name_text=name, ingredient_id=info.ingredient_id, canonical_name=name,
                match_status=MatchStatus.MATCHED, grams=grams, grams_source=GramsSource.EXPLICIT_MASS)
    base.update(kw)
    return ParsedItem(**base)


def _build(store, *items):
    return pantry_from_parse(ParseResult(source_text="", items=list(items)), store)


# ---------------------------------------------------------------------------------------------- estimate_last_use_day
def test_shelf_life_halved_for_unknown_age():
    # 3-5 days -> typical 4 -> 2 days assumed remaining -> last usable day index 1; "high" confidence = 0.7
    assert estimate_last_use_day(_shelf(3, 5)) == (1, 0.7)
    # 10-14 days -> typical 12 -> 6 remaining -> index 5, still inside a 7-day plan
    assert estimate_last_use_day(_shelf(10, 14, "medium")) == (5, 0.5)


def test_long_shelf_life_means_no_deadline():
    day, conf = estimate_last_use_day(_shelf(20, 30, "low"))
    assert day is None and conf == 0.3


def test_missing_or_indefinite_shelf_life_means_no_deadline():
    assert estimate_last_use_day(None) == (None, 0.5)
    assert estimate_last_use_day(_shelf(None, None, indefinite=True))[0] is None


def test_deadline_is_never_negative():
    day, _ = estimate_last_use_day(_shelf(0.5, 1))
    assert day == 0


# ------------------------------------------------------------------------------------------------ deadline ladder
def test_stated_date_is_a_known_hard_deadline(store):
    built = _build(store, _item(store, days_left_hint=1, days_left_explicit=True, urgency=Urgency.URGENT))
    it = built.items[0]
    assert (it.last_use_day, it.expiry_known, it.expiry_confidence) == (1, True, 1.0)
    assert it.urgency is Urgency.URGENT


def test_qualitative_cue_is_a_soft_estimate(store):
    built = _build(store, _item(store, days_left_hint=3, days_left_explicit=False, urgency=Urgency.SOON))
    it = built.items[0]
    assert (it.last_use_day, it.expiry_known) == (3, False)
    assert it.expiry_confidence == pytest.approx(0.6)


def test_stated_date_beyond_the_horizon_is_known_but_not_binding(store):
    it = _build(store, _item(store, days_left_hint=14, days_left_explicit=True)).items[0]
    assert it.last_use_day is None and it.expiry_known


def test_leftovers_get_the_food_safety_default(store):
    it = _build(store, _item(store, modifiers=["leftovers"])).items[0]
    assert it.last_use_day == LEFTOVER_DAYS and not it.expiry_known


def test_frozen_food_has_no_deadline_this_week(store):
    it = _build(store, _item(store, storage_hint="freezer")).items[0]
    assert it.last_use_day is None


def test_no_cue_falls_back_to_the_foodkeeper_default(store):
    info = store.ingredient_by_name("spinach")
    expected_day, expected_conf = estimate_last_use_day(store.default_shelf_life(info.ingredient_id))
    it = _build(store, _item(store)).items[0]
    assert (it.last_use_day, it.expiry_confidence, it.expiry_known) == (expected_day, expected_conf, False)


# ------------------------------------------------------------------------------------------------ skipping + merging
def test_unusable_items_are_skipped_with_a_reason(store):
    unknown = ParsedItem(raw_text="xyzzy", name_text="xyzzy")
    ambiguous = _item(store, match_status=MatchStatus.AMBIGUOUS)
    no_amount = _item(store, grams=None)
    unsafe = _item(store, warnings=["may be unsafe to eat"])
    built = _build(store, unknown, ambiguous, no_amount, unsafe)
    assert built.items == []
    reasons = [r for _, r in built.skipped]
    assert reasons == ["ingredient not recognised", "ingredient match not confident; ask the user", "no amount",
                       "may be unsafe to eat"]


def test_duplicates_merge_grams_and_keep_the_earliest_known_deadline(store):
    a = _item(store, grams=100, days_left_hint=3, days_left_explicit=False, urgency=Urgency.SOON)
    b = _item(store, grams=50, days_left_hint=1, days_left_explicit=True, urgency=Urgency.URGENT)
    built = _build(store, a, b)
    assert len(built.items) == 1
    m = built.items[0]
    assert m.grams == pytest.approx(150)
    assert m.last_use_day == 1 and m.expiry_known and m.expiry_confidence == 1.0
    assert m.urgency is Urgency.URGENT


# ------------------------------------------------------------------------------ helpers added for the app layer
def test_the_assumed_quantity_flag_travels_from_the_parse_to_the_planner(store):
    built = _build(store, _item(store, "spinach", 250, quantity_is_assumed=True),
                   _item(store, "milk", 500, quantity_is_assumed=False))
    flags = {store.ingredient(i.ingredient_id).canonical_name: i.quantity_assumed for i in built.items}
    assert flags == {"spinach": True, "milk": False}


def test_merging_keeps_an_assumption_if_any_part_was_assumed(store):
    from domain.pantry import merge_pantry_items
    spinach = store.ingredient_by_name("spinach").ingredient_id
    from domain.models import PantryItem
    merged = merge_pantry_items([PantryItem(ingredient_id=spinach, grams=100, last_use_day=3),
                                 PantryItem(ingredient_id=spinach, grams=50, last_use_day=1, quantity_assumed=True)])
    assert len(merged) == 1
    assert (merged[0].grams, merged[0].last_use_day, merged[0].quantity_assumed) == (150, 1, True)


def test_skip_reasons_are_stable_constants(store):
    from domain.pantry import SKIP_AMBIGUOUS, SKIP_NO_AMOUNT, SKIP_UNKNOWN, SKIP_UNSAFE
    unknown = ParsedItem(raw_text="kimchi", name_text="kimchi", match_status=MatchStatus.UNKNOWN)
    ambiguous = _item(store, match_status=MatchStatus.AMBIGUOUS)
    no_amount = _item(store, grams=None)
    unsafe = _item(store, warnings=["looks moulded: unsafe to eat"])
    reasons = [r for _, r in _build(store, unknown, ambiguous, no_amount, unsafe).skipped]
    assert reasons == [SKIP_UNKNOWN, SKIP_AMBIGUOUS, SKIP_NO_AMOUNT, SKIP_UNSAFE]


def test_make_pantry_item_stated_date_is_known_and_hard(store):
    from domain.pantry import make_pantry_item
    spinach = store.ingredient_by_name("spinach").ingredient_id
    it = make_pantry_item(spinach, 200, store, days_left=2, urgency=Urgency.URGENT)
    assert (it.last_use_day, it.expiry_known, it.expiry_confidence, it.urgency) == (2, True, 1.0, Urgency.URGENT)
    assert not it.quantity_assumed
    assert make_pantry_item(spinach, 200, store, days_left=30).last_use_day is None      # beyond the plan


def test_make_pantry_item_vague_cue_is_an_estimate_and_no_date_uses_the_shelf_life(store):
    from domain.pantry import make_pantry_item
    spinach = store.ingredient_by_name("spinach").ingredient_id
    vague = make_pantry_item(spinach, 200, store, days_left=1, days_left_explicit=False)
    assert (vague.last_use_day, vague.expiry_known, vague.expiry_confidence) == (1, False, 0.6)
    default = make_pantry_item(spinach, 200, store)
    assert not default.expiry_known
    assert (default.last_use_day, default.expiry_confidence) == estimate_last_use_day(
        store.default_shelf_life(spinach))
