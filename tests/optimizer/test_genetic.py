"""Genetic planner integration tests using the real recipe catalogue."""
from domain.models import Diet, Scenario, UserProfile
from optimizer.genetic import GAConfig, GeneticPlanner
from optimizer.hard_rules import count_violations
from evaluation.runner import build_planner


def test_genetic_registered(ctx):
    assert isinstance(build_planner("genetic", ctx), GeneticPlanner)


def test_genetic_deterministic_safe_and_distinct(ctx):
    scenario = Scenario(scenario_id="ga-test", seed=19,
                        profile=UserProfile(diet=Diet.VEGETARIAN, allergens=frozenset({"peanut"})))
    planner = GeneticPlanner(ctx, GAConfig(population=12, generations=3))
    a = planner.plan(scenario)
    b = planner.plan(scenario)
    assert a.recipe_ids == b.recipe_ids
    assert a.status == "ok"
    assert len(a.recipe_ids) == scenario.horizon_days
    assert len(set(a.recipe_ids)) == scenario.horizon_days
    indices = [ctx.catalog.index_of(rid) for rid in a.recipe_ids]
    assert count_violations(ctx.catalog, scenario.profile, indices) == 0
    assert a.diagnostics["fitness_evaluations"] > 0


def test_genetic_infeasible(ctx):
    scenario = Scenario(scenario_id="ga-none", profile=UserProfile(max_total_minutes=4))
    plan = GeneticPlanner(ctx, GAConfig(population=8, generations=2)).plan(scenario)
    assert plan.recipe_ids == []
    assert plan.status == "no_candidates"


def test_generation_budget_and_seed_variants(ctx):
    from evaluation.runner import build_planner
    short = build_planner("genetic_35_s1", ctx)
    long = build_planner("genetic_350_s1", ctx)
    assert short.config.generations == 35 and long.config.generations == 350
    assert short.config.seed == long.config.seed == 1
    assert short.name != long.name
    with pytest.raises(ValueError):
        build_planner("genetic_999_s1", ctx)


def test_more_generations_do_not_worsen_best_fitness(ctx):
    from evaluation.runner import build_planner
    scenario = Scenario(scenario_id="budget-test", seed=20261012)
    a = build_planner("genetic_35_s1", ctx).plan(scenario)
    b = build_planner("genetic_350_s1", ctx).plan(scenario)
    assert b.diagnostics["objective"] <= a.diagnostics["objective"] + 1e-4
