"""Repeat GA with five seeds at 35 and 350 generations on the same validation scenarios.

Saves raw paired observations and across-seed summaries, including standard deviation.
Do not use held-out test data for choosing GA hyperparameters.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime
import pandas as pd
from evaluation.runner import run, KEY_METRICS
from evaluation.scenarios import DEFAULT_EVAL_DIR

METRICS = ["waste_g", "avoidable_waste_g", "grocery_items", "grocery_g",
           "pantry_utilisation_pct", "expiring_utilisation_pct",
           "nutrition_in_range_pct", "preference_mean", "violations", "complete"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--generations", default="35,350")
    args = parser.parse_args()
    if not 1 <= args.seeds <= 20:
        parser.error("--seeds must be 1..20")
    generations = [int(x) for x in args.generations.split(",")]
    if not generations or any(x not in (35, 350) for x in generations):
        parser.error("supported generations are 35 and 350")
    names = ["greedy", "optimiser"] + [
        f"genetic_{g}_s{seed}" for g in generations for seed in range(args.seeds)]
    df = run("validation", names, limit=args.limit)
    ga = df[df.planner.str.startswith("genetic_")].copy()
    ga["generations"] = ga.planner.str.extract(r"genetic_(\d+)_s").astype(int)
    ga["seed"] = ga.planner.str.extract(r"_s(\d+)$").astype(int)
    # Aggregate each seed over the same scenarios, then report variation across seeds.
    by_seed = ga.groupby(["generations", "seed"])[METRICS].mean().reset_index()
    summary = by_seed.groupby("generations")[METRICS].agg(["mean", "std", "min", "max"]).round(3)
    print("\n=== GA performance across seeds (mean/std/min/max of scenario means) ===")
    print(summary.to_string())
    print("\n=== Deterministic comparison ===")
    print(df[df.planner.isin(["greedy", "optimiser"])].groupby("planner")[METRICS].mean().round(3).to_string())
    seconds = df.attrs.get("seconds_per_plan", {})
    print("\n=== Runtime (seconds per plan) ===")
    print({k: round(v, 4) for k, v in seconds.items()})
    out = DEFAULT_EVAL_DIR / "runs"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(out / f"{stamp}_ga_multiseed_raw.csv", index=False)
    by_seed.to_csv(out / f"{stamp}_ga_multiseed_by_seed.csv", index=False)
    summary.to_csv(out / f"{stamp}_ga_multiseed_summary.csv")
    print("Saved three CSV files in", out)


if __name__ == "__main__":
    main()
