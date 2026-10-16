"""Robustness: how much a plan degrades when the kitchen is not what the planner was told (evaluation measure 8).

The question
------------
Every planner plans from what the user told us: amounts ("a bag of spinach") and shelf lives that are mostly
FoodKeeper *estimates*. Real kitchens differ - the spinach turns a day early, the bag held 30 % less. A planner that
leans hard on the stated facts can look good on paper and fall apart in the real week. The slide's robustness measure
is "performance under expiry / quantity perturbations, compared against the planner without expiry awareness: less
degradation is better".

How it is measured
------------------
1. Each planner plans each scenario **once**, from the planner-visible scenario (unchanged).
2. The plan is replayed (``evaluation.metrics.evaluate_plan``, the same judge as every other metric) against several
   *perturbed realities* (:func:`perturb_reality`): same user, same plan, same planner-visible deadlines, but the
   hidden truth changed - food spoils earlier than the truth the benchmark already hides, or the stock is not the
   stated amount.
3. **Degradation** = how much worse a metric gets in the perturbed reality than in the nominal one, signed so that
   *positive = worse* whichever way the metric points. It is computed per (scenario, planner), then paired across
   planners on the same scenarios (paired bootstrap, as everywhere else).

The plan is not re-planned when reality differs: the measure is how well a week chosen *in advance* holds up, which
is what the user lives with until they re-plan (``optimizer.replan`` is the remedy, measured separately).

What is perturbed
-----------------
* **Expiry** applies only to stock whose deadline is an *estimate* that falls inside the week. Known use-by dates are
  the truth by definition (CLAUDE.md: they are hard constraints), and food with no deadline this week does not start
  spoiling because an estimate was off. Deadlines are clamped at day 0: the user just told us the food is there, so it
  lasts at least tonight.
* **Quantity** scales every stock's actual grams (the planner still sees the stated grams). Less stock than stated
  means the plan buys the shortfall mid-week; more means more is left over (and wasted if it is perishable).

Everything random takes an explicit seed and a stable per-scenario/per-perturbation hash, so a run is reproducible.

Usage::

    python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_no_expiry --limit 24
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/robustness.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from domain.models import Scenario
from evaluation.metrics import HIGHER_IS_BETTER, evaluate_plan, paired_bootstrap
from evaluation.runner import _stratified_head, build_planner
from evaluation.scenarios import DEFAULT_EVAL_DIR, load_split
from logging_setup import configure_logging
from optimizer.inventory import deadlines_from_pantry
from optimizer.planning import PlanningContext, make_context, prepare

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Perturbation:
    """One way reality can differ from what the planner was told. The default instance changes nothing."""

    name: str
    expiry_shift_days: int = 0      # > 0: estimated perishables spoil this many days EARLIER than the hidden truth
    expiry_jitter_days: int = 0     # each such item additionally moves by a uniform integer in [-j, +j] days
    quantity_scale: float = 1.0     # every stock's real grams = stated grams x scale ...
    quantity_sigma: float = 0.0     # ... x exp(N(0, sigma)), drawn per item (0 = no noise)

    @property
    def is_nominal(self) -> bool:
        return (self.expiry_shift_days == 0 and self.expiry_jitter_days == 0 and self.quantity_scale == 1.0
                and self.quantity_sigma == 0.0)


NOMINAL = Perturbation("nominal")
# The standard set. Sizes are "plausible error", not stress tests: 1-2 days is well inside the spread of a FoodKeeper
# min-max range for fridge produce (spinach 3-7 days, berries 3-6), and +/-30 % is how far a guessed amount ("some
# rice", "a bag of spinach") or the NLP layer's assumed default quantity (a food-group median, ``nlp/defaults.py``)
# easily is from the real one.
PERTURBATIONS: tuple[Perturbation, ...] = (
    NOMINAL,
    Perturbation("expiry_1d_early", expiry_shift_days=1),
    Perturbation("expiry_2d_early", expiry_shift_days=2),
    Perturbation("expiry_jitter_2d", expiry_jitter_days=2),
    Perturbation("quantity_30pct_less", quantity_scale=0.7),
    Perturbation("quantity_30pct_more", quantity_scale=1.3),
    Perturbation("quantity_noise_30pct", quantity_sigma=0.3),
    Perturbation("combined", expiry_shift_days=1, expiry_jitter_days=1, quantity_sigma=0.3),
)

# Metrics whose degradation is reported. Nutrition, preference, time and safety depend only on the recipes chosen,
# which do not change when reality does, so they cannot degrade here.
ROBUSTNESS_METRICS: tuple[str, ...] = ("waste_g", "avoidable_waste_g", "grocery_items", "grocery_g",
                                       "expiring_utilisation_pct", "pantry_utilisation_pct")
DEFAULT_BASELINE = "opt_no_expiry"       # the slide: "compared against the planner without expiry awareness"


def _rng(scenario: Scenario, perturbation: Perturbation, seed: int) -> np.random.Generator:
    """A generator that depends only on (scenario, perturbation, seed): stable across runs and planners."""
    return np.random.default_rng([seed, zlib.crc32(scenario.scenario_id.encode()),
                                  zlib.crc32(perturbation.name.encode())])


def perturb_reality(scenario: Scenario, perturbation: Perturbation, seed: int = 0) -> Scenario:
    """The kitchen as it really is under ``perturbation``. Pure: ``scenario`` is not modified.

    The returned scenario keeps the profile and every planner-visible field (``last_use_day``, ``expiry_known``,
    confidence, urgency); only the hidden truth changes: ``true_last_use_day`` and each pantry item's ``grams``. Use it
    only to *judge* a plan made from ``scenario``, never to plan.
    """
    if perturbation.is_nominal:
        return scenario
    rng = _rng(scenario, perturbation, seed)
    visible = deadlines_from_pantry(scenario.pantry)
    truth = {**visible, **scenario.true_last_use_day}       # the evaluator's own rule for "what really happens"
    known = {p.ingredient_id for p in scenario.pantry if p.expiry_known}

    new_truth: dict[int, int | None] = {}
    for iid in sorted(truth):                                # sorted: the draw order must not depend on dict order
        day = truth[iid]
        jitter = (int(rng.integers(-perturbation.expiry_jitter_days, perturbation.expiry_jitter_days + 1))
                  if perturbation.expiry_jitter_days else 0)
        if day is None or iid in known or day >= scenario.horizon_days:
            new_truth[iid] = day
        else:
            new_truth[iid] = max(0, day - perturbation.expiry_shift_days + jitter)

    pantry = []
    for item in scenario.pantry:
        factor = perturbation.quantity_scale
        if perturbation.quantity_sigma:
            factor *= float(np.exp(rng.normal(0.0, perturbation.quantity_sigma)))
        pantry.append(item.model_copy(update={"grams": item.grams * factor}))
    return scenario.model_copy(update={"pantry": pantry, "true_last_use_day": new_truth,
                                       "notes": f"{scenario.notes} | reality: {perturbation.name}".strip(" |")})


def run_robustness(split: str, planner_names: list[str], perturbations: tuple[Perturbation, ...] = PERTURBATIONS,
                   limit: int | None = None, eval_dir: Path = DEFAULT_EVAL_DIR, ctx: PlanningContext | None = None,
                   seed: int = 0) -> pd.DataFrame:
    """Plan each scenario once per planner, judge each plan under every perturbation.

    Returns one row per (scenario, planner, perturbation): every ``PlanMetrics`` field plus ``perturbation``.
    ``perturbations`` must include a nominal entry (:data:`NOMINAL`) for :func:`degradation` to work.
    """
    if not any(p.is_nominal for p in perturbations):
        raise ValueError("include the nominal perturbation: degradation is measured against it")
    ctx = ctx or make_context()
    scenarios = load_split(split, eval_dir)
    if limit:
        scenarios = _stratified_head(scenarios, limit)
    planners = [build_planner(n, ctx) for n in planner_names]
    rows: list[dict] = []
    timing = {p.name: 0.0 for p in planners}
    for k, sc in enumerate(scenarios):
        prepared = prepare(sc, ctx)
        realities = [(pt, perturb_reality(sc, pt, seed)) for pt in perturbations]
        for planner in planners:
            started = time.time()
            plan = planner.plan(sc)
            timing[planner.name] += time.time() - started
            for pt, reality in realities:
                rows.append({**asdict(evaluate_plan(reality, plan, ctx, prepared)), "perturbation": pt.name})
        if (k + 1) % 20 == 0:
            logger.info("%d/%d scenarios done", k + 1, len(scenarios))
    df = pd.DataFrame(rows)
    df.attrs["seconds_per_plan"] = {n: t / max(1, len(scenarios)) for n, t in timing.items()}
    return df


def degradation(df: pd.DataFrame, metrics: tuple[str, ...] = ROBUSTNESS_METRICS) -> pd.DataFrame:
    """Per (scenario, planner, perturbation): ``deg_<metric>`` = how much worse than nominal, positive = worse.

    Nominal rows are dropped (their degradation is 0 by definition).
    """
    key = ["scenario_id", "planner"]
    nominal = df[df.perturbation == NOMINAL.name].set_index(key)[list(metrics)]
    out = df[df.perturbation != NOMINAL.name][key + ["family", "perturbation", *metrics]].copy()
    base = nominal.loc[list(zip(out.scenario_id, out.planner))].to_numpy()
    for j, m in enumerate(metrics):
        sign = -1.0 if HIGHER_IS_BETTER[m] else 1.0
        out[f"deg_{m}"] = sign * (out[m].to_numpy() - base[:, j])
    return out.reset_index(drop=True)


def summarise_degradation(deg: pd.DataFrame, metrics: tuple[str, ...] = ROBUSTNESS_METRICS) -> pd.DataFrame:
    """Mean degradation per (perturbation, planner). Positive = worse than the same plan in the nominal kitchen."""
    cols = [f"deg_{m}" for m in metrics]
    return deg.groupby(["perturbation", "planner"], sort=False)[cols].mean().round(2)


def compare_degradation(deg: pd.DataFrame, planner: str, baseline: str,
                        metrics: tuple[str, ...] = ROBUSTNESS_METRICS) -> pd.DataFrame:
    """Paired ``planner - baseline`` difference in degradation, 95 % bootstrap CI, one row per perturbation.

    A negative mean means ``planner`` degrades *less* than ``baseline`` (more robust). Cells read
    ``mean [low, high]``; a CI that excludes 0 is a real difference at this sample size.
    """
    rows = []
    for name, sub in deg.groupby("perturbation", sort=False):
        row: dict[str, object] = {"perturbation": name, "n": int(sub.scenario_id.nunique())}
        for m in metrics:
            r = paired_bootstrap(sub, f"deg_{m}", planner, baseline, higher_is_better=False)
            row[m] = f"{r['mean_diff']:+.1f} [{r['ci_low']:+.1f}, {r['ci_high']:+.1f}]"
        rows.append(row)
    return pd.DataFrame(rows).set_index("perturbation")


def report(df: pd.DataFrame, baseline: str | None = DEFAULT_BASELINE) -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    deg = degradation(df)
    print("\n=== nominal kitchen (mean over scenarios) ===")
    print(df[df.perturbation == NOMINAL.name].groupby("planner")[list(ROBUSTNESS_METRICS)].mean().round(2).to_string())
    print("\n=== mean degradation vs the nominal kitchen (positive = worse) ===")
    print(summarise_degradation(deg).to_string())
    planners = list(dict.fromkeys(df.planner))
    if baseline and baseline in planners:
        for other in planners:
            if other == baseline:
                continue
            print(f"\n=== '{other}' minus '{baseline}' degradation [95% bootstrap CI] (negative = '{other}' more "
                  f"robust) ===")
            print(compare_degradation(deg, other, baseline).to_string())
    secs = df.attrs.get("seconds_per_plan", {})
    if secs:
        print("\nseconds per plan:", {k: round(v, 3) for k, v in secs.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["validation", "test"], default="validation")
    ap.add_argument("--planners", default="greedy,optimiser,opt_no_expiry")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--limit", type=int, default=None, help="max scenarios (stratified by family)")
    ap.add_argument("--seed", type=int, default=0, help="seed of the random perturbations")
    ap.add_argument("--save", action="store_true", help="write the per-row results to <eval-dir>/runs/")
    ap.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR, help="folder holding the frozen benchmark")
    ap.add_argument("--log-level", default=None, help="DEBUG | INFO | WARNING (default: $PTP_LOG_LEVEL, else INFO)")
    args = ap.parse_args()
    configure_logging(args.log_level)
    if args.split == "test":
        print("!! TEST SPLIT: run this once, after weights are frozen. Never tune on it. !!")
    df = run_robustness(args.split, args.planners.split(","), limit=args.limit, eval_dir=args.eval_dir,
                        seed=args.seed)
    report(df, args.baseline)
    if args.save:
        out = args.eval_dir / "runs"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{datetime.now():%Y%m%d_%H%M%S}_robustness_{args.split}.csv"
        df.to_csv(path, index=False)
        print("saved", path)


if __name__ == "__main__":
    main()
