"""Hard rules: which recipes are *allowed at all* for this user. Never relaxed, never traded off.

Role in the system
------------------
Runs before scoring and before the solver. Everything it removes is removed for good - the optimiser's cost terms
cannot buy a violation back. This is the "constraint safety: must be zero" metric of the evaluation, so the logic is
kept small, explicit and explainable: every exclusion can be traced to a named rule (``Rule`` below), which the explainer
turns into "excluded because it violates your peanut allergy".

Rules (a recipe must pass ALL)
------------------------------
=================  ==========================================================================================
rule               passes when
=================  ==========================================================================================
diet               omnivore: always; pescatarian: no meat and no poultry; vegetarian: ``is_vegetarian`` (no meat,
                   poultry, fish, shellfish, gelatin **or eggs**; dairy is fine); vegan: ``is_vegan``
allergen:<name>    the recipe's ``contains_<name>`` flag is False, for every allergen in the profile
pork               ``avoid_pork`` is off, or the recipe has no pork product
alcohol            ``avoid_alcohol`` is off, or the recipe has no alcohol
excluded           no ingredient from ``profile.excluded_ingredient_ids``
excluded_recipe    the recipe is not in ``profile.excluded_recipe_ids`` (a dinner the user rejected)
time               ``max_total_minutes`` unset, or the recipe is not longer
not_dinner         ``dinner_only`` is off, or the recipe is not breakfast/brunch/dough/batter/icing-like (a name
                   and tag heuristic: ``RecipeCatalog.non_dinner_like``)
=================  ==========================================================================================

What is *not* a hard rule here
------------------------------
* Known use-by dates: a scheduling constraint over days, handled by the optimiser and the inventory accounting.
* Weekday cooking-time limit and dislikes: soft, so they are costs, not filters.

Honesty about coverage
----------------------
The flags come from conservative keyword rules over canonical ingredients (see data/canonical/README.md). They do not
know about hidden allergens inside branded products. "Zero violations" is therefore *relative to the knowledge base*.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from domain.models import Diet, UserProfile, RESTRICTABLE_FOOD_FLAGS
from knowledge.recipes import RecipeCatalog


@dataclass(frozen=True, slots=True)
class Rule:
    """One named hard rule and a human-readable reason a recipe breaks it."""

    name: str          # e.g. "diet:vegetarian", "allergen:peanut", "excluded"
    reason: str        # e.g. "contains meat, fish or egg, which a vegetarian diet excludes"


def _diet_violation_mask(catalog: RecipeCatalog, diet: Diet) -> np.ndarray | None:
    """Boolean mask of recipes that VIOLATE the diet (None when the diet imposes nothing)."""
    if diet is Diet.OMNIVORE:
        return None
    if diet is Diet.PESCATARIAN:
        return catalog.flag("contains_meat") | catalog.flag("contains_poultry")
    if diet is Diet.VEGETARIAN:
        return ~catalog.flag("is_vegetarian")
    return ~catalog.flag("is_vegan")          # vegan


def violation_masks(catalog: RecipeCatalog, profile: UserProfile) -> dict[str, np.ndarray]:
    """One boolean "violates" mask per active rule, keyed by rule name.

    Kept separate from ``feasible_mask`` so the same arrays serve both the filter and the explanations/metrics.
    """
    masks: dict[str, np.ndarray] = {}
    diet = _diet_violation_mask(catalog, profile.diet)
    if diet is not None:
        masks[f"diet:{profile.diet.value}"] = diet
    for allergen in sorted(profile.allergens):
        masks[f"allergen:{allergen}"] = catalog.flag(f"contains_{allergen}")
    for group in sorted(profile.excluded_food_groups):
        masks[f"food_group:{group}"] = catalog.flag(RESTRICTABLE_FOOD_FLAGS[group])
    if profile.avoid_pork:
        masks["pork"] = catalog.flag("contains_pork")
    if profile.avoid_alcohol:
        masks["alcohol"] = catalog.flag("contains_alcohol")
    if profile.excluded_ingredient_ids:
        masks["excluded"] = catalog.mask_using_any(profile.excluded_ingredient_ids)
    if profile.excluded_recipe_ids:
        rejected = np.zeros(catalog.n, dtype=bool)
        for recipe_id in profile.excluded_recipe_ids:
            try:
                rejected[catalog.index_of(recipe_id)] = True
            except KeyError:             # not in the dinner pool, so it can never be planned anyway
                continue
        masks["excluded_recipe"] = rejected
    if profile.max_total_minutes is not None:
        masks["time"] = catalog.minutes > profile.max_total_minutes
    if profile.dinner_only:
        masks["not_dinner"] = catalog.non_dinner_like
    return masks


def feasible_mask(catalog: RecipeCatalog, profile: UserProfile) -> np.ndarray:
    """Boolean mask over the catalogue: ``True`` = the recipe passes every hard rule for this user."""
    ok = np.ones(catalog.n, dtype=bool)
    for violates in violation_masks(catalog, profile).values():
        ok &= ~violates
    return ok


def violated_rules(catalog: RecipeCatalog, profile: UserProfile, idx: int) -> list[Rule]:
    """Every hard rule recipe ``idx`` breaks for this profile (empty list = safe). For explanations and metrics."""
    out: list[Rule] = []
    for name, mask in violation_masks(catalog, profile).items():
        if mask[idx]:
            out.append(Rule(name, _REASONS.get(name.split(":")[0], "violates a hard rule")
                            .format(detail=name.split(":")[-1])))
    return out


_REASONS = {
    "food_group": "contains {detail}, which the user explicitly excludes",
    "diet": "is not compatible with a {detail} diet",
    "allergen": "contains {detail}, which is on the user's allergy list",
    "pork": "contains pork, which the user avoids",
    "alcohol": "contains alcohol, which the user avoids",
    "excluded": "contains an ingredient the user never eats",
    "excluded_recipe": "is a dinner the user rejected",
    "time": "takes longer than the user's maximum cooking time",
    "not_dinner": "looks like a breakfast dish, dough, batter or icing rather than a dinner",
}


def ingredient_violations(flags: Mapping[str, object], ingredient_id: int, profile: UserProfile) -> list[str]:
    """Names of the hard rules a *single ingredient* would break for this profile (empty list = safe).

    The ingredient-level twin of :func:`violation_masks`, with the same rule names. Recipes are filtered with the
    recipe flags; this is for an ingredient that enters a dinner *after* the recipe was allowed - a substitute
    (``optimizer.substitutions``) - which must pass the same rules or the substitution would smuggle a violation in.

    Args:
        flags: the ingredient's row of ``ingredient.parquet`` (any mapping with the ``contains_*``, ``is_vegetarian``
            and ``is_vegan`` columns).
        ingredient_id: its id (for ``excluded_ingredient_ids``).
        profile: the user.
    """
    out: list[str] = []
    diet = profile.diet
    if ((diet is Diet.PESCATARIAN and (bool(flags["contains_meat"]) or bool(flags["contains_poultry"])))
            or (diet is Diet.VEGETARIAN and not bool(flags["is_vegetarian"]))
            or (diet is Diet.VEGAN and not bool(flags["is_vegan"]))):
        out.append(f"diet:{diet.value}")
    out += [f"allergen:{a}" for a in sorted(profile.allergens) if bool(flags[f"contains_{a}"])]
    out += [f"food_group:{g}" for g in sorted(profile.excluded_food_groups)
            if bool(flags[RESTRICTABLE_FOOD_FLAGS[g]])]
    if profile.avoid_pork and bool(flags["contains_pork"]):
        out.append("pork")
    if profile.avoid_alcohol and bool(flags["contains_alcohol"]):
        out.append("alcohol")
    if ingredient_id in profile.excluded_ingredient_ids:
        out.append("excluded")
    return out


def count_violations(catalog: RecipeCatalog, profile: UserProfile, recipe_indices) -> int:
    """Number of (meal, rule) violations in a plan. The evaluation's *constraint safety* metric: must be zero."""
    masks = violation_masks(catalog, profile)
    return int(sum(int(mask[i]) for i in recipe_indices for mask in masks.values()))
