"""KnowledgeStore - read-only, typed access to the curated dataset in ``data/canonical/``.

Where this sits in the pipeline
-------------------------------
The offline build (``src/knowledge/build``) turns raw downloads into Parquet tables. At run time *every* module
(NLP, hard-rule filter, preference scorer, optimiser, explainer) reads the dataset through this class instead of
opening Parquet files itself. That gives us one place that knows the file layout, caches the tables, and applies
the small lookup policies (which unit weight to prefer, which shelf-life row is the default).

What it deliberately does NOT do
--------------------------------
No planning, no scoring, no parsing. It answers "what do we know about ingredient 123?", nothing more.

Design notes
------------
* Tables are loaded lazily (first use) and cached on the instance, so importing this module is free and a unit test
  that only needs ingredient names does not pay for loading 500K recipe rows.
* The store never mutates data. Everything it returns is an immutable dataclass or a plain value.
* "Not found" is ``None`` / an empty tuple, never an exception, because missing knowledge is a normal situation
  (a user can type an ingredient we have never seen). Callers must decide what to do and should record the guess.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

import pandas as pd

# The project root is two levels above this file: <root>/src/knowledge/store.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "canonical"
DATA_DIR_ENV_VAR = "PTP_DATA_DIR"  # lets tests / deployments point at another build of the dataset

# Alias sources that are trustworthy enough to be *fuzzy-match candidates*. Raw Food.com strings are noisy
# (brand names, long marketing phrases), so a raw alias only qualifies if it was seen often.
_FUZZY_SOURCES = {"canonical", "foodcom_canonical", "synonym", "generated_variant"}
_FUZZY_MIN_RAW_OCCURRENCES = 5

# When several portions exist for one unit (e.g. "each": small / medium / large) which size represents
# "one onion" when the user did not say? Medium first: it is the USDA reference size for produce.
_SIZE_PREFERENCE = (None, "medium", "regular", "large", "small", "xlarge", "xsmall", "jumbo", "miniature")

# Units that mean "one whole item" for a food, in priority order. Used for "half a cabbage" / "three eggs".
_WHOLE_ITEM_UNITS = ("each", "head", "bunch", "bulb", "loaf", "stalk", "fillet", "breast", "steak", "ear", "piece",
                     "roll", "patty", "can", "package")


@dataclass(frozen=True, slots=True)
class IngredientInfo:
    """Identity and classification of one canonical ingredient."""

    ingredient_id: int
    canonical_name: str
    food_group: str                    # dairy | meat | vegetable | herb_spice | ... (see data/canonical/README.md)
    fdc_id: int | None                 # USDA FoodData Central id this ingredient is nutritionally mapped to
    is_assumed_available: bool         # water / salt / pepper: assumed present in every kitchen (configurable)
    is_vegetarian: bool
    is_vegan: bool
    allergens: frozenset[str]          # subset of {dairy, egg, gluten, peanut, tree_nut, soy, sesame, fish, shellfish}
    n_recipes_foodcom: int             # popularity: recipes mentioning it in the full Food.com corpus


@dataclass(frozen=True, slots=True)
class UnitWeight:
    """Grams in one household unit of one ingredient (e.g. 1 cup of flour = 125 g)."""

    unit: str                          # cup | tbsp | tsp | each | clove | slice | can | head | ...
    size: str | None                   # small | medium | large ... (meaningful for unit == "each")
    grams: float
    source: str                        # usda_portion | derived_volume | group_median  (how trustworthy)


@dataclass(frozen=True, slots=True)
class ShelfLife:
    """The default FoodKeeper-based storage estimate for an ingredient. An estimate, never a use-by date."""

    storage: str                       # pantry | refrigerator | freezer
    min_days: float | None
    max_days: float | None
    confidence: str                    # high (curated) | medium (lexical) | low (category fallback)
    source: str                        # foodkeeper | foodkeeper_tip | indefinite_cap | category_median
    is_indefinite: bool


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    """A physical unit from reference/unit_conversion.csv (mass in grams, volume in millilitres)."""

    unit: str                          # canonical unit name, e.g. "tbsp"
    kind: str                          # "mass" | "volume"
    to_base: float                     # multiply a quantity by this to get grams (mass) or ml (volume)


class KnowledgeStore:
    """Lazy, cached, read-only view of ``data/canonical``. Create one and share it."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or os.environ.get(DATA_DIR_ENV_VAR) or DEFAULT_DATA_DIR)
        if not self.data_dir.exists():
            raise FileNotFoundError(
                f"Dataset directory not found: {self.data_dir}. Build it with "
                f"`python src/knowledge/build/run_all.py` or set {DATA_DIR_ENV_VAR}.")

    # ------------------------------------------------------------------ loading
    def _read(self, relative: str) -> pd.DataFrame:
        return pd.read_parquet(self.data_dir / relative)

    @cached_property
    def _ingredients(self) -> pd.DataFrame:
        return self._read("ingredients/ingredient.parquet").set_index("ingredient_id", drop=False)

    @cached_property
    def _aliases(self) -> pd.DataFrame:
        return self._read("ingredients/ingredient_alias.parquet")

    @cached_property
    def _unit_weights(self) -> dict[int, tuple[UnitWeight, ...]]:
        df = self._read("ingredients/ingredient_unit_weight.parquet")
        out: dict[int, list[UnitWeight]] = {}
        for r in df.itertuples(index=False):
            size = r.size if isinstance(r.size, str) else None
            out.setdefault(int(r.ingredient_id), []).append(
                UnitWeight(unit=r.unit, size=size, grams=float(r.grams_per_unit), source=r.source))
        return {k: tuple(v) for k, v in out.items()}

    @cached_property
    def _nutrition(self) -> pd.DataFrame:
        return self._read("nutrition/ingredient_nutrition_per100g.parquet").set_index("ingredient_id")

    @cached_property
    def _shelf_life_default(self) -> pd.DataFrame:
        sl = self._read("shelf_life/ingredient_shelf_life.parquet")
        return sl[sl.is_default].drop_duplicates("ingredient_id").set_index("ingredient_id")

    # -------------------------------------------------------------- ingredients
    @cached_property
    def _name_to_id(self) -> dict[str, int]:
        return {n: int(i) for n, i in zip(self._ingredients.canonical_name, self._ingredients.index)}

    def ingredient(self, ingredient_id: int) -> IngredientInfo | None:
        """Return the ingredient's identity/classification, or ``None`` for an unknown id."""
        try:
            r = self._ingredients.loc[int(ingredient_id)]
        except KeyError:
            return None
        allergen_cols = {"dairy": "contains_dairy", "egg": "contains_egg", "gluten": "contains_gluten",
                         "peanut": "contains_peanut", "tree_nut": "contains_tree_nut", "soy": "contains_soy",
                         "sesame": "contains_sesame", "fish": "contains_fish", "shellfish": "contains_shellfish"}
        return IngredientInfo(
            ingredient_id=int(r.ingredient_id), canonical_name=r.canonical_name, food_group=r.food_group,
            fdc_id=None if pd.isna(r.fdc_id) else int(r.fdc_id),
            is_assumed_available=bool(r.is_assumed_available),
            is_vegetarian=bool(r.is_vegetarian), is_vegan=bool(r.is_vegan),
            allergens=frozenset(a for a, c in allergen_cols.items() if bool(r[c])),
            n_recipes_foodcom=int(r.n_recipes_foodcom))

    def all_ingredients(self) -> pd.DataFrame:
        """The whole ingredient table as a DataFrame copy (columns as in ``ingredient.parquet``).

        For generators and analysis that need to sample over *all* ingredients; request-time code should use
        ``ingredient()`` / ``ingredient_by_name()``.
        """
        return self._ingredients.copy()

    def ingredient_by_name(self, canonical_name: str) -> IngredientInfo | None:
        """Look an ingredient up by its exact canonical name (e.g. ``"cheddar cheese"``)."""
        iid = self._name_to_id.get(canonical_name)
        return self.ingredient(iid) if iid is not None else None

    # ------------------------------------------------------------------ aliases
    @cached_property
    def _alias_to_ids(self) -> dict[str, tuple[int, ...]]:
        grouped = self._aliases.groupby("alias").ingredient_id.apply(lambda s: tuple(sorted(int(i) for i in s)))
        return grouped.to_dict()

    def lookup_alias(self, text: str) -> tuple[int, ...]:
        """Exact (already-normalised, lower-case) alias -> ingredient ids.

        Usually one id. Two or more means the alias is a deliberate split such as "salt and pepper".
        An empty tuple means we have never seen this spelling.
        """
        return self._alias_to_ids.get(text, ())

    @cached_property
    def fuzzy_candidates(self) -> tuple[tuple[str, ...], tuple[tuple[int, ...], ...]]:
        """(aliases, ids) restricted to spellings reliable enough to fuzzy-match against.

        Returned as two parallel tuples so they can be handed straight to ``rapidfuzz.process``.
        """
        a = self._aliases
        keep = a.alias_source.isin(_FUZZY_SOURCES) | (a.n_occurrences >= _FUZZY_MIN_RAW_OCCURRENCES)
        names = sorted(set(a.loc[keep, "alias"]))
        return tuple(names), tuple(self._alias_to_ids[n] for n in names)

    @cached_property
    def connector_phrases(self) -> frozenset[str]:
        """Known aliases that contain " and " / " & " ("salt and pepper", "half and half").

        The text segmenter must not split a pantry list inside these phrases.
        """
        return frozenset(a for a in self._alias_to_ids if " and " in a or " & " in a)

    # ------------------------------------------------------------- unit weights
    def unit_weights(self, ingredient_id: int) -> tuple[UnitWeight, ...]:
        """Every household-unit weight known for the ingredient (possibly empty)."""
        return self._unit_weights.get(int(ingredient_id), ())

    def unit_weight(self, ingredient_id: int, unit: str, size: str | None = None) -> UnitWeight | None:
        """Grams for one ``unit`` of the ingredient, honouring ``size`` when given.

        If ``size`` is None (the user said "an onion", not "a large onion") we prefer the generic row, then the
        medium row. If a size is requested but missing, we fall back to the same preference order rather than
        returning nothing: an approximate weight is more useful than none, and the weight's ``source`` is kept.
        """
        rows = [w for w in self.unit_weights(ingredient_id) if w.unit == unit]
        if not rows:
            return None
        order = (size,) + _SIZE_PREFERENCE if size else _SIZE_PREFERENCE
        for wanted in order:
            for w in rows:
                if w.size == wanted:
                    return w
        return rows[0]

    def whole_item_weight(self, ingredient_id: int) -> UnitWeight | None:
        """Weight of "one of it" (one egg, one head of cabbage, one onion) or ``None`` if unknown.

        Walks ``_WHOLE_ITEM_UNITS`` in priority order and returns the first unit the ingredient has data for.
        """
        for unit in _WHOLE_ITEM_UNITS:
            w = self.unit_weight(ingredient_id, unit)
            if w is not None:
                return w
        return None

    # ----------------------------------------------------------- units (physical)
    @cached_property
    def unit_definitions(self) -> dict[str, UnitDefinition]:
        """Alias -> physical unit, from ``reference/unit_conversion.csv`` ("tablespoons" -> tbsp, 14.79 ml)."""
        df = pd.read_csv(self.data_dir / "reference" / "unit_conversion.csv")
        out: dict[str, UnitDefinition] = {}
        for r in df.itertuples(index=False):
            definition = UnitDefinition(unit=r.unit, kind=r.kind, to_base=float(r.to_base))
            for alias in str(r.aliases).split("|"):
                out[alias.strip().lower()] = definition
        return out

    # ---------------------------------------------------------------- nutrition
    def nutrition_per_100g(self, ingredient_id: int) -> dict[str, float] | None:
        """USDA nutrients per 100 g (``energy_kcal``, ``protein_g`` ...). Missing nutrients are absent, not 0."""
        try:
            row = self._nutrition.loc[int(ingredient_id)]
        except KeyError:
            return None
        cols = ["energy_kcal", "protein_g", "fat_g", "sat_fat_g", "carbohydrate_g", "sugars_g", "fiber_g",
                "sodium_mg", "cholesterol_mg", "calcium_mg", "iron_mg", "potassium_mg", "vitamin_c_mg",
                "vitamin_a_rae_ug"]
        return {c: float(row[c]) for c in cols if pd.notna(row[c])}

    # --------------------------------------------------------------- shelf life
    def default_shelf_life(self, ingredient_id: int) -> ShelfLife | None:
        """The planner's default shelf-life estimate for an unopened item, or ``None`` if there is none."""
        try:
            r = self._shelf_life_default.loc[int(ingredient_id)]
        except KeyError:
            return None
        return ShelfLife(
            storage=r.storage,
            min_days=None if pd.isna(r.min_days_effective) else float(r.min_days_effective),
            max_days=None if pd.isna(r.max_days_effective) else float(r.max_days_effective),
            confidence=r.confidence, source=r.effective_source, is_indefinite=bool(r.is_indefinite))


@lru_cache(maxsize=1)
def get_default_store() -> KnowledgeStore:
    """Process-wide shared store for the default dataset (avoids re-reading Parquet in every module)."""
    return KnowledgeStore()
