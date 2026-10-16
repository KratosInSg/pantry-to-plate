"""Real-taste users: 100 MealRec (Allrecipes) users whose ratings stand in for "we suggested, they rated".

Why this exists
---------------
The planning benchmark's users are synthetic: their likes are drawn at random, so "preference quality" there only
measures how well the optimiser follows likes we invented. MealRec (Li et al., 2022, "MealRec: A Meal Recommendation
Dataset"; raw files in ``data/mealRecResearchpaper_Data/``) holds real people's ratings of real dinners. This module
turns a sample of them into a small, frozen set of *real-taste users*:

* each user's **earliest** ``HISTORY_DISHES`` rated main dishes play the part of "the dinners we suggested and they
  rated" - the input ``preference.history`` turns into likes;
* their **later** main-dish ratings are held out to check whether those likes predict what they went on to enjoy.

The split is by date, never random: building a profile from the same ratings it is judged on would be circular.

What the data is (and is not)
-----------------------------
* **Likes only.** MealRec keeps only 4- and 5-star interactions, so there are no dislikes to learn from.
* **Not our recipes.** MealRec ids are Allrecipes ids. Dishes are bridged to our vocabulary through their
  *ingredients* (resolved to canonical ingredients exactly as pantry text is) and their *tags* (Allrecipes uses the
  same cuisine tag names as Food.com). A held-out dish can only be ranked in our catalogue if its name matches exactly
  one catalogue recipe (``catalogue_recipe_id``); ambiguous names are not linked.
* **A simulation.** These people chose and rated these dishes on Allrecipes; nobody rated a suggestion of ours.

Freezing
--------
Like the planning benchmark: built once (``python src/evaluation/taste_users.py``), written with SHA-256 hashes in
``FROZEN.json`` and re-verified on every load; users are split 50/50 into validation and test *before* anything is
tuned. Never tune on the test users. Everything is a pure function of the raw files, the dataset and ``SEED``.

Versions: ``v1`` (dinners as ingredients + cuisines). ``v2`` adds each dinner's tags in the catalogue's tag vocabulary
(dish type, main protein, cuisine...), for :func:`preference.history.nearest_dish_scores`. The users, their history /
held-out split and the validation / test split are the same in both - same raw files, rules and seed (tested).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/taste_users.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from domain.models import RatedDinner
from knowledge.recipes import RecipeCatalog
from knowledge.store import KnowledgeStore
from logging_setup import configure_logging
from nlp.pantry_parser import PantryParser
from nlp.resolver import IngredientResolver, normalise_name
from nlp.schemas import MatchStatus
from preference.history import RatedDish

logger = logging.getLogger(__name__)

TASTE_VERSION = "v2"
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = _ROOT / "data" / "mealRecResearchpaper_Data"
DEFAULT_TASTE_DIR = _ROOT / "data" / "evaluation" / f"taste_{TASTE_VERSION}"
RECIPE_FILE, RATING_FILE = "recipe.csv", "user_recipe.csv"

MAIN_CATEGORY = "main-dish"      # MealRec's label for dinners; appetizers and desserts are not what we plan
N_USERS = 100
MIN_MAIN_RATINGS = 100           # users with at least this many rated main dishes qualify (111 of 1,575 do)
HISTORY_DISHES = 80              # earliest N rated dinners = the "suggested and rated" input; the rest is held out
MIN_HELDOUT_LINKED = 3           # a user needs this many held-out dinners that are in our catalogue to be checkable
VALIDATION_SHARE = 0.5
SEED = 20261016


class TasteRecipe(BaseModel):
    """One MealRec main dish in our vocabulary."""

    recipe_id: int                                   # MealRec / Allrecipes id
    name: str
    ingredient_ids: list[int] = Field(default_factory=list)   # canonical ids; unmapped ingredient text is absent
    cuisines: list[str] = Field(default_factory=list)          # tags that are catalogue cuisine names
    catalogue_recipe_id: int | None = None           # the Food.com recipe with exactly this name, if exactly one
    tags: list[str] = Field(default_factory=list)    # tags in the catalogue's tag vocabulary (v2+; empty in v1)


class TasteRating(BaseModel):
    recipe_id: int
    rating: int
    date: str                                        # ISO timestamp of the review's last modification


class TasteUser(BaseModel):
    """A MealRec user: the dinners that form their profile, and the later ones held out to check it."""

    user_id: int                                     # MealRec user id (already public in the MealRec release)
    history: list[TasteRating]
    heldout: list[TasteRating]


@dataclass(frozen=True)
class TasteSet:
    recipes: list[TasteRecipe]
    users: list[TasteUser]
    split: dict[str, list[int]]
    stats: dict[str, float | int] = field(default_factory=dict)


# ==================================================================================================================
# recipes: ingredient text -> canonical ingredients, tags -> cuisines, name -> catalogue recipe
# ==================================================================================================================
def map_ingredient_texts(texts: Iterable[str], resolver: IngredientResolver, parser: PantryParser
                         ) -> dict[str, tuple[int, ...]]:
    """Canonical ingredient ids for each distinct ingredient text.

    The resolver is tried on the whole text first (keeps names like "half and half" or "cream cheese" whole); if it
    is not confident, the pantry parser strips preparation words ("minced fresh ginger root") and may split a
    compound ("diced tomatoes with garlic and onion"). Texts neither understands map to ``()``.
    """
    out: dict[str, tuple[int, ...]] = {}
    for text in sorted(set(texts)):
        res = resolver.resolve(text)
        if res.status is MatchStatus.MATCHED and res.ingredient_ids:
            out[text] = tuple(res.ingredient_ids)
            continue
        parsed = parser.parse(text)
        ids = [i.ingredient_id for i in parsed.items
               if i.ingredient_id is not None and i.match_status is MatchStatus.MATCHED]
        out[text] = tuple(dict.fromkeys(ids))
    return out


def catalogue_names(catalog: RecipeCatalog) -> dict[str, int | None]:
    """Normalised catalogue recipe name -> Food.com recipe id, or ``None`` when several recipes share the name."""
    out: dict[str, int | None] = {}
    for idx, name in enumerate(catalog.names):
        key = normalise_name(name)
        out[key] = None if key in out else int(catalog.recipe_id_of(idx))
    return out


def build_recipes(raw: pd.DataFrame, store: KnowledgeStore, catalog: RecipeCatalog
                  ) -> tuple[list[TasteRecipe], dict[str, float | int]]:
    """Main dishes of ``raw`` (MealRec ``recipe.csv`` columns) in our vocabulary, plus mapping statistics."""
    mains = raw[raw.category == MAIN_CATEGORY].sort_values("recipe_id")
    texts = {rid: [t.strip() for t in str(s).split("^") if t.strip()]
             for rid, s in zip(mains.recipe_id, mains.ingredients.fillna(""))}
    resolver = IngredientResolver(store)
    mapping = map_ingredient_texts((t for ts in texts.values() for t in ts), resolver,
                                   PantryParser(store=store, resolver=resolver))
    vocabulary = {c for c in catalog.cuisine if c}
    tag_vocabulary = {t for tags in catalog.tags for t in tags}
    names = catalogue_names(catalog)

    recipes: list[TasteRecipe] = []
    n_mentions = n_mapped = n_ambiguous = n_tag_mentions = n_tags_kept = 0
    for rid, name, tags in zip(mains.recipe_id, mains.recipe_name, mains.tags.fillna("")):
        ids: list[int] = []
        for t in texts[int(rid)]:
            n_mentions += 1
            n_mapped += bool(mapping[t])
            ids += mapping[t]
        key = normalise_name(str(name))
        n_ambiguous += key in names and names[key] is None
        raw_tags = {t for t in str(tags).split(";") if t}
        kept = sorted(raw_tags & tag_vocabulary)
        n_tag_mentions += len(raw_tags)
        n_tags_kept += len(kept)
        recipes.append(TasteRecipe(
            recipe_id=int(rid), name=str(name), ingredient_ids=sorted(set(ids)),
            cuisines=sorted({t for t in raw_tags if t in vocabulary}),
            catalogue_recipe_id=names.get(key), tags=kept))
    stats = {"n_main_dishes": len(recipes),
             "ingredient_mentions_mapped_share": round(n_mapped / max(1, n_mentions), 4),
             "main_dishes_linked_to_catalogue": sum(r.catalogue_recipe_id is not None for r in recipes),
             "main_dishes_with_ambiguous_catalogue_name": int(n_ambiguous),
             "main_dishes_with_a_cuisine": sum(bool(r.cuisines) for r in recipes),
             "tag_mentions_in_catalogue_vocabulary_share": round(n_tags_kept / max(1, n_tag_mentions), 4),
             "main_dishes_with_a_catalogue_tag": sum(bool(r.tags) for r in recipes)}
    return recipes, stats


# ==================================================================================================================
# users: who qualifies, the temporal split, the sample
# ==================================================================================================================
def _ratings_frame(raw: pd.DataFrame, recipe_ids: set[int]) -> pd.DataFrame:
    df = raw[raw.recipe_id.isin(recipe_ids)].copy()
    df["date"] = pd.to_datetime(df.dateLastModified.astype(str).str.strip(), format="mixed")
    return df.sort_values(["user_id", "date", "recipe_id"], kind="stable")


def split_user(rows: pd.DataFrame, history_dishes: int = HISTORY_DISHES) -> tuple[list[TasteRating], list[TasteRating]]:
    """(history, held-out) of one user's rated main dishes: the earliest ``history_dishes`` by date, then the rest."""
    ratings = [TasteRating(recipe_id=int(r), rating=int(s), date=d.isoformat())
               for r, s, d in zip(rows.recipe_id, rows.rating, rows.date)]
    return ratings[:history_dishes], ratings[history_dishes:]


def linked_heldout(user: TasteUser, recipes: dict[int, TasteRecipe]) -> set[int]:
    """Catalogue recipe ids of the user's held-out dinners, minus any their history already links to (no leakage)."""
    seen = {recipes[r.recipe_id].catalogue_recipe_id for r in user.history}
    return {cid for r in user.heldout
            if (cid := recipes[r.recipe_id].catalogue_recipe_id) is not None and cid not in seen}


def select_users(raw_ratings: pd.DataFrame, recipes: Sequence[TasteRecipe], n_users: int = N_USERS,
                 min_main_ratings: int = MIN_MAIN_RATINGS, history_dishes: int = HISTORY_DISHES,
                 min_heldout_linked: int = MIN_HELDOUT_LINKED, seed: int = SEED
                 ) -> tuple[list[TasteUser], dict[str, int]]:
    """Qualifying users (enough rated dinners, enough checkable held-out ones), then a seeded sample of ``n_users``.

    Raises:
        ValueError: fewer than ``n_users`` users qualify (change a threshold deliberately; never silently take fewer).
    """
    if history_dishes >= min_main_ratings:
        raise ValueError("history_dishes must leave held-out dinners: it must be below min_main_ratings")
    by_id = {r.recipe_id: r for r in recipes}
    df = _ratings_frame(raw_ratings, set(by_id))
    counts = df.groupby("user_id").size()
    candidates = sorted(int(u) for u in counts[counts >= min_main_ratings].index)
    qualifying: list[TasteUser] = []
    for uid in candidates:
        history, heldout = split_user(df[df.user_id == uid], history_dishes)
        user = TasteUser(user_id=uid, history=history, heldout=heldout)
        if len(linked_heldout(user, by_id)) >= min_heldout_linked:
            qualifying.append(user)
    if len(qualifying) < n_users:
        raise ValueError(f"only {len(qualifying)} users qualify (>= {min_main_ratings} main dishes, >= "
                         f"{min_heldout_linked} linked held-out); asked for {n_users}")
    rng = np.random.default_rng(seed)
    chosen = sorted(rng.choice(len(qualifying), size=n_users, replace=False).tolist())
    stats = {"users_with_enough_main_dishes": len(candidates), "users_qualifying": len(qualifying)}
    return [qualifying[i] for i in chosen], stats


def split_users(users: Sequence[TasteUser], validation_share: float = VALIDATION_SHARE, seed: int = SEED
                ) -> dict[str, list[int]]:
    """``{"validation": [user ids], "test": [user ids]}``; deterministic given ``seed``."""
    ids = sorted(u.user_id for u in users)
    rng = np.random.default_rng([seed, 1])
    rng.shuffle(ids)
    cut = int(round(len(ids) * validation_share))
    return {"validation": sorted(ids[:cut]), "test": sorted(ids[cut:])}


def build_taste_set(raw_dir: Path, store: KnowledgeStore, catalog: RecipeCatalog, n_users: int = N_USERS,
                    seed: int = SEED) -> TasteSet:
    """Read the raw MealRec files and build the whole set (not yet written)."""
    raw_recipes = pd.read_csv(raw_dir / RECIPE_FILE, usecols=["recipe_id", "recipe_name", "category", "ingredients",
                                                               "tags"])
    raw_ratings = pd.read_csv(raw_dir / RATING_FILE)
    recipes, recipe_stats = build_recipes(raw_recipes, store, catalog)
    users, user_stats = select_users(raw_ratings, recipes, n_users=n_users, seed=seed)
    logger.info("taste set: %d main dishes (%d linked to the catalogue), %d users of %d qualifying",
                len(recipes), recipe_stats["main_dishes_linked_to_catalogue"], len(users),
                user_stats["users_qualifying"])
    return TasteSet(recipes, users, split_users(users, seed=seed), {**recipe_stats, **user_stats})


# ==================================================================================================================
# freeze / load
# ==================================================================================================================
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def freeze_taste_set(taste: TasteSet, out_dir: Path = DEFAULT_TASTE_DIR, raw_dir: Path | None = None) -> Path:
    """Write recipes, users, split and ``FROZEN.json`` (hashes). Refuses to overwrite a frozen set."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen = out_dir / "FROZEN.json"
    if frozen.exists():
        raise FileExistsError(f"{frozen} already exists: the taste set is frozen. Bump TASTE_VERSION for a new one.")
    files = {f"recipes_{TASTE_VERSION}.jsonl": "\n".join(r.model_dump_json() for r in taste.recipes) + "\n",
             f"users_{TASTE_VERSION}.jsonl": "\n".join(u.model_dump_json() for u in taste.users) + "\n",
             f"split_{TASTE_VERSION}.json": json.dumps(taste.split, indent=1) + "\n"}
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    sources = {}
    if raw_dir is not None:
        sources = {name: _sha256(raw_dir / name) for name in (RECIPE_FILE, RATING_FILE) if (raw_dir / name).exists()}
    meta = {"version": TASTE_VERSION, "created": date.today().isoformat(), "seed": SEED,
            "changes": "v2 = v1 + each dinner's tags in the catalogue tag vocabulary; same users and splits",
            "source": "MealRec (Li et al., 2022), user_recipe.csv + recipe.csv; https://github.com/WUT-IDEA/MealRec",
            "source_sha256": sources,
            "thresholds": {"n_users": len(taste.users), "min_main_ratings": MIN_MAIN_RATINGS,
                           "history_dishes": HISTORY_DISHES, "min_heldout_linked": MIN_HELDOUT_LINKED,
                           "validation_share": VALIDATION_SHARE},
            "stats": taste.stats,
            "files": {name: _sha256(out_dir / name) for name in files}}
    frozen.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8", newline="\n")
    return frozen


def _verified(eval_dir: Path) -> dict:
    meta = json.loads((eval_dir / "FROZEN.json").read_text(encoding="utf-8"))
    for name, expected in meta["files"].items():
        if _sha256(eval_dir / name) != expected:
            raise RuntimeError(f"{name} does not match FROZEN.json - the frozen taste set has been modified")
    return meta


def load_taste_recipes(eval_dir: Path = DEFAULT_TASTE_DIR) -> dict[int, TasteRecipe]:
    """Every MealRec main dish of the frozen set, by MealRec recipe id (hashes verified first)."""
    meta = _verified(eval_dir)
    with open(eval_dir / f"recipes_{meta['version']}.jsonl", encoding="utf-8") as fh:
        recipes = [TasteRecipe.model_validate_json(line) for line in fh if line.strip()]
    return {r.recipe_id: r for r in recipes}


def load_taste_users(split: str, eval_dir: Path = DEFAULT_TASTE_DIR) -> list[TasteUser]:
    """The ``"validation"`` or ``"test"`` users (hashes verified first)."""
    if split not in ("validation", "test"):
        raise ValueError("split must be 'validation' or 'test'")
    meta = _verified(eval_dir)
    ids = set(json.loads((eval_dir / f"split_{meta['version']}.json").read_text(encoding="utf-8"))[split])
    with open(eval_dir / f"users_{meta['version']}.jsonl", encoding="utf-8") as fh:
        users = [TasteUser.model_validate_json(line) for line in fh if line.strip()]
    return [u for u in users if u.user_id in ids]


def rated_dishes(ratings: Iterable[TasteRating], recipes: dict[int, TasteRecipe]) -> list[RatedDish]:
    """A user's ratings as ``preference.history.RatedDish`` objects (with tags from a v2+ set)."""
    return [RatedDish(frozenset(recipes[r.recipe_id].ingredient_ids), frozenset(recipes[r.recipe_id].cuisines),
                      r.rating, frozenset(recipes[r.recipe_id].tags)) for r in ratings]


def rated_dinners(ratings: Iterable[TasteRating], recipes: dict[int, TasteRecipe]) -> tuple[RatedDinner, ...]:
    """A user's ratings as ``domain.models.RatedDinner`` - exactly what a ``UserProfile`` carries in the app.

    ``recipe_id`` is the linked catalogue recipe when there is one (the dish is "one of ours"), else ``None``.
    """
    return tuple(RatedDinner(rating=r.rating, name=recipes[r.recipe_id].name,
                             recipe_id=recipes[r.recipe_id].catalogue_recipe_id,
                             ingredient_ids=frozenset(recipes[r.recipe_id].ingredient_ids),
                             tags=frozenset(recipes[r.recipe_id].tags), cuisines=frozenset(recipes[r.recipe_id].cuisines))
                 for r in ratings)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_TASTE_DIR)
    ap.add_argument("--log-level", default=None)
    args = ap.parse_args()
    configure_logging(args.log_level)
    if (args.out_dir / "FROZEN.json").exists():
        sys.exit(f"{args.out_dir} is already frozen; bump TASTE_VERSION to build a new taste set")
    from knowledge.recipes import get_default_catalog
    from knowledge.store import get_default_store
    taste = build_taste_set(args.raw_dir, get_default_store(), get_default_catalog())
    print("frozen:", freeze_taste_set(taste, args.out_dir, args.raw_dir))
    print(json.dumps(taste.stats, indent=1))


if __name__ == "__main__":
    main()
