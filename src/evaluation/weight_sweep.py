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
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/weight_sweep.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from evaluation.scenarios import DEFAULT_EVAL_DIR
from logging_setup import configure_logging
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
    configs = []
    for pair in (s for s in spec.split(",") if s):
        parts = pair.split(":")
        if len(parts) not in (2, 4, 5):
            raise ValueError(f"candidate {pair!r}: expected 'pref:nutrition', 'pref:nutrition:variety:cap' or "
                             "'pref:nutrition:variety:cap:waste'")
        configs.append(SweepConfig(float(parts[0]), float(parts[1]),
                                   float(parts[2]) if len(parts) >= 4 else 1.0,
                                   int(parts[3]) if len(parts) >= 4 else 4,
                                   float(parts[4]) if len(parts) == 5 else 1.0))
    default = SweepConfig()
    return (default, *[c for c in configs if c != default])


# A week with this many dinners of one protein type reads as "chicken every night". Used to *report* how common that
# is (``samey_weeks``) and in the variety rule below.
SAMEY_WEEK_MEALS = 5

# --- choosing a variety setting (declared before the run, like the others) --------------------------------------
# Context: reading the first real plans in the UI showed 7 poultry dinners for a pantry containing chicken, under the
# ORIGINAL weights as well as the adopted ones. The objective counts distinct grocery items, so repeating one protein
# is cheap, and the variety penalty (0.7 per dinner beyond 4 of one type) is weak. Candidates are compared with a
# reference (the adopted weights) on the same scenarios.
VARIETY_CRITERIA = {
    "samey_weeks_drop": 0.25,              # share of one-protein weeks must fall by at least this much (absolute)
    "grocery_items": 1.0,                  # at most +1.0 extra grocery items vs the reference
    "nutrition_in_range_pct": -3.0,        # at most 3 points fewer dinners in the calorie band
    "liked_cuisine_rate": -0.03,           # at most 3 points fewer liked-cuisine dinners
    "waste_g": 0.05,                       # at most 5 % more waste
    "violations": 0.0,
    "complete": 0.0,
}


def variety_failures(summary: pd.DataFrame, reference: str, candidate: str) -> list[str]:
    """Which ``VARIETY_CRITERIA`` ``candidate`` misses against ``reference`` (empty = an acceptable fix)."""
    r, c = summary.loc[reference], summary.loc[candidate]
    missed: list[str] = []
    if r["samey_weeks"] - c["samey_weeks"] < VARIETY_CRITERIA["samey_weeks_drop"] - 1e-9:
        missed.append("still too many one-protein weeks")
    if c["grocery_items"] - r["grocery_items"] > VARIETY_CRITERIA["grocery_items"] + 1e-9:
        missed.append("too many extra grocery items")
    if c["nutrition_in_range_pct"] - r["nutrition_in_range_pct"] < VARIETY_CRITERIA["nutrition_in_range_pct"] - 1e-9:
        missed.append("calorie fit fell")
    if c["liked_cuisine_rate"] - r["liked_cuisine_rate"] < VARIETY_CRITERIA["liked_cuisine_rate"] - 1e-9:
        missed.append("liked cuisines fell")
    if c["waste_g"] > r["waste_g"] * (1 + VARIETY_CRITERIA["waste_g"]) + 1e-9:
        missed.append("waste rose")
    if c["violations"] > VARIETY_CRITERIA["violations"] + 1e-9:
        missed.append("rule violations")
    if c["complete"] < r["complete"] + VARIETY_CRITERIA["complete"] - 1e-9:
        missed.append("shorter weeks")
    return missed


def choose_variety(summary: pd.DataFrame, reference: str) -> tuple[str, dict[str, list[str]]]:
    """The variety setting to adopt: the lowest mean ``max_protein_type_meals`` among candidates with no failures;
    ties go to the smaller change; if none qualifies, ``reference`` is kept. Returns ``(name, failures)``."""
    failures = {n: variety_failures(summary, reference, n) for n in summary.index if n != reference}
    passing = [n for n, broken in failures.items() if not broken]
    if not passing:
        return reference, failures

    def key(name: str) -> tuple[float, float]:
        row = summary.loc[name]
        change = abs(row["variety_x"] - 1.0) + abs(row["protein_cap"] - 4.0)
        return (round(float(row["max_protein_type_meals"]), 2), float(change))

    return min(passing, key=key), failures


# --- choosing a waste weight (declared 2026-10-14, BEFORE the 120-scenario run) ------------------------------------
# Context: in ``restrictive_diet`` the adopted weights wasted more than greedy (+47 g [+3, +93], validation). A
# diagnosis on those 15 scenarios found the waste term too weak next to preference x6: using up 60 g of expiring
# vegetables was worth less than half a grocery item, so 7 of 15 weeks used none of the expiring stock; waste x3 closed
# the gap there. That diagnosis motivated the candidates (waste x2, x3) - which is why the decision is made on ALL 120
# validation scenarios, against these criteria, relative to the adopted weights. The headline measure is
# ``avoidable_waste_g`` (waste some permitted recipe could have prevented; ``evaluation/metrics.py``).
WASTE_CRITERIA = {
    "avoidable_waste_drop": 0.05,          # avoidable waste must fall by at least 5 % (relative)
    "grocery_items": 1.0,                  # at most +1.0 extra grocery items a week
    "nutrition_in_range_pct": -3.0,        # at most 3 points fewer dinners in the calorie band
    "protein_ok_pct": -3.0,                # at most 3 points fewer dinners reaching the protein minimum
    "liked_cuisine_rate": -0.03,           # at most 3 points fewer liked-cuisine dinners (protects the 10-13 decision)
    "violations": 0.0,
    "complete": 0.0,
}


def waste_failures(summary: pd.DataFrame, reference: str, candidate: str) -> list[str]:
    """Which ``WASTE_CRITERIA`` ``candidate`` misses against ``reference`` (empty = acceptable)."""
    r, c = summary.loc[reference], summary.loc[candidate]
    missed: list[str] = []
    if c["avoidable_waste_g"] > r["avoidable_waste_g"] * (1 - WASTE_CRITERIA["avoidable_waste_drop"]) + 1e-9:
        missed.append("avoidable waste did not fall enough")
    if c["grocery_items"] - r["grocery_items"] > WASTE_CRITERIA["grocery_items"] + 1e-9:
        missed.append("too many extra grocery items")
    if c["nutrition_in_range_pct"] - r["nutrition_in_range_pct"] < WASTE_CRITERIA["nutrition_in_range_pct"] - 1e-9:
        missed.append("calorie fit fell")
    if c["protein_ok_pct"] - r["protein_ok_pct"] < WASTE_CRITERIA["protein_ok_pct"] - 1e-9:
        missed.append("protein fell")
    if c["liked_cuisine_rate"] - r["liked_cuisine_rate"] < WASTE_CRITERIA["liked_cuisine_rate"] - 1e-9:
        missed.append("liked cuisines fell")
    if c["violations"] > WASTE_CRITERIA["violations"] + 1e-9:
        missed.append("rule violations")
    if c["complete"] < r["complete"] + WASTE_CRITERIA["complete"] - 1e-9:
        missed.append("shorter weeks")
    return missed


def choose_waste(summary: pd.DataFrame, reference: str) -> tuple[str, dict[str, list[str]]]:
    """The waste weight to adopt: the lowest mean ``avoidable_waste_g`` among candidates with no failures (equal to
    1 g: the smaller change); if none qualifies, ``reference`` is kept. Returns ``(name, failures)``."""
    failures = {n: waste_failures(summary, reference, n) for n in summary.index
                if n != reference and summary.loc[n, "waste_x"] != summary.loc[reference, "waste_x"]}
    passing = [n for n, broken in failures.items() if not broken]
    if not passing:
        return reference, failures
    return min(passing, key=lambda n: (round(float(summary.loc[n, "avoidable_waste_g"])),
                                       abs(float(summary.loc[n, "waste_x"]) - 1.0))), failures


@dataclass(frozen=True)
class SweepConfig:
    """One candidate: multipliers on the default weights."""

    preference: float = 1.0
    nutrition: float = 1.0
    variety: float = 1.0                 # multiplier on the per-meal penalty beyond a variety cap
    protein_cap: int = 4                 # most dinners of one protein type before that penalty applies
    waste: float = 1.0                   # multiplier on the cost of expiring stock left unused

    @property
    def name(self) -> str:
        # unchanged parts are left out, so names of earlier recorded runs stay comparable
        parts = [f"pref x{self.preference:g}, nutrition x{self.nutrition:g}"]
        if not (self.variety == 1.0 and self.protein_cap == 4):
            parts.append(f"variety x{self.variety:g}, cap {self.protein_cap}")
        if self.waste != 1.0:
            parts.append(f"waste x{self.waste:g}")
        return ", ".join(parts)

    @property
    def is_default(self) -> bool:
        return self == SweepConfig()


GRID = tuple(SweepConfig(p, n) for p in PREFERENCE_MULTIPLIERS for n in NUTRITION_MULTIPLIERS)


#: The hand-set weights the sweep started from. Multipliers are relative to THIS, not to ``DEFAULT_WEIGHTS``: once a
#: candidate is adopted ``DEFAULT_WEIGHTS`` changes, and "x3" must keep meaning x3 of the starting point or the sweep
#: would stop being reproducible (x3 of an adopted x3 is x9). Every weight the grid scales is written out here by
#: value on purpose - deriving any of them from ``DEFAULT_WEIGHTS`` is the bug this constant exists to prevent (it
#: happened once: only ``preference`` was pinned, so adopting nutrition x2 silently turned the grid's x2 into x4).
SWEEP_BASE = replace(DEFAULT_WEIGHTS, preference=1.0, kcal_deviation=4.0, protein_deviation=2.0, variety=0.7,
                     protein_type_cap=4, waste_per_100g=1.0)


def weights_for(config: SweepConfig) -> OptimizerWeights:
    """``OptimizerWeights`` with the multipliers applied to ``SWEEP_BASE``."""
    return replace(SWEEP_BASE,
                   preference=SWEEP_BASE.preference * config.preference,
                   kcal_deviation=SWEEP_BASE.kcal_deviation * config.nutrition,
                   protein_deviation=SWEEP_BASE.protein_deviation * config.nutrition,
                   variety=SWEEP_BASE.variety * config.variety, protein_type_cap=config.protein_cap,
                   waste_per_100g=SWEEP_BASE.waste_per_100g * config.waste)


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
    from optimizer.weekly import WeeklyPlanner, protein_type

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
        indices = [ctx.catalog.index_of(r) for r in plan.recipe_ids]
        cuisines = [ctx.catalog.cuisine[i] for i in indices]
        types = Counter(protein_type(ctx.catalog, i) for i in indices)
        rows.append({**m.__dict__, "config": config.name, "preference_x": config.preference,
                     "nutrition_x": config.nutrition, "variety_x": config.variety, "protein_cap": config.protein_cap,
                     "waste_x": config.waste,
                     "liked_cuisine_rate": liked_cuisine_rate(cuisines, sc.profile.liked_cuisines),
                     # variety as a user sees it: the most dinners sharing one protein type, and how many types
                     "max_protein_type_meals": max(types.values()) if types else 0,
                     "distinct_protein_types": len(types)})
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
    cols = ["preference_mean", "disliked_rate", "liked_cuisine_rate", "waste_g", "avoidable_waste_g", "grocery_items",
            "nutrition_in_range_pct", "protein_ok_pct", "violations", "complete", "max_protein_type_meals",
            "distinct_protein_types"]
    means = df.groupby("config", sort=False)[[c for c in cols if c in df.columns]].mean()
    if "max_protein_type_meals" in df.columns:        # the share of weeks a user would call "the same thing all week"
        samey = (df.max_protein_type_meals >= SAMEY_WEEK_MEALS).groupby(df.config, sort=False).mean()
        means = means.join(samey.rename("samey_weeks"))
    keys = [c for c in ("preference_x", "nutrition_x", "variety_x", "protein_cap", "waste_x") if c in df.columns]
    return means.join(df.groupby("config", sort=False)[keys].first())


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
    ap.add_argument("--variety-reference", default=None, metavar="SPEC",
                    help="compare the other candidates with this one (e.g. '6:2:1:4' = the adopted weights) under "
                         "VARIETY_CRITERIA")
    ap.add_argument("--waste-reference", default=None, metavar="SPEC",
                    help="compare candidates with a different waste multiplier against this one (e.g. '6:2' = the "
                         "adopted weights) under WASTE_CRITERIA")
    ap.add_argument("--save", action="store_true", help="write per-scenario rows to data/evaluation/runs/")
    args = ap.parse_args()
    configure_logging()       # this process only: the worker processes keep Python's default (WARNING and above)

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
    if args.variety_reference:
        ref = parse_candidates(args.variety_reference)[-1].name
        pick, why = choose_variety(summary, ref)
        print(f"\n=== variety candidates vs {ref} ===")
        for name, broken in why.items():
            print(f"  {name:<46} {'ok' if not broken else 'FAIL: ' + ', '.join(broken)}")
        print(f"  -> variety choice by the pre-declared rule: {pick}")
    if args.waste_reference:
        ref = parse_candidates(args.waste_reference)[-1].name
        pick, why = choose_waste(summary, ref)
        print(f"\n=== waste candidates vs {ref} (WASTE_CRITERIA) ===")
        for key, value in WASTE_CRITERIA.items():
            print(f"  criterion {key:<24} {value}")
        for name, broken in why.items():
            print(f"  {name:<46} {'ok' if not broken else 'FAIL: ' + ', '.join(broken)}")
        print(f"  -> waste choice by the pre-declared rule: {pick}")
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
