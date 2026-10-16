"""Plan metrics: replay any method's week against a scenario and measure what matters (docs/evaluation.md).

Every method - random, greedy, the optimiser, its ablations - goes through :func:`evaluate_plan`, which uses the
*same* inventory replay (``optimizer.inventory.account_inventory``) and the *same* scoring functions. Methods can only
differ in the plan they hand in, never in how they are judged.

Metric table (higher/lower is better is encoded in ``HIGHER_IS_BETTER``)
------------------------------------------------------------------------
=========================  =====================================================================================
metric                     meaning
=========================  =====================================================================================
pantry_utilisation_pct     share of starting (non-staple) pantry grams cooked with
expiring_utilisation_pct   same, restricted to stock that truly expires inside the week
waste_g / waste_pct        grams (and share of expiring stock) that spoiled unused - measured against the HIDDEN
                           true expiry, not the planner's estimate
avoidable_waste_g          the part of ``waste_g`` that some recipe ALLOWED for this user could have used. The rest,
                           ``unavoidable_waste_g``, is stock no permitted recipe contains (meat in a vegan pantry,
                           an allergen): every planner wastes it, so it only dilutes comparisons (added 2026-10-14
                           after it turned out to be ~70 % of the waste in ``restrictive_diet``)
grocery_items / grocery_g  what must be bought: distinct items and grams
violations                 hard-rule violations (diet/allergen/exclusion/...). Must be 0
nutrition_in_range_pct     share of dinners inside the kcal band
nutrition_dev_pct          mean distance outside the band, as % of the dinner target (0 when always inside)
protein_ok_pct             share of dinners meeting the protein minimum
preference_mean            mean preference score of the meals (0-1)
disliked_rate              share of meals containing a disliked ingredient / cuisine
weekday_overtime_rate      share of weekday dinners longer than the user's limit
distinct_cuisines          variety: number of different cuisines in the week
complete                   1 if a full week was planned (infeasible users may get fewer meals)
=========================  =====================================================================================

Note (from the project's own evaluation design): the preference, nutrition and cook-time metrics use the *same
definitions the optimiser minimises*, deliberately - the claim being tested is that planning the week jointly beats
one-meal-at-a-time planning on these costs. Robustness, the frozen NLP set and ablations are the independent checks.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from domain.models import Scenario, WeekPlan
from optimizer.hard_rules import count_violations
from optimizer.inventory import InventoryReport, account_inventory, deadlines_from_pantry
from optimizer.planning import PlanningContext, Prepared, prepare
from preference.scorer import disliked_mask

HIGHER_IS_BETTER: dict[str, bool] = {
    "pantry_utilisation_pct": True, "expiring_utilisation_pct": True, "waste_g": False, "waste_pct": False,
    "avoidable_waste_g": False, "grocery_items": False, "grocery_g": False, "violations": False,
    "nutrition_in_range_pct": True, "nutrition_dev_pct": False, "protein_ok_pct": True, "preference_mean": True,
    "disliked_rate": False, "weekday_overtime_rate": False, "distinct_cuisines": True, "complete": True,
}


@dataclass(frozen=True)
class PlanMetrics:
    """All metrics for one (scenario, planner) pair."""

    scenario_id: str
    family: str
    planner: str
    n_meals: int
    complete: float
    pantry_utilisation_pct: float
    expiring_utilisation_pct: float
    waste_g: float
    waste_pct: float
    avoidable_waste_g: float
    unavoidable_waste_g: float          # identical for every planner on a scenario: context, not a score
    grocery_items: int
    grocery_g: float
    violations: int
    nutrition_in_range_pct: float
    nutrition_dev_pct: float
    protein_ok_pct: float
    preference_mean: float
    disliked_rate: float
    weekday_overtime_rate: float
    distinct_cuisines: int


def _pct(num: float, den: float) -> float:
    return 100.0 * num / den if den > 1e-9 else 0.0


def unusable_ingredients(scenario: Scenario, ctx: PlanningContext, prepared: Prepared) -> set[int]:
    """Pantry ingredients that no recipe passing this user's hard rules contains.

    No planner may cook with them, so their spoilage is the same for every method. Staples are excluded (they are
    never pantry stock in the replay).
    """
    cat = ctx.catalog
    return {item.ingredient_id for item in scenario.pantry
            if item.ingredient_id not in ctx.ignore_ids
            and not prepared.feasible[cat.recipes_using(item.ingredient_id)].any()}


def evaluate_plan(scenario: Scenario, plan: WeekPlan, ctx: PlanningContext,
                  prepared: Prepared | None = None) -> PlanMetrics:
    """Measure ``plan`` on ``scenario``. Pass ``prepared`` to reuse preference scores across planners."""
    cat, profile = ctx.catalog, scenario.profile
    prepared = prepared or prepare(scenario, ctx)
    idx = [cat.index_of(r) for r in plan.recipe_ids]
    n = len(idx)

    # -- inventory against the TRUE deadlines (what really happens) ------------------------------------------------
    visible = deadlines_from_pantry(scenario.pantry)
    truth = {**visible, **scenario.true_last_use_day} if scenario.true_last_use_day else visible
    inv: InventoryReport = account_inventory(idx, scenario.pantry, cat, truth, ctx.ignore_ids, scenario.horizon_days)

    # -- nutrition ---------------------------------------------------------------------------------------------------
    lo, hi = profile.dinner_kcal_range
    kcal = cat.kcal[idx] if n else np.empty(0)
    outside = np.maximum(0.0, np.maximum(lo - kcal, kcal - hi)) if n else np.empty(0)
    in_range = (outside == 0).mean() * 100 if n else 0.0
    dev = float(outside.mean() / profile.dinner_kcal_target * 100) if n else 0.0
    protein_ok = float((cat.protein_g[idx] >= profile.min_protein_g_per_dinner).mean() * 100) if n else 0.0

    # -- preference / cook time / variety ------------------------------------------------------------------------------
    pref = float(prepared.preference[idx].mean()) if n else 0.0
    disliked = float(disliked_mask(cat, profile)[idx].mean()) if n else 0.0
    weekday_days = [d for d in range(n) if scenario.is_weekday(d)]
    over = [cat.minutes[idx[d]] > profile.max_weekday_minutes for d in weekday_days]
    overtime = float(np.mean(over)) if over else 0.0
    cuisines = {cat.cuisine[i] for i in idx if cat.cuisine[i] is not None}

    expiring = inv.expiring_pantry_g
    expiring_used = sum(inv.consumed_g.get(i, 0.0) for i in inv.expiring_ids)
    unusable = unusable_ingredients(scenario, ctx, prepared)
    unavoidable = sum(g for i, g in inv.waste_g.items() if i in unusable)
    return PlanMetrics(
        scenario_id=scenario.scenario_id, family=scenario.family, planner=plan.planner, n_meals=n,
        complete=float(n >= scenario.horizon_days),
        pantry_utilisation_pct=_pct(inv.total_consumed_g, inv.total_pantry_g),
        expiring_utilisation_pct=_pct(expiring_used, expiring),
        waste_g=inv.total_waste_g, waste_pct=_pct(inv.total_waste_g, expiring),
        avoidable_waste_g=inv.total_waste_g - unavoidable, unavoidable_waste_g=unavoidable,
        grocery_items=inv.n_grocery_items, grocery_g=inv.total_groceries_g,
        violations=count_violations(cat, profile, idx),
        nutrition_in_range_pct=float(in_range), nutrition_dev_pct=dev, protein_ok_pct=protein_ok,
        preference_mean=pref, disliked_rate=disliked, weekday_overtime_rate=overtime, distinct_cuisines=len(cuisines))


def to_frame(rows: list[PlanMetrics]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in rows])


def summarise(df: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Mean of every metric, grouped by ``by`` (default: planner)."""
    metric_cols = list(HIGHER_IS_BETTER)
    return df.groupby(by or ["planner"])[metric_cols].mean().round(2)


def paired_bootstrap(df: pd.DataFrame, metric: str, a: str, b: str, n_boot: int = 2000, seed: int = 0,
                     higher_is_better: bool | None = None) -> dict[str, float]:
    """Paired comparison of planners ``a`` and ``b`` on one metric over the *same* scenarios.

    Returns the mean difference ``a - b`` with a 95% bootstrap confidence interval (resampling scenarios), plus the share
    of scenarios where ``a`` is strictly better. Paired because both methods ran on identical scenarios, so the scenario's
    own difficulty cancels out (docs/evaluation.md, "Statistical comparison").

    ``higher_is_better`` defaults to ``HIGHER_IS_BETTER[metric]``; pass it for a column that is not a plan metric
    (e.g. a robustness degradation, where lower is better).
    """
    wide = df.pivot_table(index="scenario_id", columns="planner", values=metric)
    pair = wide[[a, b]].dropna()
    diff = (pair[a] - pair[b]).to_numpy()
    rng = np.random.default_rng(seed)
    boots = np.array([rng.choice(diff, size=len(diff), replace=True).mean() for _ in range(n_boot)]) if len(diff) else np.array([0.0])
    up = HIGHER_IS_BETTER[metric] if higher_is_better is None else higher_is_better
    better = (diff > 0) if up else (diff < 0)
    return {"n": float(len(diff)), "mean_diff": float(diff.mean()) if len(diff) else 0.0,
            "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5)),
            "share_a_better": float(better.mean()) if len(diff) else 0.0}
