"""Tests for ``explain/render.py``: every sentence is traceable, shortfalls are stated as shortfalls, nothing is claimed
that the facts do not support."""
from __future__ import annotations

import re

import numpy as np
import pytest

from domain.models import Diet, PantryItem, Scenario, UserProfile
from explain.facts import build_facts
from explain.paraphrase import CLAIM_WORDS
from explain.render import (SRC_COST_TERM, SRC_INPUT, SRC_PROFILE, SRC_REPLAY, SRC_RULE, SRC_SUBSTITUTION,
                            TERM_LABELS, fmt_g, render, _listed)
from optimizer.baselines import RandomFeasiblePlanner
from optimizer.planning import plan_from_indices

SOURCES = {SRC_REPLAY, SRC_COST_TERM, SRC_RULE, SRC_PROFILE, SRC_INPUT, SRC_SUBSTITUTION}
TERMS = {"waste", "groceries", "nutrition", "preference", "cook_time", "variety", "overview", "rule", "solver", "data"}


def _explain(ctx, scenario, indices):
    return render(build_facts(scenario, plan_from_indices("manual", ctx, list(indices), 7), ctx))


def _text(explanation) -> str:
    return explanation.to_text()


# --------------------------------------------------------------------------------------------- traceability
def test_every_statement_names_a_known_term_and_source(ctx, optimised_week):
    scenario, plan = optimised_week
    explanation = render(build_facts(scenario, plan, ctx))
    statements = [st for section in explanation.sections for st in section.statements]
    assert len(statements) > 10
    assert all(st.term in TERMS and st.source in SOURCES for st in statements)
    assert all(st.text.strip() and st.text.endswith((".", ")")) for st in statements)


def test_section_text_is_exactly_its_statements_before_any_paraphrase(ctx, optimised_week):
    scenario, plan = optimised_week
    for section in render(build_facts(scenario, plan, ctx)).sections:
        assert section.text == section.template_text and section.source == "template" and section.note == ""


def test_sections_come_in_a_stable_order(ctx, optimised_week):
    scenario, plan = optimised_week
    keys = [s.key for s in render(build_facts(scenario, plan, ctx)).sections]
    assert keys[0] == "overview"
    assert keys[1:8] == [f"day:{d}" for d in range(7)]
    assert keys[8:] in (["rules", "caveats"], ["rules"], ["caveats"], [])      # optional, always in this order


def test_solver_cost_term_sentences_only_exist_for_plans_that_have_cost_terms(ctx, optimised_week):
    scenario, plan = optimised_week
    with_terms = render(build_facts(scenario, plan, ctx)).section("overview")
    assert any(st.source == SRC_COST_TERM for st in with_terms.statements)
    baseline = RandomFeasiblePlanner(ctx).plan(Scenario(scenario_id="t"))
    without = render(build_facts(Scenario(scenario_id="t"), baseline, ctx)).section("overview")
    assert not any(st.source == SRC_COST_TERM for st in without.statements)


def test_the_largest_cost_term_is_the_one_named_first(ctx, optimised_week):
    scenario, plan = optimised_week
    facts = build_facts(scenario, plan, ctx)
    top = max(facts.solver.terms, key=facts.solver.terms.get)
    sentence = next(st.text for st in render(facts).section("overview").statements if "costs this plan" in st.text)
    assert sentence.index(TERM_LABELS[top]) == min(
        sentence.index(label) for t, label in TERM_LABELS.items() if label in sentence)


# --------------------------------------------------------------------------------------------- honesty
def test_shortfalls_are_stated_as_shortfalls(ctx):
    cat = ctx.catalog
    idx = int(np.flatnonzero((cat.kcal > 400) & (cat.kcal < 800) & (cat.minutes >= 40))[0])
    kcal, protein, minutes = float(cat.kcal[idx]), float(cat.protein_g[idx]), int(cat.minutes[idx])
    # a user whose band sits far above the recipe, wanting more protein, in less time
    profile = UserProfile(daily_kcal_target=kcal * 2 / 0.30, min_protein_g_per_dinner=protein + 15,
                          max_weekday_minutes=minutes - 15)
    text = _text(_explain(ctx, Scenario(scenario_id="t", profile=profile), [idx]))
    assert "below your dinner range" in text
    assert "short of your" in text
    assert "15 min longer than your" in text
    assert "inside your dinner range" not in text and "meets your" not in text and "fits your" not in text


def test_a_small_shortfall_never_prints_as_zero(ctx):
    """Regression (found by the live paraphrase check, 2026-10-13): 17.6 g protein against an 18 g minimum rendered as
    "18 g protein is 0 g short of your 18 g minimum" - a shortfall that says it is none."""
    cat = ctx.catalog
    idx = int(np.flatnonzero((cat.kcal > 400) & (cat.kcal < 800))[0])
    kcal, protein = float(cat.kcal[idx]), float(cat.protein_g[idx])
    band_low = kcal + 0.3                                               # the dinner is 0.3 kcal under the band
    profile = UserProfile(daily_kcal_target=band_low / (0.30 * 0.80), min_protein_g_per_dinner=protein + 0.4)
    text = _explain(ctx, Scenario(scenario_id="t", profile=profile), [idx]).section("day:0").text
    assert "0.4 g short of your" in text
    assert "0.3 kcal below your dinner range" in text
    assert " 0 g short" not in text and " 0 kcal below" not in text


def test_float_noise_is_not_reported_as_a_miss(ctx):
    cat = ctx.catalog
    idx = int(np.flatnonzero((cat.kcal > 400) & (cat.kcal < 800))[0])
    protein = float(cat.protein_g[idx])
    profile = UserProfile(daily_kcal_target=float(cat.kcal[idx]) / 0.30, min_protein_g_per_dinner=protein + 0.01)
    text = _explain(ctx, Scenario(scenario_id="t", profile=profile), [idx]).section("day:0").text
    assert "meets your" in text and "short of" not in text


def test_a_dinner_inside_the_band_says_so(ctx):
    cat = ctx.catalog
    idx = int(np.flatnonzero((cat.kcal > 400) & (cat.kcal < 800))[0])
    profile = UserProfile(daily_kcal_target=float(cat.kcal[idx]) / 0.30, min_protein_g_per_dinner=0)
    day = _explain(ctx, Scenario(scenario_id="t", profile=profile), [idx]).section("day:0")
    assert "sits inside your dinner range" in day.text and "protein" in day.text.split("sits inside")[0]
    assert "minimum" not in day.text                     # no protein sentence when the user set no minimum


def test_unused_expiring_stock_is_named_with_its_deadline(ctx):
    spinach = int(ctx.store.ingredient_by_name("spinach").ingredient_id)
    pantry = [PantryItem(ingredient_id=spinach, grams=400, last_use_day=1, expiry_known=False, expiry_confidence=0.5)]
    explanation = _explain(ctx, Scenario(scenario_id="t", pantry=pantry), [500, 501, 502, 503, 504, 505, 506])
    overview = explanation.section("overview").text
    assert "400 g of the 400 g of pantry stock that expires this week will still go unused" in overview
    assert "400 g spinach (use by Tuesday, estimated)" in overview
    assert "estimate" in explanation.section("caveats").text


def test_stranded_stock_is_explained_not_left_as_a_mystery(ctx):
    ids, grams = ctx.catalog.ingredients(500)
    pantry = [PantryItem(ingredient_id=int(i), grams=float(g) * 100, last_use_day=0, expiry_known=True)
              for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids and g > 1]
    explanation = _explain(ctx, Scenario(scenario_id="t", pantry=pantry), [501, 502, 503, 500, 504, 505, 506])
    overview = explanation.section("overview").text
    several = len(build_facts(Scenario(scenario_id="t", pantry=pantry),
                              plan_from_indices("manual", ctx, [501, 502, 503, 500, 504, 505, 506], 7), ctx).stranded)
    assert several > 1, "this fixture strands several ingredients, so the plural wording is what is under test"
    assert "they expire before the dinner that needs them, so the plan buys them again" in overview


def test_grammar_agrees_with_the_count(ctx):
    """One dinner in range / one stranded ingredient read as singular (found reading a real explanation)."""
    cat = ctx.catalog
    idx = int(np.flatnonzero((cat.kcal > 400) & (cat.kcal < 800))[0])
    profile = UserProfile(daily_kcal_target=float(cat.kcal[idx]) / 0.30, min_protein_g_per_dinner=0)
    text = _explain(ctx, Scenario(scenario_id="t", profile=profile), [idx]).section("overview").text
    assert "1 of 1 dinners is inside your calorie range" in text and "0 of 1 dinners are" not in text
    # exactly one owned ingredient, plentiful but expired by the time recipe 500 is cooked on day 3
    food = next(int(i) for i in cat.ingredients(500)[0] if int(i) not in ctx.ignore_ids)
    pantry = [PantryItem(ingredient_id=food, grams=5000, last_use_day=0, expiry_known=True)]
    text = _explain(ctx, Scenario(scenario_id="t", pantry=pantry), [501, 502, 503, 500, 504, 505, 506]) \
        .section("overview").text
    assert "but it expires before the dinner that needs it, so the plan buys it again" in text


def test_rules_section_states_counts_and_the_safety_verdict(ctx):
    profile = UserProfile(diet=Diet.VEGAN, allergens=frozenset({"tree_nut"}))
    from optimizer.hard_rules import feasible_mask
    ok = np.flatnonzero(feasible_mask(ctx.catalog, profile))[:7]
    text = _explain(ctx, Scenario(scenario_id="t", profile=profile), ok).section("rules").text
    assert "not compatible with your vegan diet" in text
    assert "contain tree nut, which is on your allergy list" in text
    assert "All 7 planned dinners pass every one of these rules" in text
    assert "hidden ingredients inside packaged foods" in text           # the honest limit of allergen checks


def test_a_violating_plan_is_flagged_loudly(ctx):
    meat = int(np.flatnonzero(ctx.catalog.flag("contains_meat"))[0])
    text = _explain(ctx, Scenario(scenario_id="t", profile=UserProfile(diet=Diet.VEGAN)), [meat]).section("rules").text
    assert "WARNING" in text and "do not cook from this plan" in text


def test_an_impossible_request_explains_why_there_is_no_plan(ctx):
    explanation = _explain(ctx, Scenario(scenario_id="t", profile=UserProfile(max_total_minutes=1)), [])
    overview = explanation.section("overview").text
    assert "passes all of your rules" in overview
    assert f"{ctx.catalog.n:,} dinners were removed because they take longer than your maximum cooking time" \
        in explanation.section("rules").text
    assert explanation.section("day:0") is None


def test_templates_never_make_health_or_taste_claims(ctx, optimised_week):
    scenario, plan = optimised_week
    text = _text(render(build_facts(scenario, plan, ctx))).lower()
    words = set(re.findall(r"[a-z]+", text))
    assert not words & (CLAIM_WORDS - {"best"})
    # "best" is allowed in exactly one place: the solver's proven gap ("within 2% of the best possible one")
    assert all(m.group(0).startswith("best possible") for m in re.finditer(r"best \w+", text))


# --------------------------------------------------------------------------------------------- formatting
@pytest.mark.parametrize("grams, text", [(300, "300 g"), (12.4, "12 g"), (3.5, "3.5 g"), (2.0, "2 g"),
                                         (1234, "1.2 kg"), (1000, "1 kg"), (0.4, "0.4 g")])
def test_fmt_g(grams, text):
    assert fmt_g(grams) == text


def test_lists_never_contain_two_ands():
    assert _listed(["a", "b", "c"], 3) == "a, b and c"
    assert _listed(["a", "b", "c"], 5) == "a, b, c and 2 more"
    assert _listed(["a"], 1) == "a"
    assert _listed([], 0) == ""


def test_assumed_quantities_are_flagged_in_the_caveats(ctx):
    spinach = int(ctx.store.ingredient_by_name("spinach").ingredient_id)
    pantry = [PantryItem(ingredient_id=spinach, grams=250, quantity_assumed=True)]
    caveats = _explain(ctx, Scenario(scenario_id="t", pantry=pantry), [500, 501, 502, 503, 504, 505, 506]) \
        .section("caveats").text
    assert "we assumed 250 g spinach" in caveats and "Please correct these if they are wrong" in caveats
