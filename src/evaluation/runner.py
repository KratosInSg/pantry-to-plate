"""Benchmark runner: run planners over a frozen split and print/save the comparison.

Usage (from the repository root)::

    python -m evaluation.runner --split validation --planners random,greedy --limit 40
    python -m evaluation.runner --split validation --planners random,greedy,optimiser,opt_no_expiry

(``PYTHONPATH=src`` is set automatically when run through ``pytest``; for the command line use
``python src/evaluation/runner.py ...``, which adds ``src`` to the path itself.)

Discipline: tune on ``--split validation`` only. ``--split test`` is for the single final report, after the weights are
frozen; the runner prints a loud reminder when it is used.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/runner.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from evaluation.metrics import HIGHER_IS_BETTER, PlanMetrics, evaluate_plan, paired_bootstrap, summarise, to_frame
from evaluation.scenarios import DEFAULT_EVAL_DIR, load_split
from optimizer.baselines import GreedyIngredientMatchPlanner, RandomFeasiblePlanner
from logging_setup import configure_logging
from optimizer.planning import Planner, PlanningContext, make_context, prepare

logger = logging.getLogger(__name__)

KEY_METRICS = ["waste_g", "avoidable_waste_g", "grocery_items", "pantry_utilisation_pct", "nutrition_in_range_pct",
               "preference_mean", "weekday_overtime_rate", "violations", "complete"]
FAMILY_TABLE_METRICS = ["waste_g", "avoidable_waste_g", "grocery_items", "pantry_utilisation_pct",
                        "nutrition_in_range_pct", "weekday_overtime_rate", "complete"]
PAIRED_METRICS = ["waste_g", "avoidable_waste_g", "grocery_items", "pantry_utilisation_pct", "nutrition_in_range_pct",
                  "preference_mean"]


def build_planner(name: str, ctx: PlanningContext) -> Planner:
    """Planner registry. Extend here when a new method is added."""
    if name == "random":
        return RandomFeasiblePlanner(ctx, seed=0)
    if name == "greedy":
        return GreedyIngredientMatchPlanner(ctx)
    if name.startswith(("optimiser", "opt_")):
        from optimizer.weekly import make_planner            # the weekly optimiser, its ablations, `_cpsat` variants
        return make_planner(name, ctx)
    raise ValueError(f"unknown planner {name!r}")


def run(split: str, planner_names: list[str], limit: int | None = None, eval_dir: Path = DEFAULT_EVAL_DIR,
        ctx: PlanningContext | None = None, verbose: bool = True) -> pd.DataFrame:
    """Evaluate each planner on each scenario of ``split``. Returns one row per (scenario, planner)."""
    ctx = ctx or make_context()
    scenarios = load_split(split, eval_dir)
    if limit:
        scenarios = _stratified_head(scenarios, limit)
    planners = [build_planner(n, ctx) for n in planner_names]
    rows: list[PlanMetrics] = []
    timing = {p.name: 0.0 for p in planners}
    for k, sc in enumerate(scenarios):
        prepared = prepare(sc, ctx)                     # shared by every planner and by the metrics
        for p in planners:
            t = time.time()
            plan = p.plan(sc)
            timing[p.name] += time.time() - t
            rows.append(evaluate_plan(sc, plan, ctx, prepared))
        if verbose and (k + 1) % 20 == 0:
            logger.info("%d/%d scenarios done", k + 1, len(scenarios))
    df = to_frame(rows)
    df.attrs["seconds_per_plan"] = {n: t / max(1, len(scenarios)) for n, t in timing.items()}
    return df


def _stratified_head(scenarios, limit: int):
    """First ``limit`` scenarios, taking evenly from each family so a small run still covers all of them."""
    by_family: dict[str, list] = {}
    for s in scenarios:
        by_family.setdefault(s.family, []).append(s)
    per = max(1, limit // max(1, len(by_family)))
    return [s for fam in by_family.values() for s in fam[:per]]


PER_FAMILY_METRICS = ["waste_g", "avoidable_waste_g", "grocery_items", "nutrition_in_range_pct", "preference_mean"]


def per_family_comparison(df: pd.DataFrame, planner: str, baseline: str,
                          metrics: list[str] = PER_FAMILY_METRICS) -> pd.DataFrame:
    """Paired difference ``planner - baseline`` with a 95 % bootstrap CI, one row per scenario family.

    The evaluation design asks for per-family reporting (not pooled): a method can win overall and still lose in the
    family that matters to a particular user. Cells read ``mean [low, high]``; a CI that excludes 0 is a real
    difference at this sample size (n scenarios per family is small, so CIs are wide).
    """
    rows = []
    for family, sub in df.groupby("family"):
        row: dict[str, object] = {"family": family, "n": int(sub.scenario_id.nunique())}
        for m in metrics:
            r = paired_bootstrap(sub, m, planner, baseline)
            row[m] = f"{r['mean_diff']:+.1f} [{r['ci_low']:+.1f}, {r['ci_high']:+.1f}]"
        rows.append(row)
    return pd.DataFrame(rows).set_index("family")


def report(df: pd.DataFrame, baseline: str | None = None) -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print("\n=== overall (mean over scenarios) ===")
    print(summarise(df)[KEY_METRICS].to_string())
    print("\n=== by family ===")
    print(summarise(df, ["family", "planner"])[FAMILY_TABLE_METRICS].to_string())
    planners = sorted(df.planner.unique())
    if baseline and baseline in planners and len(planners) > 1:
        print(f"\n=== paired comparison vs '{baseline}' (mean difference, 95% bootstrap CI) ===")
        for other in planners:
            if other == baseline:
                continue
            for m in PAIRED_METRICS:
                r = paired_bootstrap(df, m, other, baseline)
                arrow = "better" if (r["mean_diff"] > 0) == HIGHER_IS_BETTER[m] else "worse"
                print(f"  {other:<10} {m:<26} {r['mean_diff']:+9.2f}  [{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]  "
                      f"{arrow}; better in {100 * r['share_a_better']:.0f}% of scenarios (n={int(r['n'])})")
            print(f"\n=== '{other}' minus '{baseline}' PER FAMILY: mean difference [95% bootstrap CI] ===")
            print(per_family_comparison(df, other, baseline).to_string())
    secs = df.attrs.get("seconds_per_plan", {})
    if secs:
        print("\nseconds per plan:", {k: round(v, 3) for k, v in secs.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["validation", "test"], default="validation")
    ap.add_argument("--planners", default="random,greedy")
    ap.add_argument("--limit", type=int, default=None, help="max scenarios (stratified by family)")
    ap.add_argument("--baseline", default="greedy")
    ap.add_argument("--save", action="store_true", help="write the per-scenario results to data/evaluation/runs/")
    ap.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR, help="folder holding the frozen benchmark")
    ap.add_argument("--log-level", default=None, help="DEBUG | INFO | WARNING (default: $PTP_LOG_LEVEL, else INFO)")
    args = ap.parse_args()
    configure_logging(args.log_level)
    if args.split == "test":
        print("!! TEST SPLIT: run this once, after weights are frozen. Never tune on it. !!")
    df = run(args.split, args.planners.split(","), args.limit, args.eval_dir)
    report(df, args.baseline)
    if args.save:
        out = DEFAULT_EVAL_DIR / "runs"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{datetime.now():%Y%m%d_%H%M%S}_{args.split}.csv"
        df.to_csv(path, index=False)
        print("saved", path)


if __name__ == "__main__":
    main()
