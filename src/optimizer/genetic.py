"""Genetic algorithm baseline for seven-day planning.

Uses the same hard-rule shortlist and weighted cost categories as the MILP.
Fitness uses only planner-visible expiry dates, never hidden benchmark truth.
No optimality guarantee. Deterministic for a fixed scenario and seed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from domain.models import Scenario
from optimizer.candidates import ShortlistConfig, shortlist
from optimizer.inventory import account_inventory, visible_deadlines
from optimizer.planning import PlanningContext, plan_from_indices, prepare
from optimizer.weekly import DEFAULT_WEIGHTS, _aggregate_pantry, protein_type


@dataclass(frozen=True)
class GAConfig:
    population: int = 48
    generations: int = 350
    elite: int = 3
    tournament: int = 3
    mutation_rate: float = 0.20
    seed: int = 42


class GeneticPlanner:
    name = "genetic"

    def __init__(self, ctx: PlanningContext, config: GAConfig = GAConfig(),
                 shortlist_config: ShortlistConfig = ShortlistConfig(size=120)):
        self.ctx, self.config, self.shortlist_config = ctx, config, shortlist_config
        self.name = "genetic" if config == GAConfig() else f"genetic_{config.generations}_s{config.seed}"
        if config.population < 4 or not 1 <= config.elite < config.population or config.generations < 1 or not 0 <= config.mutation_rate <= 1 or config.tournament < 2:
            raise ValueError("invalid genetic algorithm configuration")

    def plan(self, scenario: Scenario):
        ctx, cfg = self.ctx, self.config
        prepared = prepare(scenario, ctx)
        horizon = scenario.horizon_days
        feasible = prepared.feasible_indices
        if len(feasible) < horizon:
            return plan_from_indices(self.name, ctx, feasible.tolist(), horizon, n_feasible=len(feasible))
        candidates = shortlist(ctx.catalog, scenario.profile, scenario.pantry,
                               prepared.feasible, prepared.preference, ctx.ignore_ids, self.shortlist_config)
        cat, profile, w = ctx.catalog, scenario.profile, DEFAULT_WEIGHTS
        rng = np.random.default_rng([cfg.seed, scenario.seed])
        stock = _aggregate_pantry(scenario.pantry, set(ctx.ignore_ids), horizon,
                                  self.shortlist_config.urgent_within_days)
        deadlines = visible_deadlines(scenario.pantry, horizon)
        lo, hi = profile.dinner_kcal_range
        target = profile.dinner_kcal_target
        protein_min = profile.min_protein_g_per_dinner
        info = {}
        for x in candidates:
            i = int(x)
            kcal = float(cat.kcal[i])
            protein = float(cat.protein_g[i])
            nutrition = (w.kcal_deviation * (max(0., lo-kcal)+max(0., kcal-hi))/target
                         + w.protein_deviation * max(0., protein_min-protein)/max(protein_min, 1.))
            preference = w.preference * (1.-float(prepared.preference[i]))
            overtime = w.weekday_time * max(0., float(cat.minutes[i])-profile.max_weekday_minutes)/max(1, profile.max_weekday_minutes)
            info[i] = (nutrition, preference, overtime, cat.cuisine[i], protein_type(cat, i))
        cache = {}

        def fitness(plan):
            key = tuple(int(i) for i in plan)
            if key in cache:
                return cache[key]
            inventory = account_inventory(key, scenario.pantry, cat, deadlines,
                                          ctx.ignore_ids, horizon)
            waste = 0.
            for iid, s in stock.items():
                if s.last_use_day is not None:
                    factor = s.urgency_factor if w.urgency_weighting else 1.
                    confidence = s.confidence if w.confidence_weighting else 1.
                    waste += max(0., s.grams-inventory.consumed_g.get(iid, 0.)) * factor * confidence / 100.
            grocery = w.grocery_item * inventory.n_grocery_items + w.grocery_per_100g * inventory.total_groceries_g/100.
            nutrition = preference = overtime = 0.
            cuisines, proteins = Counter(), Counter()
            for day, idx in enumerate(key):
                n, p, t, cuisine, protein = info[idx]
                nutrition += n
                preference += p
                if scenario.is_weekday(day):
                    overtime += t
                if cuisine is not None:
                    cuisines[cuisine] += 1
                proteins[protein] += 1
            variety = w.variety * (sum(max(0, n-w.cuisine_cap) for n in cuisines.values())
                                   + sum(max(0, n-w.protein_type_cap) for n in proteins.values()))
            score = w.waste_per_100g*waste + grocery + nutrition + preference + overtime + variety
            cache[key] = float(score)
            return float(score)

        def repair(child):
            used = set()
            result = []
            for i in child:
                i = int(i)
                if i in used:
                    i = int(next(x for x in rng.permutation(candidates) if int(x) not in used))
                used.add(i)
                result.append(i)
            return tuple(result)

        population = [tuple(map(int, rng.choice(candidates, size=horizon, replace=False)))
                      for _ in range(cfg.population)]
        best = None
        best_score = float("inf")
        for generation in range(cfg.generations+1):
            ranked = sorted(((fitness(p), p) for p in population), key=lambda pair: pair[0])
            if ranked[0][0] < best_score:
                best_score, best = ranked[0]
            if generation == cfg.generations:
                break
            next_population = [p for _, p in ranked[:cfg.elite]]
            def tournament():
                return min((population[int(j)] for j in rng.integers(len(population), size=cfg.tournament)),
                           key=fitness)
            while len(next_population) < cfg.population:
                a, b = tournament(), tournament()
                start, end = sorted(rng.choice(horizon+1, size=2, replace=False))
                child = list(a[:start] + b[start:end] + a[end:])
                if rng.random() < cfg.mutation_rate:
                    child[int(rng.integers(horizon))] = int(rng.choice(candidates))
                next_population.append(repair(child))
            population = next_population
        return plan_from_indices(self.name, ctx, list(best), horizon,
                                 n_feasible=len(feasible), n_candidates=len(candidates),
                                 objective=round(best_score, 4), fitness_evaluations=len(cache),
                                 generations=cfg.generations, population=cfg.population, seed=cfg.seed)
