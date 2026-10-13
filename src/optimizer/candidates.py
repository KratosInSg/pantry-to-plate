"""Candidate shortlisting: from ~54K recipes to a few hundred the solver can reason about.

Why shortlist at all
--------------------
The weekly optimiser picks 7 of N recipes. With N = 54K the model would have 380K decision variables and an enormous
ingredient-balance structure - far too slow for an interactive app, and almost all of it irrelevant: most recipes
share nothing with this pantry and cannot possibly be part of a good plan.

So the pipeline is: **hard rules** (safety, removes recipes) -> **shortlist** (this module, ranks and keeps the
promising ones) -> **solver** (chooses the combination). The shortlist is deliberately generous and deliberately
*pantry-aware*: it guarantees that every ingredient the user must use up soon has recipes available that use it, so the
solver is never starved of the options it needs to reduce waste.

What the composite score means (all parts in [0, 1])
----------------------------------------------------
    composite = W_PANTRY * pantry_coverage + W_PREFERENCE * preference + W_NUTRITION * nutrition_fit

* ``pantry_coverage``: share of the recipe's mass the pantry can supply, with urgent / soon-to-expire stock counted
  more (``urgency_weight``). A recipe made entirely of things about to go off scores 1.
* ``preference``: from ``preference.scorer``.
* ``nutrition_fit``: how close one serving is to the user's dinner kcal target.

The shortlist is a *candidate generator*, not the decision: its weights only decide who gets considered. Plan quality
is decided by the solver's objective.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

import numpy as np

from domain.models import PantryItem, UserProfile
from knowledge.recipes import RecipeCatalog


@dataclass(frozen=True, slots=True)
class ShortlistConfig:
    """Knobs of the shortlist. ``size`` x 7 days = the number of recipe-day binaries the solver gets: 250 -> 1,750
    (solves in tens of seconds with HiGHS); ``WeeklyPlanner`` defaults to 120, which solves in ~6 s per plan."""

    size: int = 250                       # total candidates handed to the solver
    per_urgent_ingredient: int = 10       # guaranteed options per soon-to-expire pantry ingredient
    urgent_within_days: int = 3           # "soon-to-expire" = last_use_day <= this
    w_pantry: float = 0.5
    w_preference: float = 0.3
    w_nutrition: float = 0.2
    max_cuisine_share: float = 0.35       # no single cuisine may fill more than this share of the shortlist


def urgency_weight(item: PantryItem, urgent_within_days: int = 3) -> float:
    """How much more a gram of this stock is worth using than a gram of ordinary stock.

    1.0 for stock with no deadline in sight, rising to 3.0 for stock that must go today/tomorrow. Estimated deadlines
    count in proportion to their confidence (a guess is worth chasing less than a known date).
    """
    if item.last_use_day is None:
        return 1.0
    closeness = max(0.0, (urgent_within_days + 1 - item.last_use_day) / (urgent_within_days + 1))   # 1 today .. 0 later
    bonus = 2.0 * closeness * (1.0 if item.expiry_known else item.expiry_confidence)
    return 1.0 + bonus


def pantry_coverage(catalog: RecipeCatalog, pantry: list[PantryItem], ignore_ids: Collection[int] = (),
                    urgent_within_days: int = 3) -> np.ndarray:
    """For each recipe: urgency-weighted share of its mass that the pantry can supply, in [0, 1].

    Vectorised over the catalogue's flat ingredient rows, so it costs a few milliseconds for 54K recipes.
    """
    owner, ids, grams = catalog.flat
    size = int(ids.max()) + 1 if len(ids) else 1
    stock = np.zeros(size, dtype=np.float32)
    weight = np.ones(size, dtype=np.float32)
    ignore = set(ignore_ids)
    for item in pantry:
        if item.ingredient_id < size and item.ingredient_id not in ignore:
            stock[item.ingredient_id] += item.grams
            weight[item.ingredient_id] = max(weight[item.ingredient_id], urgency_weight(item, urgent_within_days))
    counted = np.ones(size, dtype=bool)
    if ignore:
        counted[[i for i in ignore if i < size]] = False

    row_total = grams * counted[ids]
    row_covered = np.minimum(grams, stock[ids]) * weight[ids] * counted[ids]
    total = np.bincount(owner, weights=row_total, minlength=catalog.n)
    covered = np.bincount(owner, weights=row_covered, minlength=catalog.n)
    w_max = float(weight.max()) if size else 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = np.where(total > 0, covered / (total * w_max), 0.0)
    return np.clip(cov, 0.0, 1.0).astype(np.float32)


def nutrition_fit(catalog: RecipeCatalog, profile: UserProfile) -> np.ndarray:
    """1.0 when a serving hits the dinner kcal target exactly, falling linearly to 0 at +/-100% of the target."""
    target = profile.dinner_kcal_target
    return np.clip(1.0 - np.abs(catalog.kcal - target) / target, 0.0, 1.0).astype(np.float32)


def shortlist(catalog: RecipeCatalog, profile: UserProfile, pantry: list[PantryItem], feasible: np.ndarray,
              preference: np.ndarray, ignore_ids: Collection[int] = (),
              config: ShortlistConfig = ShortlistConfig()) -> np.ndarray:
    """Pick the candidate recipes for the solver. Returns sorted catalogue row indices (all feasible).

    Steps: composite-rank every feasible recipe; take the best ``size``; then top up so that each soon-to-expire
    pantry ingredient has at least ``per_urgent_ingredient`` recipes that use it; finally cap any one cuisine's share.
    """
    feasible_idx = np.flatnonzero(feasible)
    if len(feasible_idx) <= config.size:
        return feasible_idx

    cov = pantry_coverage(catalog, pantry, ignore_ids, config.urgent_within_days)
    composite = (config.w_pantry * cov + config.w_preference * preference
                 + config.w_nutrition * nutrition_fit(catalog, profile))
    composite = np.where(feasible, composite, -np.inf)

    order = np.argsort(-composite, kind="stable")
    chosen: list[int] = []
    cuisine_count: dict[str | None, int] = {}
    cap = max(1, int(config.max_cuisine_share * config.size))
    for idx in order:
        if len(chosen) >= config.size or composite[idx] == -np.inf:
            break
        c = catalog.cuisine[idx]
        if c is not None and cuisine_count.get(c, 0) >= cap:
            continue
        chosen.append(int(idx))
        cuisine_count[c] = cuisine_count.get(c, 0) + 1
    selected = set(chosen)

    # guarantee options for every ingredient that has to be used up soon
    ignore = set(ignore_ids)
    for item in pantry:
        if item.last_use_day is None or item.last_use_day > config.urgent_within_days or item.ingredient_id in ignore:
            continue
        users = catalog.recipes_using(item.ingredient_id)
        users = users[feasible[users]]
        if len(users) == 0:
            continue
        best = users[np.argsort(-composite[users], kind="stable")][: config.per_urgent_ingredient]
        selected.update(int(i) for i in best)

    return np.array(sorted(selected), dtype=np.int64)
