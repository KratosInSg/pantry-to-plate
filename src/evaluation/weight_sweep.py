"""Bounded weight sweep for the weekly optimiser - on the VALIDATION split only.

Why this exists
---------------
Reading real explanations showed two weaknesses of the hand-set defaults (``md docs/evaluation.md``): the preference
term has almost no effect (a user who says "I love Italian food" sees no change), and restrictive diets get dinners far
below the protein minimum. Both are weights. This module tunes them *the way the project's rules require*:

* **Validation only.** ``--split test`` is refused outright. The test split is run once, after weights are frozen.
* **A small, stated grid** (``GRID``), not a search. Every candidate is a multiple of the default, so the result is
  readable ("preference x3") and the number of comparisons - the room to overfit - is small.
* **The choice rule is code, decided before the numbers are seen** (``choose``): among candidates that pass the
  guardrails, take the one with the largest liked-cuisine rate; ties go to the smaller change. If none passes, the
  default is kept. Writing the rule down first is what stops "pick the best-looking row".
* **Paired comparison on identical scenarios**, so differences are the weights, not the scenario draw.

What "visible effect" means
---------------------------
``liked_cuisine_rate``: of the planned dinners, the share whose cuisine the user said they like (over scenarios that
state a liked cuisine). It is what a user would notice. ``preference_mean`` and ``disliked_rate`` come from the
standard metrics.

Usage (repository root)::

    python src/evaluation/weight_sweep.py --limit 48 --workers 6 --save
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/weight_sweep.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from evaluation.scenarios import DEFAULT_EVAL_DIR
from optimizer.weekly import DEFAULT_WEIGHTS, OptimizerWeights

# Candidate weights are multiples of the starting weights (``SWEEP_BASE``). 1.0 = unchanged.
PREFERENCE_MULTIPLIERS = (1.0, 3.0, 6.0)
NUTRITION_MULTIPLIERS = (1.0, 2.0)          # scales kcal_deviation and protein_deviation together

# Guardrails a candidate must satisfy against the default, on the same scenarios (means over scenarios).
GUARDRAILS = {
    "waste_g": 0.05,                       # may be at most 5 % worse (relative)
    "grocery_items": 0.5,                  # at most half an item worse (absolute)
    "nutrition_in_range_pct": -3.0,        # at most 3 points worse (absolute; negative = allowed drop)
    "disliked_rate": 0.02,                 # the share of disliked meals may not rise by more than 2 points
    "violations": 0.0,                     # never any violation
    "complete": 0.0,                       # never a shorter week
}


# --- confirmation of a trade-off the project owner chose to make --------------------------------------------------
# The sweep's guardrail protects the grocery count (+0.5 items). On 2026-10-13 the owner decided that stronger taste
# matching and a better calorie fit are worth up to about three extra grocery items a week - a product decision, not
# something the data can make. Because that decision came *after* seeing the 48-scenario sweep, the exact candidate is
# re-measured on the FULL validation split (which includes scenarios the sweep never saw) against criteria fixed here,
# before that run. All differences are candidate minus the starting weights; means over scenarios.
ADOPTION_CRITERIA = {
    "liked_cuisine_rate": 0.10,            # at least +10 points of dinners in a liked cuisine
    "nutrition_in_range_pct": 8.0,         # at least +8 points of dinners inside the calorie band
    "grocery_items": 3.5,                  # at most +3.5 extra grocery items a week (the owner's accepted cost)
    "waste_g": 0.05,                       # at most 5 % more waste (relative)
    "disliked_rate": 0.02,                 # disliked meals may not rise by more than 2 points
    "violations": 0.0,                     # no rule violations
    "complete": 0.0,                       # no shorter weeks
}


def adoption_failures(summary: pd.DataFrame, baseline: str, candidate: str) -> list[str]:
    """Which ``ADOPTION_CRITERIA`` ``candidate`` misses against ``baseline`` (empty = adopt)."""
    b, c = summary.loc[baseline], summary.loc[candidate]
    missed: list[str] = []
    if c["liked_cuisine_rate"] - b["liked_cuisine_rate"] < ADOPTION_CRITERIA["liked_cuisine_rate"] - 1e-9:
        missed.append("liked cuisine effect too small")
    if c["nutrition_in_range_pct"] - b["nutrition_in_range_pct"] < ADOPTION_CRITERIA["nutrition_in_range_pct"] - 1e-9:
        missed.append("calorie-band gain too small")
    if c["grocery_items"] - b["grocery_items"] > ADOPTION_CRITERIA["grocery_items"] + 1e-9:
        missed.append("too many extra grocery items")
    if c["waste_g"] > b["waste_g"] * (1 + ADOPTION_CRITERIA["waste_g"]) + 1e-9:
        missed.append("waste rose")
    if c["disliked_rate"] - b["disliked_rate"] > ADOPTION_CRITERIA["disliked_rate"] + 1e-9:
        missed.append("disliked meals rose")
    if c["violations"] > ADOPTION_CRITERIA["violations"] + 1e-9:
        missed.append("rule violations")
    if c["complete"] < b["complete"] + ADOPTION_CRITERIA["complete"] - 1e-9:
        missed.append("shorter weeks")
    return missed


def parse_candidates(spec: str) -> tuple["SweepConfig", ...]:
    """``"1:1,3:1,6:2"`` -> candidates (preference multiplier : nutrition multiplier). The default (1:1) is always
    first, because every comparison is against it."""
    configs = [SweepConfig(float(p), float(n)) for p, n in (pair.split(":") for pair in spec.split(",") if pair)]
    default = SweepConfig()
    return (default, *[c for c in configs if c != default])


@dataclass(frozen=True)
class SweepConfig:
    """One candidate: multipliers on the default weights."""

    preference: float = 1.0
    nutrition: float = 1.0

    @property
    def name(self) -> str:
        return f"pref x{self.preference:g}, nutrition x{self.nutrition:g}"

    @property
    def is_default(self) -> bool:
        return self.preference == 1.0 and self.nutrition == 1.0


GRID = tuple(SweepConfig(p, n) for p in PREFERENCE_MULTIPLIERS for n in NUTRITION_MULTIPLIERS)


#: The hand-set weights the sweep started from (preference 1.0). Multipliers are relative to THIS, not to
#: ``DEFAULT_WEIGHTS``: once a candidate is adopted ``DEFAULT_WEIGHTS`` changes, and "x3" must keep meaning x3 of the
#: starting point or the sweep would stop being reproducible (x3 of an adopted x3 is x9).
SWEEP_BASE = replace(DEFAULT_WEIGHTS, preference=1.0)


def weights_for(config: SweepConfig) -> OptimizerWeights:
    """``OptimizerWeights`` with the multipliers applied to ``SWEEP_BASE``."""
    return replace(SWEEP_BASE,
                   preference=SWEEP_BASE.preference * config.preference,
                   kcal_deviation=SWEEP_BASE.kcal_deviation * config.nutrition,
                   protein_deviation=SWEEP_BASE.protein_deviation * config.nutrition)


# ==================================================================================================================
# measurement
# ==================================================================================================================
def liked_cuisine_rate(cuisines: list[str | None], liked: frozenset[str]) -> float | None:
    """Share of dinners in a liked cuisine; ``None`` when the user stated no liked cuisine (not measurable)."""
    if not liked or not cuisines:
        return None
    return float(np.mean([c in liked for c in cuisines]))


def _run_config(args: tuple[SweepConfig, str, int | None, Path]) -> list[dict]:
    """One worker: plan every scenario with one candidate. Top-level so it can be pickled."""
    config, split, limit, eval_dir = args
    from evaluation.metrics import evaluate_plan
    from evaluation.runner import _stratified_head
    from evaluation.scenarios import load_split
    from optimizer.planning import make_context, prepare
    from optimizer.weekly import WeeklyPlanner

    ctx = make_context()
    scenarios = load_split(split, eval_dir)
    if limit:
        scenarios = _stratified_head(scenarios, limit)
    planner = WeeklyPlanner(ctx, weights_for(config), name=config.name)
    rows: list[dict] = []
    for sc in scenarios:
        prepared = prepare(sc, ctx)
        plan = planner.plan(sc)
        m = evaluate_plan(sc, plan, ctx, prepared)
        cuisines = [ctx.catalog.cuisine[ctx.catalog.index_of(r)] for r in plan.recipe_ids]
        rows.append({**m.__dict__, "config": config.name, "preference_x": config.preference,
                     "nutrition_x": config.nutrition,
                     "liked_cuisine_rate": liked_cuisine_rate(cuisines, sc.profile.liked_cuisines)})
    return rows


def run_sweep(split: str = "validation", limit: int | None = 48, workers: int = 6,
              configs: tuple[SweepConfig, ...] = GRID, eval_dir: Path = DEFAULT_EVAL_DIR) -> pd.DataFrame:
    """Evaluate every candidate on the same scenarios (one process per candidate). One row per (scenario, config)."""
    if split != "validation":
        raise ValueError("weights are tuned on the VALIDATION split only; the test split is run once, afterwards")
    jobs = [(c, split, limit, eval_dir) for c in configs]
    if workers <= 1:
        results = [_run_config(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
            results = list(pool.map(_run_config, jobs))
    return pd.DataFrame([row for rows in results for row in rows])


# ==================================================================================================================
# the decision rule
# ==================================================================================================================
def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Mean of each metric per candidate (``liked_cuisine_rate`` over the scenarios where it is defined)."""
    cols = ["preference_mean", "disliked_rate", "liked_cuisine_rate", "waste_g", "grocery_items",
            "nutrition_in_range_pct", "protein_ok_pct", "violations", "complete"]
    means = df.groupby("config", sort=False)[cols].mean()
    return means.join(df.groupby("config", sort=False)[["preference_x", "nutrition_x"]].first())


def guardrail_failures(summary: pd.DataFrame, baseline: str) -> dict[str, list[str]]:
    """Which guardrails each candidate breaks relative to ``baseline`` (empty list = passes)."""
    base = summary.loc[baseline]
    out: dict[str, list[str]] = {}
    for name, row in summary.iterrows():
        broken: list[str] = []
        if row["waste_g"] > base["waste_g"] * (1 + GUARDRAILS["waste_g"]) + 1e-9:
            broken.append("waste")
        if row["grocery_items"] > base["grocery_items"] + GUARDRAILS["grocery_items"] + 1e-9:
            broken.append("groceries")
        if row["nutrition_in_range_pct"] < base["nutrition_in_range_pct"] + GUARDRAILS["nutrition_in_range_pct"] - 1e-9:
            broken.append("nutrition")
        if row["disliked_rate"] > base["disliked_rate"] + GUARDRAILS["disliked_rate"] + 1e-9:
            broken.append("disliked meals")
        if row["violations"] > GUARDRAILS["violations"] + 1e-9:
            broken.append("violations")
        if row["complete"] < base["complete"] + GUARDRAILS["complete"] - 1e-9:
            broken.append("completeness")
        out[name] = broken
    return out


def choose(summary: pd.DataFrame, baseline: str) -> tuple[str, dict[str, list[str]]]:
    """The candidate to adopt: largest ``liked_cuisine_rate`` among those passing every guardrail; ties go to the
    smaller change from the default; if none beats the default, the default is kept.

    Returns ``(name, failures)`` where ``failures`` explains every rejection.
    """
    failures = guardrail_failures(summary, baseline)
    passing = [n for n, broken in failures.items() if not broken]
    base_rate = summary.loc[baseline, "liked_cuisine_rate"]

    def key(name: str) -> tuple[float, float]:
        row = summary.loc[name]
        change = (row["preference_x"] - 1.0) + (row["nutrition_x"] - 1.0)      # how far from the default
        return (-round(float(row["liked_cuisine_rate"]), 3), float(change))     # equal rates (3 d.p.): smaller change

    best = min(passing, key=key) if passing else baseline
    if summary.loc[best, "liked_cuisine_rate"] <= base_rate + 1e-9:
        best = baseline
    return best, failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="validation", help="only 'validation' is allowed")
    ap.add_argument("--limit", type=int, default=48, help="scenarios (stratified by family)")
    ap.add_argument("--workers", type=int, default=6, help="parallel processes (one per candidate)")
    ap.add_argument("--candidates", default=None,
                    help="only these, as 'pref:nutrition' multipliers, e.g. '3:1,6:2' (the default 1:1 is always "
                         "included). Omit for the full grid. --limit 0 uses every validation scenario")
    ap.add_argument("--confirm", default=None, metavar="PREF:NUTRITION",
                    help="also check this candidate against ADOPTION_CRITERIA (must be among the candidates)")
    ap.add_argument("--save", action="store_true", help="write per-scenario rows to data/evaluation/runs/")
    args = ap.parse_args()

    configs = parse_candidates(args.candidates) if args.candidates else GRID
    df = run_sweep(args.split, args.limit or None, args.workers, configs)
    pd.set_option("display.width", 220)
    summary = summarise(df)
    baseline = SweepConfig().name
    print(f"\n=== candidates (mean over {df.scenario_id.nunique()} validation scenarios) ===")
    print(summary.round(3).to_string())
    best, failures = choose(summary, baseline)
    print("\n=== guardrail check vs default ===")
    for name, broken in failures.items():
        print(f"  {name:<28} {'PASS' if not broken else 'FAIL: ' + ', '.join(broken)}")
    print(f"\nchosen by the pre-declared rule: {best}")
    if args.confirm:
        pref, nut = (float(x) for x in args.confirm.split(":"))
        target = SweepConfig(pref, nut).name
        missed = adoption_failures(summary, baseline, target)
        print(f"\n=== adoption criteria for {target} (n={df.scenario_id.nunique()}) ===")
        for key, value in ADOPTION_CRITERIA.items():
            print(f"  {key:<24} {value}")
        print("  ->", "MEETS ALL CRITERIA: adopt" if not missed else "MISSES: " + "; ".join(missed))
    if args.save:
        out = DEFAULT_EVAL_DIR / "runs"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{datetime.now():%Y%m%d_%H%M%S}_weight_sweep_{args.split}.csv"
        df.to_csv(path, index=False)
        print("saved", path)


if __name__ == "__main__":
    main()
