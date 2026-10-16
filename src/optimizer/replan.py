"""Mid-week replanning: turn "days 0..t-1 have happened" into a fresh planning problem for the days that are left.

Why this is a *roll forward* and not a change to the optimiser
--------------------------------------------------------------
``docs/systemflow.md`` asks for: past days never touched, ingredients of a skipped or rejected meal stay in stock and
get used first, and the remaining days re-planned from the *current* pantry. All of that falls out of one
transformation, so the optimiser itself needs no new concept (no "locked day", no partial horizon):

1. replay the dinners that were actually cooked (``None`` = skipped) against the pantry, with the same substitution
   rules the plan showed (``optimizer.substitutions``: a dinner cooked with milk + lemon instead of buttermilk used
   the milk),
2. what they consumed leaves the pantry; stock whose deadline has passed is gone (reported, not silently dropped),
3. the remaining stock's deadlines are shifted by ``t`` days,
4. the new ``Scenario`` has ``horizon_days - t`` days and ``start_weekday + t``.

A skipped or rejected dinner simply was not cooked, so its ingredients are still in the pantry and - with their
shorter deadline - are exactly what the waste term chases in the next solve. Rejections ("not this recipe") are a hard
rule on the profile (``UserProfile.excluded_recipe_ids``), applied by the caller before planning.

This module is pure: the input scenario is never modified.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from domain.models import PantryItem, Scenario
from optimizer.inventory import deadlines_from_pantry
from optimizer.planning import PlanningContext
from optimizer.substitutions import replay_with_substitutions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RolledForward:
    """The remaining-days problem plus what happened to the pantry while the earlier days passed."""

    scenario: Scenario
    elapsed_days: int
    consumed_g: dict[int, float] = field(default_factory=dict)     # ingredient_id -> grams cooked with
    expired_g: dict[int, float] = field(default_factory=dict)      # ingredient_id -> grams that went off, unused


def roll_forward(scenario: Scenario, cooked_recipe_ids: Sequence[int | None], ctx: PlanningContext) -> RolledForward:
    """Plan-from-here: the scenario for the days after ``len(cooked_recipe_ids)`` have been lived.

    Args:
        scenario: the problem the original plan was made for.
        cooked_recipe_ids: for each elapsed day in order, the Food.com recipe id actually cooked, or ``None`` if that
            day was skipped (nothing consumed; the day still passes).
        ctx: planning context (catalogue + staples to ignore).

    Returns:
        The new scenario (``horizon_days`` shorter, ``start_weekday`` advanced, current pantry, deadlines shifted)
        and the grams consumed / expired.

    Raises:
        ValueError: nothing is left to plan, or more days were given than the horizon holds.
        KeyError: a cooked recipe id is not in the catalogue.
    """
    elapsed = len(cooked_recipe_ids)
    remaining = scenario.horizon_days - elapsed
    if remaining <= 0:
        raise ValueError(f"nothing left to plan: {elapsed} day(s) elapsed of a {scenario.horizon_days}-day plan")

    indices = [None if rid is None else ctx.catalog.index_of(rid) for rid in cooked_recipe_ids]
    deadlines = deadlines_from_pantry(scenario.pantry)
    # horizon_days=elapsed: leftover stock with a deadline inside the elapsed days is "waste" (it expired);
    # everything else is "unused" (still good now)
    report = replay_with_substitutions(indices, scenario, ctx, deadlines, horizon_days=elapsed).report

    by_ingredient: dict[int, list[PantryItem]] = {}
    for item in scenario.pantry:
        by_ingredient.setdefault(item.ingredient_id, []).append(item)

    new_pantry: list[PantryItem] = []
    for iid, grams in report.unused_g.items():
        items = by_ingredient[iid]
        binding = min((p for p in items if p.last_use_day is not None), key=lambda p: p.last_use_day, default=items[0])
        shifted = None if binding.last_use_day is None else binding.last_use_day - elapsed
        if shifted is not None and shifted >= remaining:
            shifted = None                     # "no deadline inside the plan" is how the model reads a far deadline
        new_pantry.append(PantryItem(
            ingredient_id=iid, grams=grams, last_use_day=shifted, expiry_known=binding.expiry_known,
            expiry_confidence=binding.expiry_confidence, urgency=binding.urgency,
            quantity_assumed=any(p.quantity_assumed for p in items)))

    truth = {iid: (None if d is None else d - elapsed) for iid, d in scenario.true_last_use_day.items()}
    rolled = scenario.model_copy(update={
        "scenario_id": f"{scenario.scenario_id}+d{elapsed}", "pantry": new_pantry, "horizon_days": remaining,
        "start_weekday": (scenario.start_weekday + elapsed) % 7, "true_last_use_day": truth})
    logger.debug("rolled %s forward %d day(s) (%d skipped): %d day(s) left, %d pantry item(s), %.0f g used, "
                 "%.0f g expired", scenario.scenario_id, elapsed, sum(r is None for r in cooked_recipe_ids), remaining,
                 len(new_pantry), sum(report.consumed_g.values()), sum(report.waste_g.values()))
    return RolledForward(scenario=rolled, elapsed_days=elapsed, consumed_g=dict(report.consumed_g),
                         expired_g=dict(report.waste_g))
