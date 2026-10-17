"""Tests for ``app/service.py``: the facade a UI calls. Real dataset, real optimiser (small shortlist for speed).

These are the flows the prototype needs: free text -> review -> fix -> profile -> plan -> reasons -> grocery box ->
re-plan. They assert behaviour a user would notice, and that everything shown agrees with the inventory replay.
"""
from __future__ import annotations

import logging
from datetime import date

import pytest

from app.models import (ENTRY_ASSUMED, ENTRY_CHOOSE, ENTRY_NO_AMOUNT, ENTRY_OK, ENTRY_UNKNOWN, PantryEntry,
                        PlannedWeek)
from app.service import MAX_FOOD_NAMES, MAX_PANTRY_CHARS, PantryToPlateService
from domain.models import Diet, PantryItem, UserProfile
from nlp.schemas import Urgency
from optimizer.hard_rules import count_violations

TODAY = date(2026, 10, 14)                      # a Wednesday
TEXT = ("half a bag of spinach going off, 500g chicken breast, 6 eggs, leftover rice, a tub of kimchi, "
        "2 lbs potatoes, milk expires tomorrow, flour")


@pytest.fixture(scope="module")
def service(ctx) -> PantryToPlateService:
    return PantryToPlateService(ctx, shortlist_size=60, time_limit_s=10.0)


@pytest.fixture(scope="module")
def review(service):
    return service.review_pantry(TEXT, today=TODAY)


@pytest.fixture(scope="module")
def week(service, review) -> PlannedWeek:
    profile = service.build_profile(liked_cuisines=["italian"]).profile
    scenario = service.make_scenario(profile, service.pantry_items(review.entries), today=TODAY)
    return service.plan_week(scenario)


# --------------------------------------------------------------------------------------------- vocabulary
def test_cuisines_are_sorted_known_names(service):
    c = service.cuisines()
    assert c == sorted(c) and "italian" in c and "mexican" in c and len(c) > 20


def test_ingredient_search_ranks_prefix_matches_first_and_tolerates_typos(service):
    assert service.search_ingredients("spinac")[0].name == "spinach"
    assert "chicken" in [c.name for c in service.search_ingredients("chiken")]
    assert service.search_ingredients("x") == []                       # too short to mean anything
    ids = [c.ingredient_id for c in service.search_ingredients("pepper", limit=5)]
    assert len(ids) == len(set(ids)) <= 5


def test_resolve_names_separates_matched_ambiguous_and_unknown(service):
    res = service.resolve_names(["basil", "kimchi", "qzxqzx"])
    assert "basil" in res.ids
    assert "kimchi" in res.ambiguous and any("kimchi" in c.name for c in res.ambiguous["kimchi"])
    assert "qzxqzx" in res.unresolved


# --------------------------------------------------------------------------------------------- the profile
def test_build_profile_maps_names_to_ids_and_enables_dinner_only(service):
    pb = service.build_profile(diet="Vegetarian", allergens=["Peanut", "tree nut"], liked_cuisines=["Italian"],
                               liked_foods=["basil"], disliked_foods=["cilantro"], excluded_foods=["qzxqzx"])
    p = pb.profile
    assert p.diet is Diet.VEGETARIAN and p.allergens == frozenset({"peanut", "tree_nut"})
    assert p.liked_cuisines == frozenset({"italian"}) and p.dinner_only
    assert len(p.liked_ingredient_ids) == 1 and len(p.disliked_ingredient_ids) == 1
    assert p.excluded_ingredient_ids == frozenset()                    # unresolved: left out, never guessed
    assert any("qzxqzx" in n for n in pb.notes)


@pytest.mark.parametrize("kwargs, message", [({"diet": "carnivore"}, "unknown diet"),
                                              ({"allergens": ["kryptonite"]}, "unknown allergen"),
                                              ({"liked_cuisines": ["atlantean"]}, "unknown cuisine")])
def test_build_profile_rejects_unknown_choices_with_the_valid_options(service, kwargs, message):
    with pytest.raises(ValueError, match=message):
        service.build_profile(**kwargs)


def test_build_profile_propagates_numeric_validation(service):
    with pytest.raises(ValueError):
        service.build_profile(daily_kcal_target=100)                   # below the model's allowed range


# --------------------------------------------------------------------------------------------- pantry review
def test_review_turns_text_into_rows_with_honest_statuses(review):
    by_name = {e.name: e for e in review.entries if e.name}
    assert by_name["chicken breast"].status == ENTRY_OK and by_name["chicken breast"].grams == 500
    assert not by_name["chicken breast"].quantity_assumed
    assert by_name["spinach"].status == ENTRY_ASSUMED and by_name["spinach"].quantity_assumed
    assert by_name["spinach"].urgency is Urgency.URGENT and by_name["spinach"].last_use_day is not None
    assert by_name["potato"].grams == pytest.approx(907.2, abs=0.1)     # 2 lb, stated
    assert by_name["milk"].expiry_known                                  # "expires tomorrow" is a stated date


def test_rows_carry_their_food_group_for_the_icon(service, review):
    by_name = {e.name: e for e in review.entries if e.name}
    assert by_name["spinach"].food_group == "vegetable" and by_name["chicken breast"].food_group == "poultry"
    assert all(e.food_group is None for e in review.needs_attention if e.ingredient_id is None)
    row = review.needs_attention[0]
    picked = service.choose_ingredient(row, row.suggestions[0].ingredient_id)
    assert picked.food_group is not None                                  # set once the user picks an ingredient
    rice = service.search_ingredients("rice")[0].ingredient_id
    assert service.add_pantry_entry(rice, 200).food_group == "grain_pasta"


def test_unrecognised_items_need_attention_and_come_with_suggestions(review):
    bad = review.needs_attention
    assert [e.raw_text for e in bad] == ["a tub of kimchi"]
    e = bad[0]
    assert e.status == ENTRY_UNKNOWN and not e.usable and e.problem
    assert any("kimchi" in s.name for s in e.suggestions)


def test_choosing_a_suggestion_makes_the_row_usable_and_keeps_the_amount(service, review):
    row = review.needs_attention[0]
    pick = next(s for s in row.suggestions if "kimchi" in s.name)
    fixed = service.choose_ingredient(row, pick.ingredient_id)
    assert fixed.usable and fixed.name == pick.name and fixed.grams == row.grams
    assert fixed.raw_text == row.raw_text and fixed.status in (ENTRY_OK, ENTRY_ASSUMED)


def test_editing_the_amount_clears_the_assumption(review):
    spinach = next(e for e in review.entries if e.name == "spinach")
    fixed = spinach.with_grams(120)
    assert fixed.grams == 120 and not fixed.quantity_assumed and fixed.status == ENTRY_OK
    with pytest.raises(ValueError):
        spinach.with_grams(0)


def test_a_stated_use_by_becomes_a_known_hard_deadline(review):
    rice = next(e for e in review.entries if e.name == "rice")
    fixed = rice.with_days_left(2)
    assert fixed.last_use_day == 2 and fixed.expiry_known and fixed.expiry_confidence == 1.0
    assert rice.with_days_left(None).last_use_day is None and rice.with_days_left(30).last_use_day is None
    with pytest.raises(ValueError):
        rice.with_days_left(-1)


def test_a_row_added_by_hand_uses_the_estimate_unless_a_date_is_given(service):
    spinach = service.search_ingredients("spinach")[0].ingredient_id
    estimated = service.add_pantry_entry(spinach, 200)
    stated = service.add_pantry_entry(spinach, 200, days_left=1, urgent=True)
    assert estimated.usable and not estimated.expiry_known and estimated.expiry_confidence < 1
    assert stated.expiry_known and stated.last_use_day == 1 and stated.urgency is Urgency.URGENT
    with pytest.raises(ValueError):
        service.add_pantry_entry(spinach, -5)


def test_pantry_items_keeps_usable_rows_only_and_merges_duplicates(service):
    spinach = service.search_ingredients("spinach")[0].ingredient_id
    rows = [service.add_pantry_entry(spinach, 100, days_left=3), service.add_pantry_entry(spinach, 150, days_left=1),
            PantryEntry(raw_text="mystery", status=ENTRY_UNKNOWN, grams=50)]
    items = service.pantry_items(rows)
    assert len(items) == 1
    assert items[0].grams == 250 and items[0].last_use_day == 1        # grams add, earliest deadline wins


def test_pantry_items_carry_the_assumption_flag_to_the_planner(service, review):
    items = {i.ingredient_id: i for i in service.pantry_items(review.entries)}
    spinach_id = next(e.ingredient_id for e in review.entries if e.name == "spinach")
    chicken_id = next(e.ingredient_id for e in review.entries if e.name == "chicken breast")
    assert items[spinach_id].quantity_assumed and not items[chicken_id].quantity_assumed


def test_garbage_text_does_not_raise(service):
    r = service.review_pantry("!!! ??? 12345", today=TODAY)
    assert r.usable_entries == []


def test_oversized_pantry_text_is_refused_not_truncated(service):
    # security review: a 57 KB text took 22 s of shared server time; refusing (not truncating) drops nothing silently
    assert service.review_pantry("6 eggs, " * (MAX_PANTRY_CHARS // 8), today=TODAY).entries     # at the limit: fine
    with pytest.raises(ValueError, match="under"):
        service.review_pantry("x" * (MAX_PANTRY_CHARS + 1), today=TODAY)


def test_too_many_food_names_are_refused(service):
    # 3,000 names took 42 s; empty names do not count
    assert service.resolve_names(["basil"] * MAX_FOOD_NAMES + ["", "  "]).ids == {"basil": service.resolve_names(
        ["basil"]).ids["basil"]}
    with pytest.raises(ValueError, match="at most"):
        service.build_profile(liked_foods=[f"food{i}" for i in range(MAX_FOOD_NAMES + 1)])


def test_autocomplete_tolerates_a_huge_query(service):
    assert service.search_ingredients("spinach" + "x" * 100_000) == service.search_ingredients(
        ("spinach" + "x" * 100_000)[:100])


# --------------------------------------------------------------------------------------------- planning
def test_a_week_is_planned_complete_safe_and_dinner_only(ctx, week):
    assert week.complete and week.status in ("optimal", "feasible") and len(week.days) == 7
    assert [d.weekday for d in week.days][:2] == ["Wednesday", "Thursday"]
    idx = [ctx.catalog.index_of(d.recipe_id) for d in week.days]
    assert count_violations(ctx.catalog, week.scenario.profile, idx) == 0
    assert not ctx.catalog.non_dinner_like[idx].any()


def test_every_day_carries_what_a_ui_needs_to_show_it(week):
    for d in week.days:
        assert d.name and d.minutes > 0 and d.kcal > 0
        assert d.steps and all(s[0].isupper() for s in d.steps)
        assert d.ingredients and d.explanation is not None and d.explanation.text
        for line in d.ingredients:
            assert line.from_pantry_g + line.to_buy_g <= line.grams + 0.01
            assert line.staple or abs(line.from_pantry_g + line.to_buy_g - line.grams) < 0.01


def test_pantry_use_by_deadline_is_shown_for_stock_that_has_one(week):
    uses = [l for d in week.days for l in d.ingredients if l.from_pantry_g > 0 and l.use_by_day is not None]
    assert uses, "the scenario has perishable stock, so some dinner must use stock that has a deadline"
    assert all(0 <= l.use_by_day < 7 for l in uses)


def test_the_grocery_box_is_the_sum_of_what_each_dinner_needs_to_buy(week):
    per_day: dict[str, float] = {}
    for d in week.days:
        for line in d.ingredients:
            if line.to_buy_g > 0:
                per_day[line.name] = per_day.get(line.name, 0.0) + line.to_buy_g
    assert {i.name: i.grams for i in week.grocery_box.items} == pytest.approx(per_day)
    assert all(0 <= i.first_needed_day < 7 for i in week.grocery_box.items)


def test_the_explanation_is_attached_and_traceable(week):
    assert week.overview.text and week.overview.key == "overview"
    assert week.explanation.facts.violations == 0
    assert week.rules is not None                                     # dinner_only is an active rule, so it is stated
    assert "breakfast dishes, doughs or batters" in week.rules.text


def test_assumed_quantities_are_reported_to_the_user(week):
    assert week.caveats is not None and "we assumed" in week.caveats.text


def test_a_vegetarian_user_gets_no_meat_even_with_chicken_in_the_pantry(service, review, ctx):
    profile = service.build_profile(diet="vegetarian").profile
    scenario = service.make_scenario(profile, service.pantry_items(review.entries), today=TODAY)
    w = service.plan_week(scenario)
    assert w.complete
    idx = [ctx.catalog.index_of(r) for r in w.recipe_ids]
    assert not ctx.catalog.flag("contains_meat")[idx].any() and not ctx.catalog.flag("contains_poultry")[idx].any()
    # ...and the unusable chicken is stated, not silently ignored
    assert "chicken breast" in w.overview.text


# --------------------------------------------------------------------------------------------- re-planning
def test_rejecting_a_dinner_replans_without_it_and_keeps_the_rest_coherent(service, week):
    rejected = week.days[2].recipe_id
    again = service.replan(week, cooked=[], rejected=[rejected])
    assert again.complete and len(again.days) == 7 and again.day_offset == 0
    assert rejected not in again.recipe_ids
    assert rejected in again.scenario.profile.excluded_recipe_ids      # carried, so later re-plans keep honouring it
    assert "dinners you rejected" in again.rules.text


def test_cooked_and_skipped_days_roll_forward_the_pantry_and_the_calendar(service, week):
    first = week.days[0].recipe_id
    rest = service.replan(week, cooked=[first, None])
    assert len(rest.days) == 5 and rest.day_offset == 2
    assert [d.weekday for d in rest.days][0] == "Friday"                # Wednesday + 2
    assert rest.scenario.horizon_days == 5 and rest.scenario.start_weekday == (TODAY.weekday() + 2) % 7
    # stock that went off while two days passed is reported by name, and is gone from the new pantry
    gone = set(rest.expired)
    names_now = {service.ctx.store.ingredient(p.ingredient_id).canonical_name for p in rest.scenario.pantry}
    assert gone.isdisjoint(names_now)


def test_replanning_twice_accumulates_the_offset_and_the_rejections(service, week):
    a = service.replan(week, cooked=[week.days[0].recipe_id], rejected=[week.days[3].recipe_id])
    b = service.replan(a, cooked=[a.days[0].recipe_id], rejected=[a.days[2].recipe_id])
    assert b.day_offset == 2 and len(b.days) == 5
    assert {week.days[3].recipe_id, a.days[2].recipe_id} <= b.scenario.profile.excluded_recipe_ids


def test_replanning_never_modifies_the_week_it_started_from(service, week):
    before = week.scenario.model_dump()
    service.replan(week, cooked=[week.days[0].recipe_id], rejected=[week.days[1].recipe_id])
    assert week.scenario.model_dump() == before and len(week.days) == 7


def test_nothing_left_to_replan_is_a_clear_error(service, week):
    with pytest.raises(ValueError, match="nothing left to plan"):
        service.replan(week, cooked=[d.recipe_id for d in week.days])


# --------------------------------------------------------------------------------------------- LLM is optional
class _StubLlm:
    """Echoes the facts it is shown, so every section is accepted."""

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def complete_text(self, messages, max_tokens=None):
        self.calls += 1
        return " ".join(line[2:] for line in messages[-1]["content"].splitlines() if line.startswith("- "))

    def complete_json(self, messages, schema):                           # pantry re-read: never needed here
        return {"items": []}


def test_each_step_logs_one_info_line_that_names_its_outcome(service, caplog):
    # the INFO log is the developer's timeline of a session: one line per step, not one per fragment or variable
    with caplog.at_level(logging.INFO, logger="app.service"):
        review = service.review_pantry("500g chicken breast, 6 eggs, 2 lbs potatoes", today=TODAY)
        profile = service.build_profile().profile
        service.plan_week(service.make_scenario(profile, service.pantry_items(review.entries), today=TODAY))
    messages = [r.getMessage() for r in caplog.records if r.name == "app.service" and r.levelno == logging.INFO]
    assert any(m.startswith("pantry reviewed in ") and "3 row(s)" in m for m in messages)
    assert any(m.startswith("planning 7 day(s) from 3 pantry item(s)") for m in messages)
    assert any(m.startswith("plan ") and "of 7 dinner(s)" in m for m in messages)
    assert not any("chicken" in m for m in messages)          # the user's own text is DEBUG only


def test_without_an_llm_everything_works_and_nothing_is_reworded(service, week):
    assert not service.llm_available()
    assert service.reword(week) is week
    assert all(s.source == "template" for s in week.explanation.sections)


def test_reword_uses_the_llm_only_for_overview_and_days(ctx, week):
    stub = _StubLlm()
    svc = PantryToPlateService(ctx, llm=stub, shortlist_size=60)
    assert svc.llm_available()
    out = svc.reword(week)
    by_key = {s.key: s for s in out.explanation.sections}
    assert by_key["overview"].source == "llm" and all(by_key[f"day:{d}"].source == "llm" for d in range(7))
    assert all(s.source == "template" for k, s in by_key.items() if k in ("rules", "caveats"))
    assert all(d.explanation.source == "llm" for d in out.days)         # the per-day view sees the reworded text
    assert out.plan == week.plan and out.recipe_ids == week.recipe_ids  # the plan itself is untouched


def test_a_substitution_shows_on_the_ingredient_line_and_leaves_the_grocery_box(service, ctx):
    from optimizer.planning import plan_from_indices
    buttermilk, milk, lemon = (ctx.store.ingredient_by_name(n).ingredient_id
                               for n in ("buttermilk", "milk", "lemon juice"))
    idx = next(int(i) for i in ctx.catalog.recipes_using(buttermilk)
               if not {milk, lemon} & set(ctx.catalog.ingredients(int(i))[0].tolist()))
    scenario = service.make_scenario(UserProfile(), [PantryItem(ingredient_id=milk, grams=500),
                                                     PantryItem(ingredient_id=lemon, grams=100)],
                                     today=TODAY, horizon_days=1)
    # _present is the presentation step plan_week runs after the solver; a hand-made plan pins the recipe
    week = service._present(scenario, plan_from_indices("manual", ctx, [idx], 1), paraphrase=False)
    line = next(l for l in week.days[0].ingredients if l.name == "buttermilk")
    assert line.to_buy_g == 0 and line.substituted_by.startswith("milk (") and "lemon juice" in line.substituted_by
    assert "buttermilk" not in {i.name for i in week.grocery_box.items}
    assert week.explanation.facts.days[0].substitutions[0].rule_key == "buttermilk_milk_lemon"


# --------------------------------------------------------------------------------------------- rating history
def test_rate_dinner_describes_a_catalogue_recipe_in_our_vocabulary(service, week):
    rid = week.days[0].recipe_id
    rated = service.rate_dinner(rid, 4)
    idx = service.ctx.catalog.index_of(rid)
    assert (rated.recipe_id, rated.rating, rated.name) == (rid, 4, week.days[0].name)
    assert rated.ingredient_ids == {int(i) for i in service.ctx.catalog.ingredients(idx)[0]}
    assert rated.tags == set(service.ctx.catalog.tags[idx])
    with pytest.raises(ValueError, match="unknown recipe"):
        service.rate_dinner(-1)
    with pytest.raises(ValueError):
        service.rate_dinner(rid, 6)


def test_build_profile_carries_rated_dinners_and_keeps_the_latest_rating(service, week):
    rid = week.days[0].recipe_id
    built = service.build_profile(rated_dinners=[service.rate_dinner(rid, 2), service.rate_dinner(rid, 5)])
    assert [(d.recipe_id, d.rating) for d in built.profile.rated_dinners] == [(rid, 5)]


def test_a_loved_dinner_becomes_rating_evidence_for_the_rest_of_the_week(service, week):
    first = week.days[0].recipe_id
    again = service.replan(week, cooked=[first], loved=[first])
    assert [d.recipe_id for d in again.scenario.profile.rated_dinners] == [first]
    assert all(d.rating == 5 for d in again.scenario.profile.rated_dinners)
    assert week.scenario.profile.rated_dinners == ()                     # the original week is not modified
    later = service.replan(again, cooked=[again.days[0].recipe_id])        # carried through later re-plans
    assert [d.recipe_id for d in later.scenario.profile.rated_dinners] == [first]
