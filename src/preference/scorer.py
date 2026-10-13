"""Content-based preference scoring: how much would *this user* like each recipe?

Role in the system
------------------
The preference scorer turns the user's stated likes and dislikes into one number per recipe in ``[0, 1]`` that the
optimiser minimises ``1 - score`` of. It is **content-based**: it compares what a recipe *contains* (cuisine,
ingredients) with what the user said, so it works for a brand-new user with no history (the MVP situation) and it is
explainable ("matches your liking for Italian food").

What it must never do
---------------------
It scores; it does **not** filter. Safety (allergies, diet) is the hard-rule filter's job (``optimizer.hard_rules``).
A recipe with a disliked ingredient gets a low score but stays eligible - a dislike is a preference, not a prohibition.
(Use ``UserProfile.excluded_ingredient_ids`` for a true "never".)

Formula
-------
    score = clip( 0.5
                  + W_CUISINE   * cuisine_match            (+1 liked cuisine, -1 disliked, 0 otherwise)
                  + W_LIKED     * min(1, liked_hits / 2)   (liked ingredients present, saturating at 2)
                  - W_DISLIKED  * min(1, disliked_hits)    (any disliked ingredient is a strong negative)
                  + W_POPULAR   * (2 * popularity - 1),    0, 1)

``popularity`` is the Bayesian-smoothed Food.com train rating mapped from [3.5, 5] to [0, 1]; unrated recipes get a
neutral 0.5. Its weight is deliberately small: Food.com ratings are heavily skewed (72% are 5 stars), so they carry
little signal beyond "not terrible".

All weights are named constants so they can be tuned on the *validation* scenarios (never on test).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from domain.models import UserProfile
from knowledge.recipes import RecipeCatalog


@dataclass(frozen=True, slots=True)
class PreferenceWeights:
    """Weights of the preference formula. Defaults are hand-set; tune on validation scenarios only."""

    cuisine: float = 0.20
    liked_ingredient: float = 0.25
    disliked_ingredient: float = 0.35
    popularity: float = 0.10
    liked_hits_saturation: float = 2.0     # this many liked ingredients earn the full liked bonus
    rating_prior_strength: float = 5.0     # "m" in the Bayesian average: pseudo-ratings at the global mean
    rating_floor: float = 3.5              # ratings at/below this map to popularity 0
    rating_ceiling: float = 5.0            # ratings at/above this map to popularity 1


DEFAULT_WEIGHTS = PreferenceWeights()


def _hit_counts(catalog: RecipeCatalog, ingredient_ids: Iterable[int]) -> np.ndarray:
    """For each recipe, how many of ``ingredient_ids`` it contains."""
    hits = np.zeros(catalog.n, dtype=np.float32)
    for iid in ingredient_ids:
        hits[catalog.recipes_using(iid)] += 1.0
    return hits


def popularity(catalog: RecipeCatalog, weights: PreferenceWeights = DEFAULT_WEIGHTS) -> np.ndarray:
    """Smoothed, rescaled rating in [0, 1]; 0.5 for unrated recipes. Independent of the user."""
    rated = catalog.n_ratings > 0
    global_mean = float(np.nanmean(catalog.rating_mean[rated])) if rated.any() else 4.0
    m = weights.rating_prior_strength
    mean = np.where(rated, np.nan_to_num(catalog.rating_mean, nan=global_mean), global_mean)
    smoothed = (catalog.n_ratings * mean + m * global_mean) / (catalog.n_ratings + m)
    scaled = (smoothed - weights.rating_floor) / (weights.rating_ceiling - weights.rating_floor)
    pop = np.clip(scaled, 0.0, 1.0)
    return np.where(rated, pop, 0.5).astype(np.float32)


def score_recipes(catalog: RecipeCatalog, profile: UserProfile, ignore_for_likes: Iterable[int] = (),
                  weights: PreferenceWeights = DEFAULT_WEIGHTS) -> np.ndarray:
    """Preference score in [0, 1] for every recipe in the catalogue (higher = better liked).

    Args:
        catalog: the recipe pool.
        profile: the user's likes/dislikes.
        ignore_for_likes: ingredient ids that must not count as a "liked ingredient hit" - pass the assumed-available
            staples (salt, pepper, water) so that liking salt does not boost every recipe.
        weights: formula weights.
    """
    ignore = set(ignore_for_likes)
    liked = [i for i in profile.liked_ingredient_ids if i not in ignore]

    cuisine_match = np.zeros(catalog.n, dtype=np.float32)
    if profile.liked_cuisines or profile.disliked_cuisines:
        for i, c in enumerate(catalog.cuisine):
            if c in profile.liked_cuisines:
                cuisine_match[i] = 1.0
            elif c in profile.disliked_cuisines:
                cuisine_match[i] = -1.0

    liked_term = np.minimum(1.0, _hit_counts(catalog, liked) / weights.liked_hits_saturation)
    disliked_term = np.minimum(1.0, _hit_counts(catalog, profile.disliked_ingredient_ids))
    pop_term = 2.0 * popularity(catalog, weights) - 1.0

    score = (0.5 + weights.cuisine * cuisine_match + weights.liked_ingredient * liked_term
             - weights.disliked_ingredient * disliked_term + weights.popularity * pop_term)
    return np.clip(score, 0.0, 1.0).astype(np.float32)


def disliked_mask(catalog: RecipeCatalog, profile: UserProfile) -> np.ndarray:
    """Recipes the user would be *unhappy* to get: contain a disliked ingredient or are a disliked cuisine.

    Used by the evaluation's "disliked-meal rate" metric; kept next to the scorer so the two cannot drift.
    """
    mask = catalog.mask_using_any(profile.disliked_ingredient_ids)
    if profile.disliked_cuisines:
        mask |= np.array([c in profile.disliked_cuisines for c in catalog.cuisine], dtype=bool)
    return mask
