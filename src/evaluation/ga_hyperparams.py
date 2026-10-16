"""Validation-only factorial GA hyperparameter experiment.

Six configurations: mutation 0.10/0.20/0.35 x population 48/96,
350 generations, five paired seeds. Does not alter the production GA defaults.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from evaluation.metrics import evaluate_plan, to_frame
from evaluation.scenarios import DEFAULT_EVAL_DIR, load_split
from evaluation.runner import _stratified_head
from optimizer.genetic import GAConfig, GeneticPlanner
from optimizer.planning import make_context, prepare

METRICS = (
    "waste_g", "avoidable_waste_g", "grocery_items", "grocery_g",
    "pantry_utilisation_pct", "expiring_utilisation_pct",
    "nutrition_in_range_pct", "preference_mean", "violations", "complete",
)
MUTATION_RATES = (0.10, 0.20, 0.35)
POPULATIONS = (48, 96)


def experiment(limit: int = 24, seeds: int = 5, generations: int = 350,
               mutations=MUTATION_RATES, populations=POPULATIONS, ctx=None):
    """Return raw scenario results, seed-level means, summary, and runtime by config."""
    if limit < 1 or not 1 <= seeds <= 20 or generations < 1:
        raise ValueError("invalid scenario limit, seed count, or generation count")
    ctx = ctx or make_context()
    scenarios = _stratified_head(load_split("validation"), limit)
    prepared = {sc.scenario_id: prepare(sc, ctx) for sc in scenarios}
    rows, runtimes = [], []
    for population in populations:
        for mutation in mutations:
            if not 0 <= mutation <= 1 or population < 4:
                raise ValueError("invalid mutation or population")
            config_id = f"ga_p{population}_m{int(round(mutation*100)):02d}"
            for seed in range(seeds):
                config = GAConfig(population=population, generations=generations,
                                  mutation_rate=mutation, seed=seed)
                planner = GeneticPlanner(ctx, config=config)
                # Unique result label avoids accidentally pooling configurations.
                planner.name = f"{config_id}_s{seed}"
                for sc in scenarios:
                    start = time.perf_counter()
                    plan = planner.plan(sc)
                    seconds = time.perf_counter() - start
                    row = evaluate_plan(sc, plan, ctx, prepared[sc.scenario_id])
                    rows.append(row)
                    runtimes.append({
                        "planner": planner.name, "scenario_id": sc.scenario_id,
                        "population": population, "mutation_rate": mutation,
                        "seed": seed, "runtime_s": seconds,
                        "fitness": plan.diagnostics.get("objective", float("nan")),
                    })
    raw = to_frame(rows)
    timing = pd.DataFrame(runtimes)
    raw = raw.merge(timing, on=["planner", "scenario_id"], validate="one_to_one")
    group = ["population", "mutation_rate", "seed"]
    seed_means = raw.groupby(group, as_index=False)[list(METRICS) + ["fitness", "runtime_s"]].mean()
    summary = seed_means.groupby(["population", "mutation_rate"])[
        list(METRICS) + ["fitness", "runtime_s"]
    ].agg(["mean", "std", "min", "max"]).round(4)
    return raw, seed_means, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--generations", type=int, default=350)
    args = parser.parse_args()
    raw, by_seed, summary = experiment(args.limit, args.seeds, args.generations)
    print("\n=== GA hyperparameter experiment: across-seed means ===")
    cols = ["fitness", "waste_g", "grocery_items", "grocery_g",
            "nutrition_in_range_pct", "preference_mean", "runtime_s", "violations"]
    print(by_seed.groupby(["population", "mutation_rate"])[cols].agg(["mean", "std"]).round(3).to_string())
    print("\n=== Complete mean/std/min/max results ===")
    print(summary.to_string())
    out = DEFAULT_EVAL_DIR / "runs"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw.to_csv(out / f"{stamp}_ga_hyperparams_raw.csv", index=False)
    by_seed.to_csv(out / f"{stamp}_ga_hyperparams_by_seed.csv", index=False)
    summary.to_csv(out / f"{stamp}_ga_hyperparams_summary.csv")
    print("\nSaved 3 CSV files to", out)
    print("All runs used the frozen validation split; held-out test was not accessed.")


if __name__ == "__main__":
    main()
