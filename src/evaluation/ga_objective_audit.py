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
from evaluation.scenarios import load_split
from evaluation.runner import build_planner
from optimizer.backends import solve_highs
from optimizer.candidates import shortlist
from optimizer.planning import make_context, prepare
from optimizer.weekly import WeeklyPlanner


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
    return {"scenario": scenario.scenario_id, "status": result.status,
            "ga_fitness": ga_score, "milp_fixed_plan_cost": round(milp_fixed, 4),
            "delta_ga_minus_milp": round(ga_score-milp_fixed, 4),
            "abs_delta": round(abs(ga_score-milp_fixed), 4)}


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
