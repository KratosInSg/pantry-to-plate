"""Evidence-based explanation cards always cover the eight requested factors."""
from domain.models import Scenario
from optimizer.baselines import GreedyIngredientMatchPlanner
from explain.facts import build_facts
from explain.cards import meal_cards


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
    assert "No verified" in cards[6].detail
    assert "Passes all" in cards[5].detail
