"""Tests for ``evaluation/weight_sweep.py``: the pre-declared choice rule and the guard against tuning on test.

No solving happens here: the rule is a pure function of a summary table, which is exactly why it can be tested and why
it can be written down before the numbers are seen.
"""
from __future__ import annotations

import pandas as pd
import pytest

from evaluation.weight_sweep import (GRID, GUARDRAILS, SWEEP_BASE, SweepConfig, choose, guardrail_failures,
                                     liked_cuisine_rate, run_sweep, summarise, weights_for)
from optimizer.weekly import DEFAULT_WEIGHTS

BASE = SweepConfig().name


def _summary(rows: dict[str, dict]) -> pd.DataFrame:
    """Rows keyed by candidate name; unspecified metrics default to the baseline's values."""
    base = dict(preference_mean=0.55, disliked_rate=0.10, liked_cuisine_rate=0.20, waste_g=700.0, grocery_items=13.0,
                nutrition_in_range_pct=57.0, protein_ok_pct=50.0, violations=0.0, complete=1.0,
                preference_x=1.0, nutrition_x=1.0)
    return pd.DataFrame({name: {**base, **vals} for name, vals in rows.items()}).T


def test_grid_is_small_and_contains_the_default():
    assert SweepConfig() in GRID and len(GRID) == 6
    assert all(c.preference >= 1.0 and c.nutrition >= 1.0 for c in GRID)


def test_multipliers_scale_the_starting_weights_and_nothing_else():
    w = weights_for(SweepConfig(preference=3.0, nutrition=2.0))
    assert w.preference == pytest.approx(SWEEP_BASE.preference * 3)
    assert w.kcal_deviation == pytest.approx(SWEEP_BASE.kcal_deviation * 2)
    assert w.protein_deviation == pytest.approx(SWEEP_BASE.protein_deviation * 2)
    assert (w.waste_per_100g, w.grocery_item, w.weekday_time, w.variety) == (
        SWEEP_BASE.waste_per_100g, SWEEP_BASE.grocery_item, SWEEP_BASE.weekday_time, SWEEP_BASE.variety)
    assert weights_for(SweepConfig()) == SWEEP_BASE


def test_the_adopted_default_is_the_candidate_the_recorded_sweep_chose():
    """Pins what was decided: preference x3 of the hand-set start, nothing else moved. If this fails, the default was
    changed without a sweep (or the sweep was redone and the docs not updated)."""
    assert SWEEP_BASE.preference == 1.0
    assert DEFAULT_WEIGHTS == weights_for(SweepConfig(preference=3.0, nutrition=1.0))


def test_multipliers_do_not_compound_when_the_default_has_moved():
    """The bug this guards: x3 of an already-adopted x3 would be x9 and the sweep would stop being reproducible."""
    assert weights_for(SweepConfig(preference=3.0)).preference == pytest.approx(3.0)


def test_liked_cuisine_rate():
    assert liked_cuisine_rate(["italian", "thai", None, "italian"], frozenset({"italian"})) == 0.5
    assert liked_cuisine_rate(["thai"], frozenset()) is None            # no liked cuisine stated: not measurable
    assert liked_cuisine_rate([], frozenset({"italian"})) is None


def test_the_candidate_with_the_largest_visible_effect_that_passes_is_chosen():
    s = _summary({BASE: {}, "a": {"liked_cuisine_rate": 0.35, "preference_x": 3.0},
                  "b": {"liked_cuisine_rate": 0.50, "preference_x": 6.0}})
    assert choose(s, BASE)[0] == "b"


def test_a_candidate_that_breaks_a_guardrail_is_rejected_however_good_it_looks():
    s = _summary({BASE: {}, "greedy": {"liked_cuisine_rate": 0.9, "waste_g": 700 * 1.20},
                  "ok": {"liked_cuisine_rate": 0.3}})
    best, failures = choose(s, BASE)
    assert best == "ok" and failures["greedy"] == ["waste"]


@pytest.mark.parametrize("change, broken", [
    ({"waste_g": 700 * 1.06}, "waste"), ({"grocery_items": 13.6}, "groceries"),
    ({"nutrition_in_range_pct": 53.9}, "nutrition"), ({"disliked_rate": 0.13}, "disliked meals"),
    ({"violations": 0.01}, "violations"), ({"complete": 0.98}, "completeness")])
def test_each_guardrail_trips_just_beyond_its_limit(change, broken):
    s = _summary({BASE: {}, "x": {"liked_cuisine_rate": 0.5, **change}})
    assert guardrail_failures(s, BASE)["x"] == [broken]


def test_each_guardrail_holds_exactly_at_its_limit():
    at_limit = {"waste_g": 700 * 1.05, "grocery_items": 13.5, "nutrition_in_range_pct": 54.0, "disliked_rate": 0.12}
    s = _summary({BASE: {}, "x": {"liked_cuisine_rate": 0.5, **at_limit}})
    assert guardrail_failures(s, BASE)["x"] == []


def test_the_default_is_kept_when_nothing_beats_it():
    s = _summary({BASE: {}, "a": {"liked_cuisine_rate": 0.20, "preference_x": 3.0},       # no improvement
                  "b": {"liked_cuisine_rate": 0.60, "waste_g": 1500.0}})                 # improvement, but fails
    assert choose(s, BASE)[0] == BASE


def test_equal_effect_goes_to_the_smaller_change():
    s = _summary({BASE: {}, "big": {"liked_cuisine_rate": 0.4004, "preference_x": 6.0, "nutrition_x": 2.0},
                  "small": {"liked_cuisine_rate": 0.4001, "preference_x": 3.0}})
    assert choose(s, BASE)[0] == "small"


def test_summarise_averages_per_candidate_and_ignores_scenarios_where_liked_cuisine_is_undefined():
    df = pd.DataFrame([
        dict(config="c", preference_mean=0.5, disliked_rate=0.0, liked_cuisine_rate=0.5, waste_g=100, grocery_items=10,
             nutrition_in_range_pct=50, protein_ok_pct=50, violations=0, complete=1, preference_x=1.0, nutrition_x=1.0),
        dict(config="c", preference_mean=0.7, disliked_rate=0.2, liked_cuisine_rate=None, waste_g=300, grocery_items=14,
             nutrition_in_range_pct=70, protein_ok_pct=70, violations=0, complete=1, preference_x=1.0, nutrition_x=1.0)])
    s = summarise(df).loc["c"]
    assert s["liked_cuisine_rate"] == 0.5 and s["waste_g"] == 200 and s["preference_mean"] == pytest.approx(0.6)


def test_the_test_split_is_refused():
    with pytest.raises(ValueError, match="VALIDATION"):
        run_sweep(split="test")


def test_guardrail_table_documents_every_rule_the_code_checks():
    assert set(GUARDRAILS) == {"waste_g", "grocery_items", "nutrition_in_range_pct", "disliked_rate", "violations",
                               "complete"}
