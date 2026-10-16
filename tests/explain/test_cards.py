"""Evidence-based explanation cards always cover the eight requested factors."""
from domain.models import PantryItem, Scenario
from optimizer.baselines import GreedyIngredientMatchPlanner
from explain.facts import build_facts
from explain.cards import meal_cards
from explain.render import SRC_SUBSTITUTION, render
from optimizer.planning import plan_from_indices


def test_eight_xai_categories_and_sources(ctx):
    sc = Scenario(scenario_id="xai-cards", seed=5)
    plan = GreedyIngredientMatchPlanner(ctx).plan(sc)
    facts = build_facts(sc, plan, ctx)
    cards = meal_cards(facts.days[0], facts)
    assert [c.key for c in cards] == [
        "expiry", "pantry", "preference", "nutrition",
        "groceries", "constraint", "substitution", "cooking_time"]
    assert all(c.icon and c.label and c.detail and c.source for c in cards)
    assert not cards[6].available
    assert "No substitution rule fired" in cards[6].detail
    assert "Passes all" in cards[5].detail


def test_substitution_card_and_sentence_cite_the_fired_rule(ctx):
    buttermilk, milk, lemon = (ctx.store.ingredient_by_name(n).ingredient_id
                               for n in ("buttermilk", "milk", "lemon juice"))
    idx = next(int(i) for i in ctx.catalog.recipes_using(buttermilk)
               if not {milk, lemon} & set(ctx.catalog.ingredients(int(i))[0].tolist()))
    sc = Scenario(scenario_id="xai-swap", horizon_days=1,
                  pantry=[PantryItem(ingredient_id=milk, grams=500), PantryItem(ingredient_id=lemon, grams=100)])
    facts = build_facts(sc, plan_from_indices("manual", ctx, [idx], 1), ctx)
    card = meal_cards(facts.days[0], facts)[6]
    assert card.available and card.source == "substitution rule: buttermilk_milk_lemon"
    assert card.detail.startswith("No buttermilk (") and "milk" in card.detail and "lemon juice" in card.detail
    day = render(facts).section("day:0")
    swaps = [s for s in day.statements if s.source == SRC_SUBSTITUTION]
    assert len(swaps) == 1 and swaps[0].text == card.detail and swaps[0].term == "groceries"
