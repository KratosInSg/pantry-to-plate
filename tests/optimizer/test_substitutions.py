"""Tests for ``optimizer/substitutions.py``: a swap fires only when it is safe, complete and costs no later dinner.

The rule mechanics use a tiny fake catalogue and hand-written rules, so each number is stated in the test. The rule
table and the integration with the real dataset (hard rules, unit weights, a real buttermilk recipe) are tested
against ``data/canonical``.
"""
from __future__ import annotations

import numpy as np
import pytest

from domain.models import Diet, PantryItem, Scenario, UserProfile
from optimizer.inventory import account_inventory
from optimizer.substitutions import (MIN_SUBSTITUTION_G, SUBSTITUTION_RULES, ResolvedRule, SubstitutionRule,
                                     allowed_substitutes, apply_substitutions, default_rules, replay_with_substitutions,
                                     resolve_rules)

BUTTERMILK, MILK, LEMON, VINEGAR = 96, 11, 16, 91          # real ids, so the integration tests read the same
MILK_LEMON = ResolvedRule("milk_lemon", BUTTERMILK, ((MILK, 0.9), (LEMON, 0.1)), "stir and wait")
MILK_VINEGAR = ResolvedRule("milk_vinegar", BUTTERMILK, ((MILK, 0.9), (VINEGAR, 0.1)), "")
ALL = {MILK, LEMON, VINEGAR}


class FakeCatalog:
    def __init__(self, recipes: list[dict[int, float]]) -> None:
        self._recipes = recipes

    def ingredients(self, idx: int):
        r = self._recipes[idx]
        return np.array(list(r), dtype=np.int32), np.array(list(r.values()), dtype=np.float32)


def _stock(iid: int, grams: float, last_use_day: int | None = None) -> PantryItem:
    return PantryItem(ingredient_id=iid, grams=grams, last_use_day=last_use_day)


def _replay(recipes, pantry, horizon=7, rules=(MILK_LEMON,), allowed=ALL, ignore=()):
    deadlines = {p.ingredient_id: p.last_use_day for p in pantry}
    report = account_inventory(list(range(len(recipes))), pantry, FakeCatalog(recipes), deadlines, ignore, horizon)
    return report, apply_substitutions(report, deadlines, rules, allowed, ignore)


# ------------------------------------------------------------------------------------------------ mechanics
def test_fires_when_the_dinner_buys_the_food_and_spare_stock_covers_it():
    before, out = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 500), _stock(LEMON, 100)])
    assert before.groceries_g == {BUTTERMILK: pytest.approx(200)}
    assert out.report.groceries_g == {} and out.report.groceries_by_day == [{}]
    assert out.report.uses_by_day[0] == {MILK: pytest.approx(180), LEMON: pytest.approx(20)}
    assert out.report.unused_g == {MILK: pytest.approx(320), LEMON: pytest.approx(80)}
    [sw] = out.substitutions
    assert (sw.day, sw.rule_key, sw.replaced_id, sw.note) == (0, "milk_lemon", BUTTERMILK, "stir and wait")
    assert sw.replaced_g == pytest.approx(200) and dict(sw.uses) == {MILK: pytest.approx(180), LEMON: pytest.approx(20)}
    assert out.on_day(0) == (sw,) and out.on_day(1) == ()


def test_the_input_replay_is_not_modified():
    before, _ = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 500), _stock(LEMON, 100)])
    assert before.groceries_g == {BUTTERMILK: pytest.approx(200)} and before.uses_by_day == [{}]


def test_never_takes_stock_a_later_dinner_needs():
    # day 1 cooks with 400 g milk: only 100 g is spare, not the 180 g the swap on day 0 would need
    _, out = _replay([{BUTTERMILK: 200.0}, {MILK: 400.0}], [_stock(MILK, 500), _stock(LEMON, 100)])
    assert out.substitutions == ()
    assert out.report.groceries_g == {BUTTERMILK: pytest.approx(200)}


def test_a_substitute_past_its_deadline_cannot_be_used():
    _, out = _replay([{2: 10.0}, {BUTTERMILK: 200.0}], [_stock(MILK, 500), _stock(LEMON, 100, last_use_day=0)])
    assert out.substitutions == ()


def test_a_disallowed_substitute_blocks_the_rule_and_the_next_rule_is_tried():
    _, out = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 500), _stock(LEMON, 100), _stock(VINEGAR, 100)],
                     rules=(MILK_LEMON, MILK_VINEGAR), allowed={MILK, VINEGAR})
    assert [s.rule_key for s in out.substitutions] == ["milk_vinegar"]


def test_rules_are_tried_in_order():
    _, out = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 500), _stock(LEMON, 100), _stock(VINEGAR, 100)],
                     rules=(MILK_VINEGAR, MILK_LEMON))
    assert [s.rule_key for s in out.substitutions] == ["milk_vinegar"]


def test_no_partial_swap():
    _, out = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 100), _stock(LEMON, 100)])
    assert out.substitutions == () and out.report.groceries_g == {BUTTERMILK: pytest.approx(200)}


def test_own_stock_of_the_food_is_used_first_and_only_the_shortfall_is_swapped():
    _, out = _replay([{BUTTERMILK: 200.0}], [_stock(BUTTERMILK, 50), _stock(MILK, 500), _stock(LEMON, 100)])
    [sw] = out.substitutions
    assert sw.replaced_g == pytest.approx(150)
    assert out.report.uses_by_day[0] == {BUTTERMILK: pytest.approx(50), MILK: pytest.approx(135),
                                         LEMON: pytest.approx(15)}


def test_swapping_in_expiring_stock_reduces_waste():
    before, out = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 500, last_use_day=3), _stock(LEMON, 100)])
    assert before.waste_g == {MILK: pytest.approx(500)}
    assert out.report.waste_g == {MILK: pytest.approx(320)}
    assert out.report.total_consumed_g == pytest.approx(before.total_consumed_g + 200)


def test_a_staple_substitute_is_available_without_being_accounted():
    _, out = _replay([{BUTTERMILK: 200.0}], [_stock(MILK, 500)], ignore={LEMON})
    [sw] = out.substitutions
    assert dict(sw.uses) == {MILK: pytest.approx(180), LEMON: 0.0}
    assert LEMON not in out.report.uses_by_day[0]


def test_a_pinch_is_not_worth_a_rule():
    _, out = _replay([{BUTTERMILK: MIN_SUBSTITUTION_G / 2}], [_stock(MILK, 500), _stock(LEMON, 100)])
    assert out.substitutions == ()


def test_two_days_share_the_spare_stock():
    # 300 g milk spare: day 0 takes 180 g, so day 1 (180 g more) cannot be covered as well
    _, out = _replay([{BUTTERMILK: 200.0}, {BUTTERMILK: 200.0}], [_stock(MILK, 300), _stock(LEMON, 100)])
    assert [s.day for s in out.substitutions] == [0]
    assert out.report.groceries_g == {BUTTERMILK: pytest.approx(200)}


# ------------------------------------------------------------------------------------------------ rule table
def test_every_rule_resolves_against_the_dataset(store):
    rules = default_rules(store)
    assert [r.key for r in rules] == [r.key for r in SUBSTITUTION_RULES]
    assert len({r.key for r in rules}) == len(rules)
    for rule in rules:
        assert rule.ratios and all(ratio > 0 for _, ratio in rule.ratios)
        assert rule.replaced_id not in {sid for sid, _ in rule.ratios}
    buttermilk = next(r for r in rules if r.key == "buttermilk_milk_lemon")
    # 1 cup buttermilk = 15 tbsp milk + 1 tbsp lemon juice, converted with the dataset's unit weights
    assert dict(buttermilk.ratios)[MILK] == pytest.approx(0.92, abs=0.02)
    assert dict(buttermilk.ratios)[LEMON] == pytest.approx(0.06, abs=0.01)


def test_an_unknown_ingredient_or_unit_is_an_error_not_a_skip(store):
    with pytest.raises(ValueError, match="not a canonical ingredient"):
        resolve_rules(store, [SubstitutionRule("x", "unobtainium", 1, "cup", (("milk", 1, "cup"),))])
    with pytest.raises(ValueError, match="no weight"):
        resolve_rules(store, [SubstitutionRule("x", "buttermilk", 1, "fathom", (("milk", 1, "cup"),))])


# ------------------------------------------------------------------------------------------------ safety
def test_substitutes_must_pass_the_users_hard_rules(store):
    rules = default_rules(store)
    butter = store.ingredient_by_name("butter").ingredient_id
    assert butter in allowed_substitutes(store, UserProfile(), rules)
    assert butter not in allowed_substitutes(store, UserProfile(diet=Diet.VEGAN), rules)        # margarine -> butter
    assert MILK not in allowed_substitutes(store, UserProfile(allergens=frozenset({"dairy"})), rules)
    assert MILK not in allowed_substitutes(store, UserProfile(excluded_ingredient_ids=frozenset({MILK})), rules)
    assert MILK not in allowed_substitutes(store, UserProfile(disliked_ingredient_ids=frozenset({MILK})), rules)


# ------------------------------------------------------------------------------------------------ real dataset
@pytest.fixture(scope="module")
def buttermilk_recipe(catalog) -> int:
    """A real recipe that needs buttermilk and neither milk nor lemon juice."""
    for idx in catalog.recipes_using(BUTTERMILK):
        ids = set(catalog.ingredients(int(idx))[0].tolist())
        if MILK not in ids and LEMON not in ids:
            return int(idx)
    pytest.skip("no suitable buttermilk recipe in this dataset")


def test_replay_with_substitutions_on_a_real_recipe(ctx, buttermilk_recipe):
    sc = Scenario(scenario_id="swap", pantry=[_stock(MILK, 500), _stock(LEMON, 100)], horizon_days=1)
    out = replay_with_substitutions([buttermilk_recipe], sc, ctx, {})
    assert [s.rule_key for s in out.substitutions] == ["buttermilk_milk_lemon"]
    assert BUTTERMILK not in out.report.groceries_g

    allergic = sc.model_copy(update={"profile": UserProfile(allergens=frozenset({"dairy"}))})
    assert replay_with_substitutions([buttermilk_recipe], allergic, ctx, {}).substitutions == ()
