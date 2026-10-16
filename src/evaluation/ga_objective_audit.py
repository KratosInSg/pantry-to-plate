"""Audit GA's replay fitness against the actual MILP objective for the SAME fixed plan.

Run on validation scenarios only. Builds the MILP with its usual shortlist, fixes all
recipe-day x binaries to the GA chromosome, and solves remaining flow/slack variables.
Differences are printed, never silently interpreted as equivalence.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from collections import Counter
from optimizer.inventory import account_inventory, visible_deadlines
from optimizer.weekly import COST_TERMS, DEFAULT_WEIGHTS, _aggregate_pantry, protein_type
from evaluation.scenarios import load_split
from evaluation.runner import build_planner
from optimizer.backends import solve_highs
from optimizer.candidates import shortlist
from optimizer.planning import make_context, prepare
from optimizer.weekly import WeeklyPlanner



def ga_cost_terms(scenario, ctx, chosen, prepared, shortlist_config):
    """Independent decomposition of current GA replay fitness (without rounded diagnostics)."""
    w = DEFAULT_WEIGHTS
    cat, profile = ctx.catalog, scenario.profile
    horizon = scenario.horizon_days
    inv = account_inventory(chosen, scenario.pantry, cat,
                            visible_deadlines(scenario.pantry, horizon), ctx.ignore_ids, horizon)
    stock = _aggregate_pantry(scenario.pantry, set(ctx.ignore_ids), horizon,
                              shortlist_config.urgent_within_days)
    waste = sum(
        max(0., item.grams - inv.consumed_g.get(iid, 0.))
        * (item.urgency_factor if w.urgency_weighting else 1.)
        * (item.confidence if w.confidence_weighting else 1.)
        * w.waste_per_100g / 100.
        for iid, item in stock.items() if item.last_use_day is not None
    )
    groceries = w.grocery_item * inv.n_grocery_items + w.grocery_per_100g * inv.total_groceries_g / 100.
    lo, hi = profile.dinner_kcal_range
    target = profile.dinner_kcal_target
    protein_min = profile.min_protein_g_per_dinner
    nutrition = preference = cook_time = 0.
    cuisines, proteins = Counter(), Counter()
    for day, idx in enumerate(chosen):
        kcal = float(cat.kcal[idx])
        prot = float(cat.protein_g[idx])
        nutrition += (w.kcal_deviation * (max(0., lo-kcal) + max(0., kcal-hi)) / target
                      + w.protein_deviation * max(0., protein_min-prot) / max(protein_min, 1.))
        preference += w.preference * (1.-float(prepared.preference[idx]))
        if scenario.is_weekday(day):
            cook_time += w.weekday_time * max(0., float(cat.minutes[idx])-profile.max_weekday_minutes) / max(1, profile.max_weekday_minutes)
        cuisine = cat.cuisine[idx]
        if cuisine is not None:
            cuisines[cuisine] += 1
        proteins[protein_type(cat, idx)] += 1
    variety = w.variety * (
        sum(max(0, n-w.cuisine_cap) for n in cuisines.values())
        + sum(max(0, n-w.protein_type_cap) for n in proteins.values()))
    return dict(waste=waste, groceries=groceries, nutrition=nutrition,
                preference=preference, cook_time=cook_time, variety=variety)


def milp_cost_terms(result, handles):
    """Read the MILP's real objective coefficient groups at its fixed-plan optimum."""
    return {
        name: sum(coef * float(result.x[var]) for var, coef in handles["terms"].get(name, []))
              + (handles["constant_waste_cost"] if name == "waste" else 0.)
        for name in COST_TERMS
    }


def audit_one(scenario, ctx, ga_name="genetic_35_s0"):
    ga = build_planner(ga_name, ctx)
    plan = ga.plan(scenario)
    if not plan.is_complete:
        return {"scenario": scenario.scenario_id, "status": plan.status}
    prepared = prepare(scenario, ctx)
    milp = WeeklyPlanner(ctx, shortlist_config=ga.shortlist_config)
    candidates = shortlist(ctx.catalog, scenario.profile, scenario.pantry, prepared.feasible,
                           prepared.preference, ctx.ignore_ids, ga.shortlist_config)
    model, handles = milp._build(scenario, candidates, prepared.preference)
    pos = {int(i): k for k, i in enumerate(candidates)}
    chosen = [ctx.catalog.index_of(rid) for rid in plan.recipe_ids]
    for day, idx in enumerate(chosen):
        if idx not in pos:
            raise AssertionError("GA used a recipe outside the MILP shortlist")
        for k in range(len(candidates)):
            variable = int(handles["x"][k, day])
            value = float(k == pos[idx])
            model._lb[variable] = value
            model._ub[variable] = value
    result = solve_highs(model, time_limit_s=30., mip_rel_gap=1e-6)
    if result.x is None:
        return {"scenario": scenario.scenario_id, "status": result.status}
    milp_fixed = result.objective + handles["constant_waste_cost"]
    ga_score = float(plan.diagnostics["objective"])
    ga_terms = ga_cost_terms(scenario, ctx, chosen, prepared, ga.shortlist_config)
    milp_terms = milp_cost_terms(result, handles)
    term_deltas = {name: round(ga_terms[name]-milp_terms[name], 5) for name in COST_TERMS}
    if abs(sum(ga_terms.values())-ga_score) > 0.001:
        raise AssertionError("GA term decomposition does not match GA fitness")
    if abs(sum(milp_terms.values())-milp_fixed) > 0.001:
        raise AssertionError("MILP term decomposition does not match fixed-plan objective")
    return {"scenario": scenario.scenario_id, "status": result.status,
            "ga_fitness": ga_score, "milp_fixed_plan_cost": round(milp_fixed, 4),
            "delta_ga_minus_milp": round(ga_score-milp_fixed, 4),
            "abs_delta": round(abs(ga_score-milp_fixed), 4),
            "ga_terms": {k: round(v, 5) for k, v in ga_terms.items()},
            "milp_terms": {k: round(v, 5) for k, v in milp_terms.items()},
            "term_deltas": term_deltas}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--planner", default="genetic_35_s0")
    args = ap.parse_args()
    ctx = make_context()
    for scenario in load_split("validation")[:args.limit]:
        print(audit_one(scenario, ctx, args.planner))


if __name__ == "__main__":
    main()
