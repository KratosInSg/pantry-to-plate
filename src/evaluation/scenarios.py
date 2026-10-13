"""Synthetic benchmark scenarios: seeded, documented, split and frozen before anything is tuned.

Why synthetic
-------------
Real household pantries (with expiry dates) are not publicly available, so evaluation uses *simulated kitchens*. The
claim the project can honestly make is therefore "better planning on realistic simulated kitchens", and the generator
exists to make that claim reproducible rather than anecdotal.

Eight scenario families, each stressing a different part of the problem (from docs/data.md):

==========================  ==================================================================================
family                      what it stresses
==========================  ==================================================================================
expiry_heavy                many items about to expire, some with known use-by dates -> waste term
sparse_pantry               3-6 items -> the grocery term; almost everything must be bought
well_stocked                25-40 items -> utilisation; large search space of pantry-driven meals
restrictive_diet            vegan/vegetarian + several allergens -> hard rules shrink the pool
conflicting_preferences     disliked ingredients sit in the pantry, liked cuisines fit it badly
tight_time                  15-25 minute weekday limit -> cook-time penalty
nutrition_pressure          extreme calorie target + high protein minimum + narrow band -> nutrition term
infeasible_combo            diet + allergens + exclusions leave very few recipes -> graceful degradation
==========================  ==================================================================================

What is random and what is not
------------------------------
Everything is a pure function of ``(family, seed)`` and the dataset. The same seeds on the same dataset give the same
benchmark byte-for-byte.

Planner-visible vs hidden truth
-------------------------------
For perishable items the *planner* is told an estimate computed exactly like the app does for a real user
(``domain.pantry.estimate_last_use_day``), while the scenario also stores the *true* last usable day, sampled from
the FoodKeeper range. The simulator uses the truth; planners never see it. This is what lets the benchmark measure
sensitivity to wrong shelf-life estimates. A share of items carry a *known* use-by date (planner sees the truth).

Freezing
--------
``freeze_benchmark`` writes the scenarios, a stratified validation/test split and a ``FROZEN.json`` holding SHA-256
hashes. ``load_split`` re-verifies them on every load, so tuning code cannot silently alter the test set.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from domain.models import ALLERGENS, HORIZON_DAYS, Diet, PantryItem, Scenario, UserProfile
from domain.pantry import estimate_last_use_day
from knowledge.recipes import RecipeCatalog
from knowledge.store import KnowledgeStore
from nlp import defaults
from nlp.schemas import Urgency

FAMILIES: tuple[str, ...] = ("expiry_heavy", "sparse_pantry", "well_stocked", "restrictive_diet",
                             "conflicting_preferences", "tight_time", "nutrition_pressure", "infeasible_combo")
BENCHMARK_VERSION = "v1"
DEFAULT_BASE_SEED = 20261012
DEFAULT_EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"

# Relative frequency of allergies in the simulated population (rough public prevalence ordering, not medical data).
_ALLERGEN_WEIGHTS = {"dairy": 0.22, "gluten": 0.22, "tree_nut": 0.15, "peanut": 0.10, "egg": 0.10, "soy": 0.07,
                     "shellfish": 0.07, "fish": 0.04, "sesame": 0.03}
_PERISHABLE_MAX_DAYS = 14        # a default shelf life at or below this can spoil inside a 7-day plan
_KNOWN_EXPIRY_SHARE_DEFAULT = 0.20


@dataclass(frozen=True, slots=True)
class FamilySpec:
    """The knobs that make one family different from another."""

    n_pantry: tuple[int, int]
    diet_probs: dict[Diet, float]
    n_allergens: tuple[int, int]
    n_excluded: tuple[int, int] = (0, 0)
    n_disliked: tuple[int, int] = (0, 2)
    weekday_minutes: tuple[int, ...] = (30, 45, 60)
    kcal_target: tuple[float, float] = (1700.0, 2400.0)
    min_protein: tuple[float, float] = (15.0, 25.0)
    kcal_tolerance: float = 0.20
    perishable_bias: float = 0.0          # extra share of items drawn from perishable ingredients
    known_expiry_share: float = _KNOWN_EXPIRY_SHARE_DEFAULT
    short_life: bool = False              # truth skewed to "about to expire"
    disliked_in_pantry: int = 0           # how many disliked ingredients are deliberately placed in the pantry
    liked_cuisine_mismatch: bool = False
    hard_time_cap: tuple[int, int] | None = None   # (low, high): a hard maximum recipe time drawn from this range
    pantry_cap_g: float = 1800.0          # stock is scaled down to this: the plan covers dinners only (~1/3 of a
                                          # person's food), so ~2 kg of dinners/week can use ~1-2 kg of pantry


_OMNI_HEAVY = {Diet.OMNIVORE: 0.65, Diet.VEGETARIAN: 0.2, Diet.PESCATARIAN: 0.08, Diet.VEGAN: 0.07}
SPECS: dict[str, FamilySpec] = {
    "expiry_heavy": FamilySpec(n_pantry=(12, 20), diet_probs=_OMNI_HEAVY, n_allergens=(0, 1), perishable_bias=0.5,
                               known_expiry_share=0.40, short_life=True),
    "sparse_pantry": FamilySpec(n_pantry=(3, 6), diet_probs=_OMNI_HEAVY, n_allergens=(0, 1)),
    "well_stocked": FamilySpec(n_pantry=(25, 40), diet_probs=_OMNI_HEAVY, n_allergens=(0, 1), pantry_cap_g=3000.0),
    "restrictive_diet": FamilySpec(n_pantry=(8, 16), diet_probs={Diet.VEGAN: 0.5, Diet.VEGETARIAN: 0.5},
                                   n_allergens=(2, 3)),
    "conflicting_preferences": FamilySpec(n_pantry=(10, 18), diet_probs=_OMNI_HEAVY, n_allergens=(0, 1),
                                          n_disliked=(2, 4), disliked_in_pantry=2, liked_cuisine_mismatch=True),
    "tight_time": FamilySpec(n_pantry=(8, 16), diet_probs=_OMNI_HEAVY, n_allergens=(0, 1), weekday_minutes=(15, 20, 25)),
    "nutrition_pressure": FamilySpec(n_pantry=(8, 16), diet_probs=_OMNI_HEAVY, n_allergens=(0, 1),
                                     kcal_target=(1300.0, 1500.0), min_protein=(30.0, 40.0), kcal_tolerance=0.10),
    "infeasible_combo": FamilySpec(n_pantry=(6, 12), diet_probs={Diet.VEGAN: 1.0}, n_allergens=(4, 6),
                                   n_excluded=(3, 5), hard_time_cap=(15, 25)),
}


# =================================================================================================================
# Ingredient pool (what a pantry can be made of)
# =================================================================================================================
@dataclass
class _Pool:
    ids: np.ndarray             # candidate pantry ingredient ids
    weight: np.ndarray          # sampling weight (popularity, dampened)
    group: list[str]
    perishable: np.ndarray      # bool: default shelf life short enough to spoil within the horizon
    shelf_min: np.ndarray       # FoodKeeper default min/max days (nan when unknown)
    shelf_max: np.ndarray


def _build_pool(store: KnowledgeStore) -> _Pool:
    tbl = store.all_ingredients()
    tbl = tbl[(tbl.fdc_id.notna()) & (~tbl.is_assumed_available) & (tbl.n_recipes_pool >= 20)
              & (~tbl.food_group.isin(["alcohol", "water", "beverage"]))]
    ids = tbl.ingredient_id.to_numpy(dtype=np.int64)
    mins, maxs = np.full(len(ids), np.nan), np.full(len(ids), np.nan)
    for k, iid in enumerate(ids):
        sl = store.default_shelf_life(int(iid))
        if sl is not None and sl.max_days is not None and not sl.is_indefinite:
            mins[k], maxs[k] = (sl.min_days if sl.min_days is not None else sl.max_days), sl.max_days
    perishable = np.nan_to_num(maxs, nan=1e9) <= _PERISHABLE_MAX_DAYS
    weight = np.sqrt(tbl.n_recipes_pool.to_numpy(dtype=float))        # dampen: salt-like heads should not dominate
    return _Pool(ids=ids, weight=weight, group=tbl.food_group.tolist(), perishable=perishable,
                 shelf_min=mins, shelf_max=maxs)


# =================================================================================================================
# One scenario
# =================================================================================================================
def _rounded(grams: float) -> float:
    return float(max(20.0, round(grams / 10.0) * 10.0))


def generate_scenario(family: str, seed: int, catalog: RecipeCatalog, store: KnowledgeStore,
                      _pool: _Pool | None = None) -> Scenario:
    """Build one scenario. Pure function of ``(family, seed)`` and the dataset."""
    spec = SPECS[family]
    pool = _pool or _build_pool(store)
    rng = np.random.default_rng([seed, FAMILIES.index(family), 7])

    # --- profile --------------------------------------------------------------------------------------------------
    diets, probs = zip(*spec.diet_probs.items())
    diet = rng.choice(len(diets), p=np.array(probs) / sum(probs))
    diet = diets[int(diet)]
    n_all = int(rng.integers(spec.n_allergens[0], spec.n_allergens[1] + 1))
    names = list(_ALLERGEN_WEIGHTS)
    pw = np.array([_ALLERGEN_WEIGHTS[a] for a in names])
    allergens = frozenset(rng.choice(names, size=min(n_all, len(names)), replace=False, p=pw / pw.sum()).tolist())

    popular = pool.ids[np.argsort(-pool.weight)][:150]                  # sensible things to like/dislike/exclude
    cuisines = [c for c, _ in _cuisine_counts(catalog)[:12]]
    n_dis = int(rng.integers(spec.n_disliked[0], spec.n_disliked[1] + 1))
    disliked = frozenset(int(i) for i in rng.choice(popular, size=n_dis, replace=False))
    n_exc = int(rng.integers(spec.n_excluded[0], spec.n_excluded[1] + 1))
    excluded = frozenset(int(i) for i in rng.choice([p for p in popular if p not in disliked], size=n_exc,
                                                    replace=False)) if n_exc else frozenset()
    liked = frozenset(int(i) for i in rng.choice([p for p in popular if p not in disliked | excluded],
                                                 size=int(rng.integers(0, 4)), replace=False))
    liked_cuisines = frozenset(rng.choice(cuisines, size=int(rng.integers(1, 3)), replace=False).tolist())

    profile = UserProfile(
        diet=diet, allergens=allergens, avoid_pork=bool(rng.random() < 0.05), excluded_ingredient_ids=excluded,
        max_total_minutes=(int(rng.integers(spec.hard_time_cap[0], spec.hard_time_cap[1] + 1))
                           if spec.hard_time_cap else None),
        liked_ingredient_ids=liked, disliked_ingredient_ids=disliked, liked_cuisines=liked_cuisines,
        max_weekday_minutes=int(rng.choice(spec.weekday_minutes)),
        daily_kcal_target=float(round(rng.uniform(*spec.kcal_target) / 50) * 50),
        kcal_tolerance=spec.kcal_tolerance, min_protein_g_per_dinner=float(round(rng.uniform(*spec.min_protein))))

    # --- pantry: half seeded from real recipes (so it is cookable), half random popular items -----------------------
    n_items = int(rng.integers(spec.n_pantry[0], spec.n_pantry[1] + 1))
    chosen: dict[int, float] = {}                                          # ingredient_id -> grams
    pool_set = set(pool.ids.tolist())
    n_seed_recipes = max(1, n_items // 6)
    for _ in range(n_seed_recipes):
        r = int(rng.integers(0, catalog.n))
        ids, grams = catalog.ingredients(r)
        for iid, g in sorted(zip(ids.tolist(), grams.tolist()), key=lambda t: -t[1])[:4]:
            if iid in pool_set and iid not in excluded and len(chosen) < n_items:
                chosen.setdefault(int(iid), _rounded(g * float(rng.uniform(1.5, 4.0))))
    weights = pool.weight * np.where(pool.perishable, 1.0 + spec.perishable_bias * 4, 1.0)
    attempts = 0
    while len(chosen) < n_items and attempts < 10 * n_items:
        attempts += 1
        k = int(rng.choice(len(pool.ids), p=weights / weights.sum()))
        iid = int(pool.ids[k])
        if iid in chosen or iid in excluded:
            continue
        base = defaults.ASSUMED_GRAMS_BY_GROUP.get(pool.group[k], defaults.FALLBACK_ASSUMED_GRAMS)
        chosen[iid] = _rounded(base * float(np.exp(rng.normal(0.0, 0.35))))
    # conflicting_preferences: deliberately stock things the user dislikes
    for iid in list(disliked)[: spec.disliked_in_pantry]:
        if iid not in chosen and iid in pool_set:
            k = int(np.flatnonzero(pool.ids == iid)[0])
            chosen[iid] = _rounded(defaults.ASSUMED_GRAMS_BY_GROUP.get(pool.group[k], 250.0))

    # size the stock for ONE person's week: scale down proportionally if the random draw came out too large
    total = sum(chosen.values())
    if total > spec.pantry_cap_g:
        scale = spec.pantry_cap_g / total
        chosen = {iid: _rounded(g * scale) for iid, g in chosen.items()}

    # --- expiry: planner-visible estimate vs hidden truth ------------------------------------------------------------
    pantry: list[PantryItem] = []
    truth: dict[int, int | None] = {}
    index_of = {int(i): k for k, i in enumerate(pool.ids)}
    for iid, grams in chosen.items():
        k = index_of.get(iid)
        sl = store.default_shelf_life(iid)
        est_day, est_conf = estimate_last_use_day(sl, HORIZON_DAYS)
        true_day: int | None = None
        if k is not None and pool.perishable[k]:
            life = rng.uniform(pool.shelf_min[k], pool.shelf_max[k])             # total shelf life of this unit
            age_fraction = rng.uniform(0.0, 0.9) if not spec.short_life else rng.uniform(0.4, 0.95)
            remaining = max(1, int(round(life * (1 - age_fraction))))
            true_day = remaining - 1 if remaining - 1 < HORIZON_DAYS else None
        known = true_day is not None and bool(rng.random() < spec.known_expiry_share)
        visible = true_day if known else est_day
        urgency = Urgency.NONE
        if visible is not None and visible <= 1:
            urgency = Urgency.URGENT if known else Urgency.SOON
        pantry.append(PantryItem(ingredient_id=iid, grams=grams, last_use_day=visible, expiry_known=known,
                                 expiry_confidence=1.0 if known else est_conf, urgency=urgency))
        truth[iid] = true_day

    return Scenario(scenario_id=f"{family}-{seed:04d}", family=family, seed=seed, profile=profile, pantry=pantry,
                    horizon_days=HORIZON_DAYS, start_weekday=int(rng.integers(0, 7)), true_last_use_day=truth,
                    notes=f"generator {BENCHMARK_VERSION}")


def _cuisine_counts(catalog: RecipeCatalog) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for c in catalog.cuisine:
        if c is not None:
            counts[c] = counts.get(c, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


# =================================================================================================================
# Benchmark, split, freeze
# =================================================================================================================
def build_benchmark(catalog: RecipeCatalog, store: KnowledgeStore, n_per_family: int = 30,
                    base_seed: int = DEFAULT_BASE_SEED) -> list[Scenario]:
    """Generate ``n_per_family`` scenarios for each family (240 by default)."""
    pool = _build_pool(store)
    return [generate_scenario(f, base_seed + k, catalog, store, pool) for f in FAMILIES for k in range(n_per_family)]


def split_benchmark(scenarios: Sequence[Scenario], validation_share: float = 0.5, seed: int = DEFAULT_BASE_SEED
                    ) -> dict[str, list[str]]:
    """Stratified split by family: ``{"validation": [ids], "test": [ids]}``. Deterministic given ``seed``."""
    rng = np.random.default_rng(seed)
    out: dict[str, list[str]] = {"validation": [], "test": []}
    for family in FAMILIES:
        ids = sorted(s.scenario_id for s in scenarios if s.family == family)
        rng.shuffle(ids)
        cut = int(round(len(ids) * validation_share))
        out["validation"] += ids[:cut]
        out["test"] += ids[cut:]
    out["validation"].sort()
    out["test"].sort()
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_benchmark(scenarios: Sequence[Scenario], out_dir: Path = DEFAULT_EVAL_DIR,
                     dataset_manifest: Path | None = None) -> Path:
    """Write scenarios + split + ``FROZEN.json`` (hashes). Refuses to overwrite an existing frozen benchmark."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = out_dir / "FROZEN.json"
    if frozen_path.exists():
        raise FileExistsError(f"{frozen_path} already exists: the benchmark is frozen. Bump BENCHMARK_VERSION and use "
                              f"a new directory to create a new one.")
    sc_path = out_dir / f"scenarios_{BENCHMARK_VERSION}.jsonl"
    sp_path = out_dir / f"split_{BENCHMARK_VERSION}.json"
    sc_path.write_text("\n".join(s.model_dump_json() for s in scenarios) + "\n", encoding="utf-8")
    sp_path.write_text(json.dumps(split_benchmark(scenarios), indent=1), encoding="utf-8")
    meta = {
        "version": BENCHMARK_VERSION, "created": date.today().isoformat(), "n_scenarios": len(scenarios),
        "files": {sc_path.name: _sha256(sc_path), sp_path.name: _sha256(sp_path)},
        "dataset_manifest_sha256": _sha256(dataset_manifest) if dataset_manifest and dataset_manifest.exists() else None,
    }
    frozen_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return frozen_path


def load_split(split: str, eval_dir: Path = DEFAULT_EVAL_DIR) -> list[Scenario]:
    """Load the ``"validation"`` or ``"test"`` scenarios, verifying the freeze hashes first."""
    if split not in ("validation", "test"):
        raise ValueError("split must be 'validation' or 'test'")
    meta = json.loads((eval_dir / "FROZEN.json").read_text(encoding="utf-8"))
    for name, expected in meta["files"].items():
        if _sha256(eval_dir / name) != expected:
            raise RuntimeError(f"{name} does not match FROZEN.json - the frozen benchmark has been modified")
    ids = set(json.loads((eval_dir / f"split_{meta['version']}.json").read_text(encoding="utf-8"))[split])
    out = []
    with open(eval_dir / f"scenarios_{meta['version']}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                sc = Scenario.model_validate_json(line)
                if sc.scenario_id in ids:
                    out.append(sc)
    return out


__all__ = ["FAMILIES", "SPECS", "FamilySpec", "generate_scenario", "build_benchmark", "split_benchmark",
           "freeze_benchmark", "load_split", "ALLERGENS"]
