"""Tests for ``optimizer/replan.py``: rolling a scenario forward so the remaining days can be re-planned from here.

A fake catalogue keeps each test's numbers stated by hand (recipe ids are the list positions).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from domain.models import PantryItem, Scenario
from nlp.schemas import Urgency
from optimizer.replan import roll_forward


class FakeCatalog:
    def __init__(self, recipes: list[dict[int, float]]) -> None:
        self._recipes = recipes

    def ingredients(self, idx: int):
        r = self._recipes[idx]
        return np.array(list(r), dtype=np.int32), np.array(list(r.values()), dtype=np.float32)

    def index_of(self, recipe_id: int) -> int:
        return recipe_id


def _ctx(recipes, ignore=()):
    return SimpleNamespace(catalog=FakeCatalog(recipes), ignore_ids=frozenset(ignore), store=None)


@pytest.fixture(autouse=True)
def _no_substitution_rules(monkeypatch):
    """The fake catalogue's ingredient ids are not real foods, so the real substitution table must not apply."""
    monkeypatch.setattr("optimizer.substitutions.default_rules", lambda store: ())


def _item(iid, grams, last_use_day=None, known=False, conf=1.0, urgency=Urgency.NONE) -> PantryItem:
    return PantryItem(ingredient_id=iid, grams=grams, last_use_day=last_use_day, expiry_known=known,
                      expiry_confidence=conf, urgency=urgency)


def _scenario(pantry, horizon=7, start=0) -> Scenario:
    return Scenario(scenario_id="s", pantry=pantry, horizon_days=horizon, start_weekday=start)


def test_cooked_dinners_leave_the_pantry_and_the_horizon_shrinks():
    ctx = _ctx([{1: 60.0}, {2: 5.0}])
    out = roll_forward(_scenario([_item(1, 100)], start=2), [0, 1], ctx)
    sc = out.scenario
    assert sc.horizon_days == 5 and sc.start_weekday == 4 and out.elapsed_days == 2
    assert [(p.ingredient_id, p.grams) for p in sc.pantry] == [(1, pytest.approx(40.0))]
    assert out.consumed_g == {1: pytest.approx(60.0)} and out.expired_g == {}


def test_deadlines_shift_and_keep_what_we_knew_about_them():
    ctx = _ctx([{9: 1.0}, {9: 1.0}])
    pantry = [_item(1, 80, last_use_day=4, known=True, conf=1.0, urgency=Urgency.URGENT),
              _item(2, 50, last_use_day=5, known=False, conf=0.5)]
    out = roll_forward(_scenario(pantry), [0, 1], ctx)
    by_id = {p.ingredient_id: p for p in out.scenario.pantry}
    assert by_id[1].last_use_day == 2 and by_id[1].expiry_known and by_id[1].urgency is Urgency.URGENT
    assert by_id[2].last_use_day == 3 and not by_id[2].expiry_known and by_id[2].expiry_confidence == 0.5


def test_stock_that_went_off_while_days_passed_is_dropped_and_reported():
    ctx = _ctx([{9: 1.0}, {9: 1.0}])
    out = roll_forward(_scenario([_item(1, 120, last_use_day=1, known=True), _item(2, 30)]), [0, 1], ctx)
    assert [p.ingredient_id for p in out.scenario.pantry] == [2]          # ingredient 1's deadline (day 1) is past
    assert out.expired_g == {1: pytest.approx(120.0)}


def test_deadline_on_the_last_elapsed_day_is_still_usable_that_day_but_not_after():
    ctx = _ctx([{1: 50.0}, {9: 1.0}])
    # day 0 cooks with it; the rest expires at the end of day 1 (deadline 1), and two days have passed -> expired
    out = roll_forward(_scenario([_item(1, 100, last_use_day=1, known=True)]), [0, 1], ctx)
    assert out.consumed_g == {1: pytest.approx(50.0)} and out.expired_g == {1: pytest.approx(50.0)}
    assert out.scenario.pantry == []


def test_a_skipped_day_consumes_nothing_but_the_clock_runs():
    ctx = _ctx([{1: 60.0}])
    out = roll_forward(_scenario([_item(1, 100, last_use_day=3, known=True)]), [None, 0], ctx)
    p = out.scenario.pantry[0]
    assert p.grams == pytest.approx(40.0) and p.last_use_day == 1        # day 3 - 2 elapsed
    assert out.scenario.horizon_days == 5


def test_a_rejected_dinners_ingredients_stay_and_keep_their_urgency():
    """Rejecting day 0's dinner = day 0 is skipped: the food it would have used is still there, one day closer."""
    ctx = _ctx([{1: 60.0}])
    out = roll_forward(_scenario([_item(1, 100, last_use_day=2, known=True)]), [None], ctx)
    p = out.scenario.pantry[0]
    assert p.grams == pytest.approx(100.0) and p.last_use_day == 1


def test_staples_are_not_carried():
    ctx = _ctx([{1: 10.0}], ignore={99})
    out = roll_forward(_scenario([_item(1, 50), _item(99, 500)]), [0], ctx)
    assert [p.ingredient_id for p in out.scenario.pantry] == [1]


def test_the_original_scenario_is_not_modified():
    ctx = _ctx([{1: 60.0}])
    original = _scenario([_item(1, 100, last_use_day=3)])
    snapshot = original.model_dump()
    roll_forward(original, [0], ctx)
    assert original.model_dump() == snapshot


def test_nothing_left_to_plan_is_an_error():
    ctx = _ctx([{1: 1.0}] * 3)
    with pytest.raises(ValueError, match="nothing left to plan"):
        roll_forward(_scenario([_item(1, 10)], horizon=3), [0, 1, 2], ctx)


def test_scenario_id_records_the_roll_forward():
    ctx = _ctx([{1: 1.0}])
    assert roll_forward(_scenario([_item(1, 10)]), [0], ctx).scenario.scenario_id == "s+d1"


def test_a_cooked_dinner_that_used_a_substitution_used_up_the_substitutes(monkeypatch):
    from optimizer.substitutions import ResolvedRule
    # ingredient 9 is "bought" by dinner 0 unless the rule swaps in 1 + 2 from the pantry (0.9 / 0.1 per gram)
    monkeypatch.setattr("optimizer.substitutions.default_rules",
                        lambda store: (ResolvedRule("nine", 9, ((1, 0.9), (2, 0.1)), ""),))
    monkeypatch.setattr("optimizer.substitutions.allowed_substitutes", lambda store, profile, rules: {1, 2})
    out = roll_forward(_scenario([_item(1, 500), _item(2, 100)]), [0], _ctx([{9: 200.0}]))
    assert out.consumed_g == {1: pytest.approx(180.0), 2: pytest.approx(20.0)}
    assert {p.ingredient_id: p.grams for p in out.scenario.pantry} == {1: pytest.approx(320.0), 2: pytest.approx(80.0)}
