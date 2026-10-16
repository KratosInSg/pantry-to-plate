"""Preferences from a rating history: turn dishes a user rated into the profile fields the scorer already reads.

Role in the system
------------------
The slide's preference model "learns from meal ratings and accepted / rejected recommendations". This module is that
step, without a trained model: given the dishes a user rated (in our canonical-ingredient vocabulary), it derives

* ``liked_ingredient_ids`` / ``liked_cuisines`` - the *existing* ``UserProfile`` fields, so the scorer, the optimiser and
  the explainer use the result unchanged ("plug and play"), and
* graded content-based scores of every catalogue recipe against the dishes the user liked - no fitting either:
  :func:`history_similarity` (closeness to the *average* liked dish, ingredients only) and
  :func:`nearest_dish_scores` (closeness to the user's *nearest* liked dishes, ingredients and tags; keeps mixed tastes
  apart). They are evaluated on real users in ``evaluation/taste_eval.py``. ``preference.scorer`` uses
  :func:`nearest_dish_scores` for a profile's ``rated_dinners``, and :func:`nearest_rated` names the closest liked
  dinners in explanations.

It works for any rating source whose dishes can be expressed as canonical ingredients: the MealRec (Allrecipes) users
of the real-taste evaluation (``evaluation/taste_users.py``) today; the app's own "how did it go?" marks later.

How a like is derived (pure counting, no fitting)
-------------------------------------------------
Only dishes rated ``>= LIKE_MIN_RATING`` count. For each ingredient: *support* = share of the user's liked dishes that
contain it; *base rate* = share of a reference pool of dishes (e.g. every MealRec main dish) that contain it;
*lift* = support / base rate. An ingredient is liked when it is common in the user's dishes (support) **and** more
common than for people in general (lift) - so garlic and onion, which are in almost everyone's dinners, do not become
everyone's "likes". Cuisines work the same way, restricted to the catalogue's cuisine vocabulary. Every derived like
keeps its evidence (:class:`LikeEvidence`) so an explanation can say *why* ("in 31 % of the dinners you rated highly,
2.4 x the usual rate").

Limits
------
* **Likes only.** Dislikes would need low ratings; the MealRec data has none (every rating is 4 or 5), so dislikes are
  not derived. A history with low ratings simply ignores them.
* Assumed-available staples (salt, pepper, water) are never likes: they would boost every recipe.
* The thresholds are declared constants, chosen before the evaluation was run; tune them on *validation* users only.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np
from scipy import sparse
from scipy.stats import rankdata

from knowledge.recipes import RecipeCatalog

# 5-star scale: 4 and 5 are "liked" (Food.com and Allrecipes both use it; MealRec keeps only 4s and 5s).
LIKE_MIN_RATING = 4


@dataclass(frozen=True, slots=True)
class HistoryConfig:
    """Thresholds for turning a history into likes. Declared before evaluation; tune on validation users only."""

    min_dishes: int = 10                  # fewer liked dishes than this is too little evidence: derive nothing
    min_support: float = 0.15             # an ingredient must be in >= 15 % of the user's liked dishes ...
    min_lift: float = 1.5                 # ... and >= 1.5 x as common as in the reference pool
    max_liked_ingredients: int = 10       # strongest by support; the scorer's liked bonus saturates at 2 hits anyway
    min_cuisine_support: float = 0.10     # cuisines are sparse labels (about half of dishes carry one)
    min_cuisine_lift: float = 1.5
    max_liked_cuisines: int = 3


DEFAULT_CONFIG = HistoryConfig()


@dataclass(frozen=True, slots=True)
class RatedDish:
    """One dish a user rated, expressed in our vocabulary."""

    ingredient_ids: frozenset[int]        # canonical ingredient ids (unmapped ingredients are simply absent)
    cuisines: frozenset[str]              # cuisine labels from the catalogue's vocabulary (may be empty)
    rating: int                           # 1-5
    tags: frozenset[str] = frozenset()    # recipe tags in the catalogue's tag vocabulary (dish type, protein, ...)


class Rated(Protocol):
    """Anything that describes a rated dish this way: :class:`RatedDish` here, ``domain.models.RatedDinner`` in a
    ``UserProfile``. The functions below only read these attributes."""

    @property
    def ingredient_ids(self) -> frozenset[int]: ...
    @property
    def cuisines(self) -> frozenset[str]: ...
    @property
    def rating(self) -> int: ...
    @property
    def tags(self) -> frozenset[str]: ...


@dataclass(frozen=True, slots=True)
class LikeEvidence:
    """Why something was derived as a like."""

    kind: str                             # "ingredient" | "cuisine"
    key: int | str                        # ingredient id or cuisine name
    support: float                        # share of the user's liked dishes containing it
    base_rate: float                      # share of the reference pool containing it
    lift: float                           # support / base_rate


@dataclass(frozen=True)
class DerivedLikes:
    """What a history says the user likes. Empty sets when the history is too short (``n_liked_dishes`` says so)."""

    liked_ingredient_ids: frozenset[int]
    liked_cuisines: frozenset[str]
    evidence: tuple[LikeEvidence, ...]
    n_liked_dishes: int


@dataclass(frozen=True)
class BaseRates:
    """Share of a reference pool of dishes containing each ingredient / cuisine. Unseen keys have rate 0."""

    ingredient: dict[int, float]
    cuisine: dict[str, float]
    n_dishes: int


def base_rates(pool: Sequence[Rated]) -> BaseRates:
    """Base rates over ``pool`` (e.g. every MealRec main dish). Ratings are ignored: this is "people in general"."""
    n = len(pool)
    if n == 0:
        return BaseRates({}, {}, 0)
    ing = Counter(i for d in pool for i in d.ingredient_ids)
    cui = Counter(c for d in pool for c in d.cuisines)
    return BaseRates({i: k / n for i, k in ing.items()}, {c: k / n for c, k in cui.items()}, n)


def _select(counts: Counter, n: int, rates: dict, min_support: float, min_lift: float, limit: int, kind: str
            ) -> list[LikeEvidence]:
    out: list[LikeEvidence] = []
    for key, k in counts.items():
        support = k / n
        base = rates.get(key, 0.0)
        # never seen in the reference pool: no base rate to compare against, so it cannot show a lift
        if base <= 0.0 or support < min_support:
            continue
        lift = support / base
        if lift >= min_lift:
            out.append(LikeEvidence(kind, key, support, base, lift))
    # strongest evidence first; the key breaks ties so the result never depends on dict order
    out.sort(key=lambda e: (-e.support, -e.lift, str(e.key)))
    return out[:limit]


def derive_likes(history: Iterable[Rated], rates: BaseRates, ignore_ids: Collection[int] = (),
                 cuisine_vocabulary: Collection[str] | None = None, config: HistoryConfig = DEFAULT_CONFIG
                 ) -> DerivedLikes:
    """Liked ingredients and cuisines from a rating history (module docstring).

    Args:
        history: the user's rated dishes, any order.
        rates: base rates of the reference pool the lift is measured against.
        ignore_ids: assumed-available staples; never derived as likes.
        cuisine_vocabulary: cuisine names the catalogue knows; others are ignored (``None`` = keep all).
        config: thresholds.

    Returns:
        The likes and their evidence. Fewer than ``config.min_dishes`` liked dishes derives nothing (empty sets),
        with ``n_liked_dishes`` saying how many there were.
    """
    liked = [d for d in history if d.rating >= LIKE_MIN_RATING]
    n = len(liked)
    if n < config.min_dishes:
        return DerivedLikes(frozenset(), frozenset(), (), n)
    ignore = set(ignore_ids)
    ing = Counter(i for d in liked for i in d.ingredient_ids if i not in ignore)
    cui = Counter(c for d in liked for c in d.cuisines
                  if cuisine_vocabulary is None or c in cuisine_vocabulary)
    ing_ev = _select(ing, n, rates.ingredient, config.min_support, config.min_lift, config.max_liked_ingredients,
                     "ingredient")
    cui_ev = _select(cui, n, rates.cuisine, config.min_cuisine_support, config.min_cuisine_lift,
                     config.max_liked_cuisines, "cuisine")
    return DerivedLikes(frozenset(int(e.key) for e in ing_ev), frozenset(str(e.key) for e in cui_ev),
                        tuple(ing_ev + cui_ev), n)


# ==================================================================================================================
# graded methods: how close is each catalogue recipe to what the user liked?
# ==================================================================================================================
@dataclass(frozen=True, slots=True)
class NearestConfig:
    """Settings of :func:`nearest_dish_scores`. Chosen on the validation real-taste users (2026-10-16); the test users
    were run once afterwards with exactly these values (``md docs/evaluation.md``)."""

    k: int = 10                           # how many of the user's most similar past dinners vouch for a recipe
    tag_weight: float = 0.5               # share of the score from tags (dish type, protein, cuisine); rest ingredients


DEFAULT_NEAREST = NearestConfig()


@dataclass(frozen=True)
class _Space:
    """Catalogue recipes as unit-length, IDF-weighted binary vectors over one vocabulary (ingredients or tags)."""

    unit: sparse.csr_matrix               # n_recipes x n_columns, rows of length 1 (or 0 for an empty recipe)
    idf: np.ndarray                       # per column
    column: dict                          # vocabulary key -> column
    idf_unknown: float                    # IDF of a key no catalogue recipe has (it still counts in a dish's length)


def _idf(df: np.ndarray, n: int) -> np.ndarray:
    """Smoothed inverse document frequency: rare ingredients say more about taste than ubiquitous ones."""
    return np.log((1.0 + n) / (1.0 + df)) + 1.0


def _space(rows: np.ndarray, keys: list, n: int) -> _Space:
    columns = {key: c for c, key in enumerate(sorted(set(keys)))}
    cols = np.array([columns[k] for k in keys], dtype=np.int64)
    binary = sparse.csr_matrix((np.ones(len(cols)), (rows, cols)), shape=(n, len(columns)))
    binary.data[:] = 1.0                                        # a recipe lists an ingredient / tag once; be safe
    idf = _idf(np.asarray((binary > 0).sum(axis=0)).ravel(), n)
    weighted = binary.multiply(idf).tocsr()
    norms = np.sqrt(np.asarray(weighted.multiply(weighted).sum(axis=1)).ravel())
    unit = sparse.diags(np.where(norms > 0, 1.0 / np.where(norms > 0, norms, 1.0), 0.0)) @ weighted
    return _Space(unit.tocsr(), idf, columns, float(_idf(np.zeros(1), n)[0]))


@lru_cache(maxsize=4)
def _ingredient_space(catalog: RecipeCatalog, ignore: frozenset[int]) -> _Space:
    owner, ids, _ = catalog.flat
    keep = ~np.isin(ids, np.array(sorted(ignore), dtype=ids.dtype))
    return _space(owner[keep], ids[keep].tolist(), catalog.n)


@lru_cache(maxsize=4)
def _tag_space(catalog: RecipeCatalog) -> _Space:
    pairs = [(r, t) for r, tags in enumerate(catalog.tags) for t in sorted(tags)]
    rows = np.array([r for r, _ in pairs], dtype=np.int64)
    return _space(rows, [t for _, t in pairs], catalog.n)


def _dish_vectors(space: _Space, dishes: Sequence[Collection]) -> tuple[np.ndarray, list[dict]]:
    """``(vectors, unknown)``: each dish's IDF-weighted vector over ``space``'s columns, divided by the dish's *full*
    length. Keys no catalogue recipe has still make a dish longer, so a dish mostly made of unknown ingredients is not
    mistaken for a close match. ``unknown`` holds each dish's weight on those keys (needed for exact norms)."""
    vectors = np.zeros((len(dishes), space.unit.shape[1]))
    unknown: list[dict] = []
    for k, keys in enumerate(dishes):
        known = [space.column[key] for key in keys if key in space.column]
        n_unknown = sum(1 for key in keys if key not in space.column)
        length = float(np.sqrt(np.sum(space.idf[known] ** 2) + n_unknown * space.idf_unknown ** 2))
        if length > 0:
            vectors[k, known] = space.idf[known] / length
        unknown.append({key: space.idf_unknown / length for key in keys if key not in space.column} if length else {})
    return vectors, unknown


def history_similarity(catalog: RecipeCatalog, history: Iterable[Rated], ignore_ids: Collection[int] = ()
                       ) -> np.ndarray:
    """Cosine similarity in ``[0, 1]`` between each catalogue recipe and the user's liked dishes (their average).

    Both sides are binary ingredient vectors weighted by the catalogue's IDF (staples dropped); the user vector is
    the mean of their liked dishes' normalised vectors. All zeros when no liked dish has a known ingredient.
    """
    ignore = frozenset(int(i) for i in ignore_ids)
    space = _ingredient_space(catalog, ignore)
    dishes = [[i for i in d.ingredient_ids if i not in ignore] for d in history if d.rating >= LIKE_MIN_RATING]
    vectors, unknown = _dish_vectors(space, [d for d in dishes if d])
    user = vectors.sum(axis=0) if len(vectors) else np.zeros(space.unit.shape[1])
    leftover: Counter = Counter()
    for weights in unknown:
        leftover.update(weights)
    norm = float(np.sqrt(np.sum(user ** 2) + sum(w ** 2 for w in leftover.values())))
    if norm == 0.0 or not user.any():
        return np.zeros(catalog.n, dtype=np.float32)
    return np.asarray(space.unit @ (user / norm)).ravel().astype(np.float32)


def _top_k_mean(similarities: np.ndarray, k: int) -> np.ndarray:
    """Per row, the mean of the ``k`` largest values (all of them when there are fewer)."""
    k = min(k, similarities.shape[1])
    return np.partition(similarities, similarities.shape[1] - k, axis=1)[:, -k:].mean(axis=1)


def _percentile(values: np.ndarray) -> np.ndarray:
    """Rank of each value in ``(0, 1]`` (ties share their average rank): puts differently scaled scores on one scale."""
    return rankdata(values, method="average") / len(values)


def nearest_dish_scores(catalog: RecipeCatalog, history: Iterable[Rated], ignore_ids: Collection[int] = (),
                        config: NearestConfig = DEFAULT_NEAREST) -> np.ndarray:
    """Preference in ``[0, 1]`` for every catalogue recipe: how close it is to the user's *nearest* liked dinners.

    Each liked dish is kept separate, so a user who likes both Mexican and Italian food is not blurred into one
    average (that is :func:`history_similarity`): a recipe scores the mean cosine to its ``config.k`` most similar
    liked dishes, once over ingredients and once over tags (dish type, main protein, cuisine; IDF-weighted). The two
    are put on one scale by percentile rank over the catalogue and mixed with ``config.tag_weight``.

    Returns all zeros when no liked dish has a known ingredient or tag. When only one kind of evidence exists (e.g. a
    history without tags), it alone gives the score - a stated rule, not a silent fallback. The values are ranks, so
    only their order is meaningful.
    """
    ignore = frozenset(int(i) for i in ignore_ids)
    liked = [d for d in history if d.rating >= LIKE_MIN_RATING]
    parts: list[tuple[float, np.ndarray]] = []
    for weight, space, keys in (
            (1.0 - config.tag_weight, _ingredient_space(catalog, ignore),
             [[i for i in d.ingredient_ids if i not in ignore] for d in liked]),
            (config.tag_weight, _tag_space(catalog), [sorted(d.tags) for d in liked])):
        known = [k for k in keys if any(key in space.column for key in k)]
        if weight <= 0 or not known:
            continue
        vectors, _ = _dish_vectors(space, known)
        similarities = np.asarray((space.unit @ vectors.T))
        parts.append((weight, _percentile(_top_k_mean(similarities, config.k))))
    if not parts:
        return np.zeros(catalog.n, dtype=np.float32)
    total = sum(w for w, _ in parts)
    return (sum(w * part for w, part in parts) / total).astype(np.float32)


def nearest_rated(catalog: RecipeCatalog, history: Sequence[Rated], recipe_idx: int, ignore_ids: Collection[int] = (),
                  config: NearestConfig = DEFAULT_NEAREST, n: int = 2) -> tuple[tuple[int, float], ...]:
    """The liked dishes of ``history`` closest to catalogue recipe ``recipe_idx`` - what an explanation names.

    Returns up to ``n`` ``(position in history, similarity)`` pairs, closest first, similarity > 0 only (empty when
    nothing liked is similar). The similarity mixes the same two cosines :func:`nearest_dish_scores` ranks by,
    ``(1 - tag_weight)`` x ingredients + ``tag_weight`` x tags, so the dishes named are the ones that pulled the
    recipe's score up.
    """
    ignore = frozenset(int(i) for i in ignore_ids)
    liked = [(pos, d) for pos, d in enumerate(history) if d.rating >= LIKE_MIN_RATING]
    if not liked:
        return ()
    total = np.zeros(len(liked))
    for weight, space, keys in (
            (1.0 - config.tag_weight, _ingredient_space(catalog, ignore),
             [[i for i in d.ingredient_ids if i not in ignore] for _, d in liked]),
            (config.tag_weight, _tag_space(catalog), [sorted(d.tags) for _, d in liked])):
        if weight <= 0:
            continue
        vectors, _ = _dish_vectors(space, keys)
        total += weight * np.asarray(space.unit[recipe_idx] @ vectors.T).ravel()
    order = sorted(range(len(liked)), key=lambda k: (-total[k], liked[k][0]))   # ties: earlier in the history first
    return tuple((liked[k][0], float(total[k])) for k in order[:n] if total[k] > 0)


def as_profile_fields(likes: DerivedLikes) -> dict[str, frozenset]:
    """The ``UserProfile`` fields to set: ``profile.model_copy(update=as_profile_fields(likes))``."""
    return {"liked_ingredient_ids": likes.liked_ingredient_ids, "liked_cuisines": likes.liked_cuisines}


__all__ = ["LIKE_MIN_RATING", "HistoryConfig", "DEFAULT_CONFIG", "NearestConfig", "DEFAULT_NEAREST", "RatedDish",
           "Rated", "LikeEvidence", "DerivedLikes", "BaseRates", "base_rates", "derive_likes", "history_similarity",
           "nearest_dish_scores", "nearest_rated", "as_profile_fields"]
