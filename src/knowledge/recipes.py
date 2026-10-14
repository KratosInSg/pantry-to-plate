"""RecipeCatalog - the dinner recipe pool as fast, read-only numpy structures.

Why not just use DataFrames?
----------------------------
The planning path touches *every* recipe on every request (hard-rule filter, preference score, pantry-coverage score)
and, in the benchmark, does so hundreds of times. Looping over a pandas frame row by row would take seconds per call;
vectorised numpy arrays and an inverted index (ingredient -> recipes that use it) take milliseconds.

Layout
------
Recipes are addressed by a dense **row index** ``idx`` in ``0..n-1`` (sorted by ``recipe_id``). All per-recipe arrays are
aligned to it, so ``catalog.kcal[idx]`` and ``catalog.flag("contains_dairy")[idx]`` are O(1) and boolean masks combine
with plain ``&`` / ``|``. Use ``index_of`` / ``recipe_id_of`` to convert at the boundary - never keep both kinds of id in
the same variable.

Per-serving grams
-----------------
Ingredient quantities are *estimates* (see data/canonical/README.md). The catalogue exposes them as-is together with
``grams_basis`` so callers can tell fitted amounts from prior defaults.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from knowledge.store import DATA_DIR_ENV_VAR, DEFAULT_DATA_DIR
from logging_setup import timed

logger = logging.getLogger(__name__)

# Boolean per-recipe flags available through ``RecipeCatalog.flag``.
FLAG_COLUMNS = (
    "is_vegetarian", "is_vegan", "contains_dairy", "contains_egg", "contains_gluten", "contains_peanut",
    "contains_tree_nut", "contains_soy", "contains_sesame", "contains_fish", "contains_shellfish", "contains_meat",
    "contains_poultry", "contains_pork", "contains_alcohol",
)


# Food.com's "main-dish" tag also covers things nobody plans as dinner ("Easy pasta dough", "Breakfast egg soup"). This
# is a conservative, transparent heuristic for them: a breakfast/brunch tag, or a name that says so. Words such as
# "crusted", "glazed" or "pancakes" are deliberately NOT included (crusted salmon and potato pancakes are dinners).
NON_DINNER_TAGS = frozenset({"breakfast", "brunch"})
NON_DINNER_NAME = re.compile(
    r"\b(dough|batter|frosting|icing|granola|oatmeal|porridge|muffins?|waffles?|french toast|smoothies?|"
    r"breakfast|brunch)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RecipeInfo:
    """One recipe's display/explanation fields (not used in the hot loops)."""

    recipe_id: int
    name: str
    minutes: int
    cuisine: str | None
    tags: tuple[str, ...]
    kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float
    rating_mean: float | None
    n_ratings: int


class RecipeCatalog:
    """Lazy, cached, read-only recipe pool. Create one and share it (``get_default_catalog``)."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or os.environ.get(DATA_DIR_ENV_VAR) or DEFAULT_DATA_DIR)
        if not (self.data_dir / "recipes" / "recipe.parquet").exists():
            raise FileNotFoundError(f"recipe table not found under {self.data_dir}; run the data build first")

    # ------------------------------------------------------------------ loading
    @cached_property
    def _recipes(self) -> pd.DataFrame:
        with timed(logger, "read recipes/recipe.parquet", logging.INFO):     # the largest one-off cost of a session
            return pd.read_parquet(self.data_dir / "recipes" / "recipe.parquet").sort_values("recipe_id").reset_index(drop=True)

    @cached_property
    def n(self) -> int:
        """Number of recipes."""
        return len(self._recipes)

    @cached_property
    def recipe_ids(self) -> np.ndarray:
        """``int64`` array: row index -> Food.com recipe id (sorted ascending)."""
        return self._recipes.recipe_id.to_numpy(dtype=np.int64)

    # ---------------------------------------------------------------- attributes
    @cached_property
    def minutes(self) -> np.ndarray:
        return self._recipes.minutes_total.to_numpy(dtype=np.int32)

    @cached_property
    def kcal(self) -> np.ndarray:
        """Energy per serving (kcal), computed from estimated grams x USDA per 100 g."""
        return self._recipes.kcal_computed.to_numpy(dtype=np.float32)

    @cached_property
    def protein_g(self) -> np.ndarray:
        return self._recipes.protein_g_computed.to_numpy(dtype=np.float32)

    @cached_property
    def fat_g(self) -> np.ndarray:
        return self._recipes.fat_g_computed.to_numpy(dtype=np.float32)

    @cached_property
    def carbohydrate_g(self) -> np.ndarray:
        return self._recipes.carbohydrate_g_computed.to_numpy(dtype=np.float32)

    @cached_property
    def rating_mean(self) -> np.ndarray:
        """Mean train rating (NaN when never rated). Train split only, so it is leakage-safe for evaluation."""
        return self._recipes.rating_mean_train.to_numpy(dtype=np.float32)

    @cached_property
    def n_ratings(self) -> np.ndarray:
        return self._recipes.n_ratings_train.to_numpy(dtype=np.int32)

    @cached_property
    def cuisine(self) -> list[str | None]:
        return [c if isinstance(c, str) else None for c in self._recipes.cuisine]

    @cached_property
    def tags(self) -> list[frozenset[str]]:
        return [frozenset(t) for t in self._recipes.tags]

    @cached_property
    def names(self) -> list[str]:
        return self._recipes["name"].tolist()

    @cached_property
    def non_dinner_like(self) -> np.ndarray:
        """Boolean array: the recipe is tagged or named as breakfast / brunch / dough / batter / icing rather than a
        dinner. A *heuristic* (see ``NON_DINNER_TAGS`` / ``NON_DINNER_NAME``); used only by the opt-in
        ``UserProfile.dinner_only`` hard rule, never by the data build or the frozen benchmark."""
        tagged = np.array([bool(t & NON_DINNER_TAGS) for t in self.tags], dtype=bool)
        named = np.array([bool(NON_DINNER_NAME.search(n)) for n in self.names], dtype=bool)
        return tagged | named

    @cached_property
    def _flags(self) -> dict[str, np.ndarray]:
        return {c: self._recipes[c].to_numpy(dtype=bool) for c in FLAG_COLUMNS}

    def flag(self, name: str) -> np.ndarray:
        """Boolean array for one of ``FLAG_COLUMNS`` (e.g. ``"contains_dairy"``)."""
        try:
            return self._flags[name]
        except KeyError:
            raise KeyError(f"unknown recipe flag {name!r}; expected one of {FLAG_COLUMNS}") from None

    # --------------------------------------------------------------- ingredients
    @cached_property
    def _ingredient_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(ingredient_ids, grams, offsets): CSR-style flat arrays; recipe ``i`` owns ``[offsets[i]:offsets[i+1]]``."""
        with timed(logger, "read recipes/recipe_ingredient.parquet", logging.INFO):
            ri = pd.read_parquet(self.data_dir / "recipes" / "recipe_ingredient.parquet",
                                 columns=["recipe_id", "ingredient_id", "grams_per_serving"])
        ri = ri.sort_values("recipe_id", kind="stable")
        # offsets by searching the sorted recipe ids of ``ri`` for each catalogue recipe id
        rid = ri.recipe_id.to_numpy()
        offsets = np.searchsorted(rid, self.recipe_ids, side="left")
        offsets = np.append(offsets, len(rid))
        return (ri.ingredient_id.to_numpy(dtype=np.int32), ri.grams_per_serving.to_numpy(dtype=np.float32), offsets)

    @cached_property
    def flat(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(owner_idx, ingredient_ids, grams)``: every recipe-ingredient row as three parallel flat arrays.

        This is the vectorisation hook: compute something per row (e.g. "grams the pantry can cover") with plain numpy,
        then reduce to per-recipe values with ``np.bincount(owner_idx, weights=..., minlength=catalog.n)``.
        """
        ids, grams, off = self._ingredient_arrays
        owner = np.repeat(np.arange(self.n, dtype=np.int32), np.diff(off))
        return owner, ids, grams

    def ingredients(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        """``(ingredient_ids, grams_per_serving)`` of recipe row ``idx`` (parallel arrays, no duplicates)."""
        ids, grams, off = self._ingredient_arrays
        return ids[off[idx]:off[idx + 1]], grams[off[idx]:off[idx + 1]]

    @cached_property
    def _inverted_index(self) -> dict[int, np.ndarray]:
        ids, _, off = self._ingredient_arrays
        owner = np.repeat(np.arange(self.n, dtype=np.int32), np.diff(off))     # recipe idx of every flat row
        order = np.argsort(ids, kind="stable")
        sorted_ids, sorted_owner = ids[order], owner[order]
        boundaries = np.flatnonzero(np.diff(sorted_ids)) + 1
        starts = np.concatenate(([0], boundaries))
        return {int(sorted_ids[s]): sorted_owner[s:e] for s, e in zip(starts, np.append(boundaries, len(sorted_ids)))}

    def recipes_using(self, ingredient_id: int) -> np.ndarray:
        """Row indices of every recipe that contains ``ingredient_id`` (empty array if none)."""
        return self._inverted_index.get(int(ingredient_id), np.empty(0, dtype=np.int32))

    def mask_using_any(self, ingredient_ids) -> np.ndarray:
        """Boolean mask: recipes containing at least one of ``ingredient_ids``."""
        mask = np.zeros(self.n, dtype=bool)
        for iid in ingredient_ids:
            mask[self.recipes_using(iid)] = True
        return mask

    # ------------------------------------------------------------------ lookups
    @cached_property
    def _id_to_index(self) -> dict[int, int]:
        return {int(r): i for i, r in enumerate(self.recipe_ids)}

    def index_of(self, recipe_id: int) -> int:
        """Row index of a Food.com recipe id. Raises ``KeyError`` for an unknown id."""
        return self._id_to_index[int(recipe_id)]

    def recipe_id_of(self, idx: int) -> int:
        return int(self.recipe_ids[idx])

    @cached_property
    def _steps(self) -> dict[int, tuple[str, ...]]:
        """recipe_id -> cooking instructions, loaded on first use (they are for display only, never for planning)."""
        path = self.data_dir / "recipes" / "recipe_step.parquet"
        if not path.exists():
            logger.warning("no %s: recipes will be shown without cooking steps", path.name)
            return {}
        with timed(logger, "read recipes/recipe_step.parquet"):
            df = pd.read_parquet(path)
        return {int(r): tuple(str(s) for s in steps) for r, steps in zip(df.recipe_id, df.steps)}

    def steps(self, idx: int) -> tuple[str, ...]:
        """Cooking instructions of recipe row ``idx``, in order. Empty if the step table is missing or has none.

        Food.com text, lower-case and as written by its contributors; the caller capitalises for display.
        """
        return self._steps.get(int(self.recipe_ids[idx]), ())

    def info(self, idx: int) -> RecipeInfo:
        """Display fields for one recipe (slow path; use arrays in loops)."""
        rm = self.rating_mean[idx]
        return RecipeInfo(
            recipe_id=int(self.recipe_ids[idx]), name=self.names[idx], minutes=int(self.minutes[idx]),
            cuisine=self.cuisine[idx], tags=tuple(sorted(self.tags[idx])), kcal=float(self.kcal[idx]),
            protein_g=float(self.protein_g[idx]), fat_g=float(self.fat_g[idx]),
            carbohydrate_g=float(self.carbohydrate_g[idx]),
            rating_mean=None if np.isnan(rm) else float(rm), n_ratings=int(self.n_ratings[idx]))


@lru_cache(maxsize=1)
def get_default_catalog() -> RecipeCatalog:
    """Process-wide shared catalogue for the default dataset."""
    return RecipeCatalog()
