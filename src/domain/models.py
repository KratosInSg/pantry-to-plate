"""Shared domain objects for planning: who is cooking, what is in the pantry, what a plan is.

Why a separate package
----------------------
These shapes are used by *every* downstream stage - the NLP layer produces pantry items, the hard-rule filter reads the
profile, the optimiser and baselines consume a ``Scenario`` and return a ``WeekPlan``, the evaluator replays plans, the
explainer reads them. Putting them in one dependency-free module means no stage has to import another stage just to
agree on a data shape.

Conventions
-----------
* **Days are integers.** Day 0 is "today" (the first dinner to plan); the horizon is normally 7 days.
* **``last_use_day`` is inclusive.** An item with ``last_use_day = 1`` can be used in tonight's or tomorrow's dinner but
  not the day after. ``None`` means "no deadline inside the horizon" (non-perishables, or shelf life longer than the plan).
* **Known vs estimated expiry** is explicit (``expiry_known``), because the project treats them differently:
  known use-by dates are hard constraints, estimates are soft and confidence-weighted.
* **Hidden truth.** A ``Scenario`` made by the synthetic generator also carries ``true_last_use_day`` - what *actually*
  happens to each item. Planners never see it; only the simulator uses it (this is how robustness to wrong shelf-life
  estimates is measured).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from nlp.schemas import Urgency

# The allergen vocabulary. Each name maps to a ``contains_<name>`` flag on ingredients and recipes in the dataset.
ALLERGENS: tuple[str, ...] = ("dairy", "egg", "gluten", "peanut", "tree_nut", "soy", "sesame", "fish", "shellfish")

HORIZON_DAYS = 7
WEEKDAYS_PER_WEEK = 5  # day-of-week indices 0..4 are Monday..Friday


class Diet(str, Enum):
    """Dietary pattern. Each is a *hard* rule enforced on every ingredient of a recipe."""

    OMNIVORE = "omnivore"
    PESCATARIAN = "pescatarian"   # fish and shellfish are fine; no meat or poultry
    VEGETARIAN = "vegetarian"     # no meat, poultry, fish or eggs; dairy is fine (project definition, not lacto-ovo)
    VEGAN = "vegan"


class UserProfile(BaseModel):
    """Constraints and preferences of the (single) user. MVP: one person, one serving per dinner."""

    # --- hard constraints: a recipe violating any of these is never planned --------------------------------------
    diet: Diet = Diet.OMNIVORE
    allergens: frozenset[str] = frozenset()
    avoid_pork: bool = False
    avoid_alcohol: bool = False
    excluded_ingredient_ids: frozenset[int] = frozenset()   # "never": the user will not eat it, ever
    excluded_recipe_ids: frozenset[int] = frozenset()       # Food.com recipe ids the user rejected ("not this one")
    max_total_minutes: int | None = None                    # optional absolute cap on a recipe's total time
    dinner_only: bool = False                               # leave out breakfast/brunch dishes, doughs, batters, icing

    # --- soft preferences: they shape the score, they never forbid -----------------------------------------------
    liked_ingredient_ids: frozenset[int] = frozenset()
    disliked_ingredient_ids: frozenset[int] = frozenset()
    liked_cuisines: frozenset[str] = frozenset()
    disliked_cuisines: frozenset[str] = frozenset()
    max_weekday_minutes: int = 45                           # soft cooking-time limit for Monday-Friday dinners

    # --- nutrition targets (planning support against reference ranges, not medical advice) ------------------------
    daily_kcal_target: float = Field(default=2000.0, gt=500, lt=6000)
    dinner_kcal_share: float = Field(default=0.30, gt=0.1, lt=0.7)   # share of the day's energy eaten at dinner
    kcal_tolerance: float = Field(default=0.20, ge=0.0, le=0.5)      # +/- band around the dinner target
    min_protein_g_per_dinner: float = Field(default=20.0, ge=0)

    @field_validator("allergens")
    @classmethod
    def _known_allergens(cls, v: frozenset[str]) -> frozenset[str]:
        unknown = set(v) - set(ALLERGENS)
        if unknown:
            raise ValueError(f"unknown allergen(s) {sorted(unknown)}; expected a subset of {list(ALLERGENS)}")
        return v

    @property
    def dinner_kcal_target(self) -> float:
        """Target energy of one dinner."""
        return self.daily_kcal_target * self.dinner_kcal_share

    @property
    def dinner_kcal_range(self) -> tuple[float, float]:
        """(low, high) kcal of an on-target dinner. No penalty is applied inside this band."""
        t = self.dinner_kcal_target
        return t * (1 - self.kcal_tolerance), t * (1 + self.kcal_tolerance)


class PantryItem(BaseModel):
    """Stock of one canonical ingredient, with what the *planner* is told about when it must be used."""

    ingredient_id: int
    grams: float = Field(gt=0)
    last_use_day: int | None = None          # inclusive; None = no deadline inside the horizon
    expiry_known: bool = False               # True: a stated use-by date (hard). False: an estimate (soft)
    expiry_confidence: float = Field(default=1.0, ge=0, le=1)   # how much to trust ``last_use_day``
    urgency: Urgency = Urgency.NONE          # the user's own words ("going bad"), kept for explanations
    quantity_assumed: bool = False           # True: ``grams`` is our estimate, not something the user told us


class Scenario(BaseModel):
    """One planning problem: a user, a pantry and a horizon. Also the unit of the evaluation benchmark."""

    scenario_id: str
    family: str = "adhoc"                    # which of the 8 benchmark families it belongs to
    seed: int = 0
    profile: UserProfile = Field(default_factory=UserProfile)
    pantry: list[PantryItem] = Field(default_factory=list)
    horizon_days: int = Field(default=HORIZON_DAYS, ge=1, le=14)
    start_weekday: int = Field(default=0, ge=0, le=6)       # 0 = Monday: which weekday is day 0
    # Hidden ground truth for the simulator: ingredient_id -> day after which the stock is unusable (None = never).
    # Empty for real user scenarios; planners must not read it.
    true_last_use_day: dict[int, int | None] = Field(default_factory=dict)
    notes: str = ""

    def is_weekday(self, day: int) -> bool:
        """Whether ``day`` (0-based) falls on Monday-Friday given ``start_weekday``."""
        return (self.start_weekday + day) % 7 < WEEKDAYS_PER_WEEK


class WeekPlan(BaseModel):
    """The answer: which recipe is cooked on which day, plus how it was produced."""

    planner: str                              # "random" | "greedy" | "optimiser" | "opt_<ablation>"
    recipe_ids: list[int] = Field(default_factory=list)   # index = day; may be shorter than the horizon if infeasible
    status: str = "ok"                        # ok | optimal | feasible | partial | infeasible | no_candidates
    diagnostics: dict[str, float | int | str] = Field(default_factory=dict)  # solver stats, cost terms ...

    @property
    def is_complete(self) -> bool:
        return self.status in ("ok", "optimal", "feasible") and len(self.recipe_ids) > 0
