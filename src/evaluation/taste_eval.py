"""Does a real person's rating history, turned into preferences, predict the dinners they go on to enjoy?

The check
---------
For each frozen real-taste user (``evaluation/taste_users.py``): their earliest rated dinners become preferences, the
catalogue is scored with each method below, and their *later* liked dinners that exist in our catalogue (the held-out
positives) are looked up in that ranking. Nothing the user rated later is used to build their preferences.

=====================  ===========================================================================================
method                 what scores the catalogue
=====================  ===========================================================================================
random                 random numbers (seeded): the chance level every other row must be read against
popularity             today's scorer for a user who states nothing: only the Food.com rating prior moves the score
derived_likes          today's scorer, unchanged, with ``liked_ingredient_ids`` / ``liked_cuisines`` derived from the
                       history - the "plug and play" route
history_similarity     closeness to the user's *average* liked dinner (ingredients) - ``preference.history``
nearest_dishes         closeness to the user's *nearest* liked dinners, ingredients + tags - ``preference.history``
scorer_with_history    the production path: today's scorer with the history in ``UserProfile.rated_dinners`` (its
                       history term is ``nearest_dishes``, next to the popularity prior). Added after the single test
                       run, so it is reported on validation users only
=====================  ===========================================================================================

Metrics (per held-out dinner, averaged per user, then over users; paired across methods on the same users)
------------------------------------------------------------------------------------------------------------
* **HR@K / NDCG@K** - the protocol of the MealRec paper (Li et al., 2022, Section 5.1.1): each held-out dinner is ranked
  against ``N_NEGATIVES`` = 99 recipes the user never rated, sampled at random (seeded; the same for every method).
  HR@K = it is in the top K of those 100; NDCG@K also credits a higher place (1 / log2(rank + 1)). Chance level:
  HR@10 = 0.10. Ties are broken at random, so a method with no information scores chance in expectation.
* **AUC** - the full-ranking counterpart: probability that a held-out dinner outranks a random catalogue recipe the
  user never rated (0.5 = chance). Stricter than sampled metrics, which can flatter every method and even reorder them
  (Krichene & Rendle, KDD 2020), so it is reported next to them.
* **recall@1 %** - share of held-out dinners in the top 1 % of the full ranking (about 540 of 54,000 recipes).

Caveats: unrated is not disliked (negatives are only "never rated"); held-out positives are the dinners whose name
matches a catalogue recipe exactly, which favours classic dishes. Compare methods on the same users, against random.

Usage::

    python src/evaluation/taste_eval.py --split validation
    python src/evaluation/taste_eval.py --split test          # once, after the method and its settings are fixed
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Collection, Sequence
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/taste_eval.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from domain.models import UserProfile
from evaluation.metrics import paired_bootstrap
from domain.models import RatedDinner
from evaluation.taste_users import (DEFAULT_TASTE_DIR, TasteRecipe, TasteUser, linked_heldout, load_taste_recipes,
                                    load_taste_users, rated_dinners, rated_dishes)
from logging_setup import configure_logging
from optimizer.planning import PlanningContext, make_context
from preference.history import (DEFAULT_CONFIG, DEFAULT_NEAREST, BaseRates, HistoryConfig, NearestConfig, RatedDish,
                                as_profile_fields, base_rates, derive_likes, history_similarity, nearest_dish_scores)
from preference.scorer import score_recipes

logger = logging.getLogger(__name__)

METHODS: tuple[str, ...] = ("random", "popularity", "derived_likes", "history_similarity", "nearest_dishes",
                            "scorer_with_history")
BASELINE = "popularity"
TOP_SHARE = 0.01                 # recall cut-off: the top 1 % of the ranked catalogue
N_NEGATIVES = 99                 # sampled never-rated recipes per held-out dinner (MealRec paper, Section 5.1.1)
KS: tuple[int, ...] = (5, 10)    # the paper reports @5 and @10
SEED = 20261016                  # negatives and tie-breaks; the same negatives for every method of a user
METRICS: tuple[str, ...] = ("hr_5", "ndcg_5", "hr_10", "ndcg_10", "auc", "recall_at_top")


def rank_metrics(scores: np.ndarray, positives: Collection[int], exclude: Collection[int] = (),
                 top_share: float = TOP_SHARE) -> tuple[float, float]:
    """``(auc, recall_at_top)`` of the ``positives`` (catalogue row indices) within ``scores``.

    Negatives are every row that is neither a positive nor in ``exclude`` (the user's history: known, not unknown).
    Ties count half, so a method that scores everything equally gets exactly 0.5.

    Raises:
        ValueError: no positives, or no negatives left.
    """
    pos = np.array(sorted(set(positives)), dtype=np.int64)
    if len(pos) == 0:
        raise ValueError("no held-out positives to rank")
    neg_mask = np.ones(len(scores), dtype=bool)
    neg_mask[pos] = False
    neg_mask[np.array(sorted(set(exclude)), dtype=np.int64)] = False
    neg = np.sort(scores[neg_mask])
    if len(neg) == 0:
        raise ValueError("no negatives left to rank against")
    s = scores[pos]
    below = np.searchsorted(neg, s, side="left")
    ties = np.searchsorted(neg, s, side="right") - below
    auc = float(np.mean((below + 0.5 * ties) / len(neg)))
    # rank among negatives + positives; a positive's rank is 1 + candidates strictly above it + half the ties
    candidates = np.sort(scores[neg_mask | np.isin(np.arange(len(scores)), pos)])
    above = len(candidates) - np.searchsorted(candidates, s, side="right")
    tied = np.searchsorted(candidates, s, side="right") - np.searchsorted(candidates, s, side="left") - 1
    k = max(1, int(round(top_share * len(candidates))))
    recall = float(np.mean(1 + above + 0.5 * tied <= k))
    return auc, recall


def sample_negatives(n_rows: int, positives: Collection[int], exclude: Collection[int], rng: np.random.Generator,
                     n_negatives: int = N_NEGATIVES) -> dict[int, np.ndarray]:
    """For each positive, ``n_negatives`` distinct rows that are neither positives nor excluded (seeded ``rng``).

    Raises:
        ValueError: fewer candidate rows than ``n_negatives``.
    """
    allowed = np.ones(n_rows, dtype=bool)
    allowed[list(set(positives) | set(exclude))] = False
    pool = np.flatnonzero(allowed)
    if len(pool) < n_negatives:
        raise ValueError(f"only {len(pool)} candidate negatives, {n_negatives} needed")
    return {p: rng.choice(pool, size=n_negatives, replace=False) for p in sorted(positives)}


def sampled_metrics(scores: np.ndarray, negatives: dict[int, np.ndarray], rng: np.random.Generator,
                    ks: Sequence[int] = KS) -> dict[str, float]:
    """HR@K and NDCG@K of each positive ranked among its sampled negatives, averaged over the positives.

    The rank is 1 + negatives scoring strictly higher + a uniformly random share of the ties (from ``rng``), so a
    constant score gets chance-level results in expectation instead of an arbitrary best or worst case.
    """
    hits = {k: [] for k in ks}
    gains = {k: [] for k in ks}
    for positive, neg in negatives.items():
        higher = int((scores[neg] > scores[positive]).sum())
        tied = int((scores[neg] == scores[positive]).sum())
        rank = 1 + higher + int(rng.integers(0, tied + 1))
        for k in ks:
            hits[k].append(float(rank <= k))
            gains[k].append(1.0 / np.log2(rank + 1) if rank <= k else 0.0)
    return {**{f"hr_{k}": float(np.mean(hits[k])) for k in ks}, **{f"ndcg_{k}": float(np.mean(gains[k])) for k in ks}}


def _scores(method: str, user_id: int, likes_profile: UserProfile, history: list[RatedDish],
            dinners: tuple[RatedDinner, ...], ctx: PlanningContext, nearest: NearestConfig) -> np.ndarray:
    cat = ctx.catalog
    if method == "scorer_with_history":
        return score_recipes(cat, UserProfile(rated_dinners=dinners), ignore_for_likes=ctx.ignore_ids,
                             weights=ctx.preference_weights)
    if method == "random":
        return np.random.default_rng([SEED, user_id, 2]).random(cat.n)
    if method == "history_similarity":
        return history_similarity(cat, history, ctx.ignore_ids)
    if method == "nearest_dishes":
        return nearest_dish_scores(cat, history, ctx.ignore_ids, nearest)
    profile = likes_profile if method == "derived_likes" else UserProfile()
    return score_recipes(cat, profile, ignore_for_likes=ctx.ignore_ids, weights=ctx.preference_weights)


def evaluate_user(user: TasteUser, recipes: dict[int, TasteRecipe], rates: BaseRates, ctx: PlanningContext,
                  config: HistoryConfig = DEFAULT_CONFIG, nearest: NearestConfig = DEFAULT_NEAREST,
                  methods: Sequence[str] = METHODS) -> list[dict]:
    """One row per method for one user (empty when the user has no linked held-out dinner)."""
    cat = ctx.catalog
    positives = {cat.index_of(cid) for cid in linked_heldout(user, recipes)}
    if not positives:
        return []
    seen = {cat.index_of(cid) for r in user.history if (cid := recipes[r.recipe_id].catalogue_recipe_id) is not None}
    history = rated_dishes(user.history, recipes)
    dinners = rated_dinners(user.history, recipes)
    likes = derive_likes(history, rates, ctx.ignore_ids, {c for c in cat.cuisine if c}, config)
    likes_profile = UserProfile(**as_profile_fields(likes))
    negatives = sample_negatives(cat.n, positives, seen, np.random.default_rng([SEED, user.user_id, 0]))
    rows = []
    for m, method in enumerate(methods):
        scores = np.asarray(_scores(method, user.user_id, likes_profile, history, dinners, ctx, nearest), dtype=float)
        auc, recall = rank_metrics(scores, positives, seen)
        sampled = sampled_metrics(scores, negatives, np.random.default_rng([SEED, user.user_id, 1, m]))
        rows.append({"user_id": user.user_id, "method": method, "n_heldout": len(positives), **sampled, "auc": auc,
                     "recall_at_top": recall, "n_liked_ingredients": len(likes.liked_ingredient_ids),
                     "n_liked_cuisines": len(likes.liked_cuisines)})
    return rows


def rated_dishes_of_pool(recipes: dict[int, TasteRecipe]) -> list[RatedDish]:
    """Every MealRec main dish as an unrated reference dish (the "people in general" pool for base rates)."""
    return [RatedDish(frozenset(r.ingredient_ids), frozenset(r.cuisines), 0, frozenset(r.tags))
            for r in recipes.values()]


def run_taste_eval(split: str = "validation", eval_dir: Path = DEFAULT_TASTE_DIR, ctx: PlanningContext | None = None,
                   config: HistoryConfig = DEFAULT_CONFIG, nearest: NearestConfig = DEFAULT_NEAREST,
                   limit: int | None = None, methods: Sequence[str] = METHODS) -> pd.DataFrame:
    """Evaluate ``methods`` on the frozen users of ``split``. One row per (user, method)."""
    ctx = ctx or make_context()
    recipes = load_taste_recipes(eval_dir)
    users = load_taste_users(split, eval_dir)
    users = users[:limit] if limit else users
    rates = base_rates(rated_dishes_of_pool(recipes))
    rows = [row for user in users for row in evaluate_user(user, recipes, rates, ctx, config, nearest, methods)]
    logger.info("taste evaluation: %d %s users, %d rows", len(users), split, len(rows))
    return pd.DataFrame(rows)


def compare(df: pd.DataFrame, baseline: str = BASELINE, metrics: Sequence[str] = ("hr_10", "ndcg_10", "auc")
            ) -> pd.DataFrame:
    """Paired ``method - baseline`` difference per metric with a 95 % bootstrap CI (users resampled)."""
    paired = df.rename(columns={"user_id": "scenario_id", "method": "planner"})
    rows = []
    for method in [m for m in dict.fromkeys(df.method) if m != baseline]:
        row: dict[str, object] = {"method": method}
        for metric in metrics:
            r = paired_bootstrap(paired, metric, method, baseline, higher_is_better=True)
            row[metric] = f"{r['mean_diff']:+.3f} [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}]"
        row["better_users_hr_10"] = round(paired_bootstrap(paired, "hr_10", method, baseline,
                                                           higher_is_better=True)["share_a_better"], 2)
        rows.append(row)
    return pd.DataFrame(rows).set_index("method")


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """Mean of every metric per method (users weighted equally), with HR@10 as a multiple of random when present."""
    table = df.groupby("method", sort=False)[list(METRICS)].mean()
    if "random" in table.index and table.loc["random", "hr_10"] > 0:
        table["hr_10_x_random"] = table["hr_10"] / table.loc["random", "hr_10"]
    return table.round(3)


def report(df: pd.DataFrame) -> None:
    pd.set_option("display.width", 220)
    print(f"\n=== {df.user_id.nunique()} users, {int(df.groupby('user_id').n_heldout.first().sum())} held-out dinners: "
          f"mean per user (HR@10 chance = 0.10, AUC chance = 0.5) ===")
    print(summary(df).to_string())
    likes = df[df.method == "derived_likes"]
    if len(likes):
        print(f"\nderived likes per user: {likes.n_liked_ingredients.mean():.1f} ingredients, "
              f"{likes.n_liked_cuisines.mean():.1f} cuisines")
    print(f"\n=== paired difference vs '{BASELINE}' [95% bootstrap CI] ===")
    print(compare(df).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["validation", "test"], default="validation")
    ap.add_argument("--eval-dir", type=Path, default=DEFAULT_TASTE_DIR)
    ap.add_argument("--save", type=Path, default=None, help="write the per-user rows to this CSV")
    ap.add_argument("--log-level", default=None)
    args = ap.parse_args()
    configure_logging(args.log_level)
    if args.split == "test":
        print("!! TEST USERS: run this once, after the method and its settings are fixed. Never tune on it. !!")
    df = run_taste_eval(args.split, args.eval_dir)
    report(df)
    if args.save:
        df.to_csv(args.save, index=False)
        print("saved", args.save)


if __name__ == "__main__":
    main()
