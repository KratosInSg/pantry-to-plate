"""Types that cross the boundary between the backend and a UI.

Two kinds, on purpose
---------------------
* **Inputs the user edits** (``PantryEntry``, ``PantryReview``, ``IngredientChoice``) are pydantic models: mutable,
  validated, JSON-serialisable, so a UI can hold them in session state and a future HTTP API can accept them.
* **Results to display** (``PlannedWeek`` and its parts) are frozen dataclasses: nothing downstream can accidentally
  change a plan that has already been explained.

Nothing here contains logic beyond small conversions; deciding is done in ``optimizer``, saying is done in ``explain``,
orchestrating is ``service.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from domain.models import PantryItem, Scenario, WeekPlan
from explain.render import Explanation, Section
from nlp.schemas import Urgency

# ``PantryEntry.status``: what the UI should do with a row.
ENTRY_OK = "ok"                          # understood; will be planned with
ENTRY_ASSUMED = "assumed_quantity"       # understood, but the amount is our estimate: show it so it can be corrected
ENTRY_CHOOSE = "needs_choice"            # several plausible ingredients: ask which one (see ``suggestions``)
ENTRY_UNKNOWN = "unrecognised"           # not in the dataset: ask the user to pick or rename
ENTRY_NO_AMOUNT = "no_amount"            # ingredient known, amount not: ask how much
ENTRY_UNSAFE = "unsafe"                  # flagged as possibly unsafe to eat: left out
USABLE_STATUSES = frozenset({ENTRY_OK, ENTRY_ASSUMED})

# A grocery line below this many grams is a pinch of spice, not shopping: flagged ``minor`` so a UI can fold it away.
MINOR_GROCERY_G = 5.0


class IngredientChoice(BaseModel):
    """A candidate canonical ingredient (an autocomplete hit or a "did you mean" suggestion)."""

    ingredient_id: int
    name: str
    score: float = Field(default=1.0, ge=0, le=1)


class PantryEntry(BaseModel):
    """One editable row of the pantry review table."""

    raw_text: str = ""                   # what the user typed ("" for a row added by hand)
    ingredient_id: int | None = None
    name: str | None = None              # canonical name
    grams: float | None = None
    quantity_assumed: bool = False
    # deadline: what the planner will be told, and what produced it (kept so a corrected ingredient can be re-derived)
    last_use_day: int | None = None
    expiry_known: bool = False
    expiry_confidence: float = 1.0
    days_left_hint: int | None = None    # days until it must be used, as read from the user's words
    days_left_explicit: bool = False     # True: the user gave a date / duration. False: a vague cue ("going bad")
    urgency: Urgency = Urgency.NONE
    # review state
    status: str = ENTRY_OK
    problem: str = ""                    # plain-English reason when ``status`` is not usable
    suggestions: list[IngredientChoice] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Will this row be planned with as it is?"""
        return (self.status in USABLE_STATUSES and self.ingredient_id is not None
                and self.grams is not None and self.grams > 0)

    def to_pantry_item(self) -> PantryItem:
        """The planner's view of this row. Only call for a usable row."""
        assert self.usable, "only usable entries can be planned with"
        return PantryItem(ingredient_id=self.ingredient_id, grams=self.grams, last_use_day=self.last_use_day,
                          expiry_known=self.expiry_known, expiry_confidence=self.expiry_confidence,
                          urgency=self.urgency, quantity_assumed=self.quantity_assumed)

    def with_grams(self, grams: float) -> "PantryEntry":
        """The user corrected the amount: it is no longer an assumption."""
        if grams <= 0:
            raise ValueError("amount must be positive")
        status = ENTRY_OK if self.ingredient_id is not None else self.status
        return self.model_copy(update={"grams": grams, "quantity_assumed": False, "status": status, "problem": ""})

    def with_days_left(self, days_left: int | None, horizon_days: int = 7) -> "PantryEntry":
        """The user gave a use-by: a known, hard deadline (``None`` = no deadline this week)."""
        if days_left is not None and days_left < 0:
            raise ValueError("days left cannot be negative")
        last = None if days_left is None or days_left >= horizon_days else days_left
        return self.model_copy(update={"last_use_day": last, "expiry_known": True, "expiry_confidence": 1.0,
                                       "days_left_hint": days_left, "days_left_explicit": True})


class PantryReview(BaseModel):
    """The parse of one block of pantry text, as rows to confirm or fix."""

    source_text: str
    entries: list[PantryEntry] = Field(default_factory=list)
    unparsed: list[str] = Field(default_factory=list)     # fragments that named no food at all

    @property
    def usable_entries(self) -> list[PantryEntry]:
        return [e for e in self.entries if e.usable]

    @property
    def needs_attention(self) -> list[PantryEntry]:
        """Rows the user must act on before they can be planned with."""
        return [e for e in self.entries if not e.usable]


# ==================================================================================================================
# results
# ==================================================================================================================
@dataclass(frozen=True, slots=True)
class IngredientLine:
    """One ingredient of one dinner and where it comes from."""

    name: str
    grams: float
    from_pantry_g: float                 # supplied by stock the user has
    to_buy_g: float                      # not covered: goes on the grocery list
    staple: bool                         # assumed to be in every kitchen (salt, water ...): never counted
    use_by_day: int | None               # deadline of the pantry stock used, relative to this plan's day 0
    deadline_known: bool


@dataclass(frozen=True, slots=True)
class DayPlan:
    """One planned dinner, everything a UI needs to show it."""

    day: int                             # 0-based within this plan
    weekday: str
    recipe_id: int
    name: str
    minutes: int
    cuisine: str | None
    kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float
    ingredients: tuple[IngredientLine, ...]
    steps: tuple[str, ...]               # Food.com's instructions; empty if the step table is not available
    explanation: Section                 # the reasons (template text, or a validated paraphrase)


@dataclass(frozen=True, slots=True)
class GroceryItem:
    ingredient_id: int
    name: str
    grams: float
    food_group: str
    first_needed_day: int                # 0-based within this plan
    weekday: str
    minor: bool                          # a pinch (< MINOR_GROCERY_G): a UI may fold these away


@dataclass(frozen=True, slots=True)
class GroceryBox:
    """What to buy for the whole plan: exactly what the inventory replay says the pantry cannot cover."""

    items: tuple[GroceryItem, ...]

    @property
    def n_items(self) -> int:
        return len(self.items)

    @property
    def total_g(self) -> float:
        return sum(i.grams for i in self.items)

    def by_group(self) -> dict[str, list[GroceryItem]]:
        """Items grouped by food group, groups and items sorted by name (shopping order)."""
        groups: dict[str, list[GroceryItem]] = {}
        for item in self.items:
            groups.setdefault(item.food_group, []).append(item)
        return {g: sorted(v, key=lambda i: i.name) for g, v in sorted(groups.items())}


@dataclass(frozen=True)
class PlannedWeek:
    """A plan, fully presented. Carries the scenario so it can be re-planned (``service.replan``)."""

    scenario: Scenario
    plan: WeekPlan
    days: tuple[DayPlan, ...]
    grocery_box: GroceryBox
    explanation: Explanation
    status: str
    complete: bool                       # a dinner for every day of the horizon
    solve_seconds: float
    day_offset: int = 0                  # days of the original week that had already passed
    expired: dict[str, float] = field(default_factory=dict)    # ingredient name -> grams that went off meanwhile

    @property
    def overview(self) -> Section:
        return self.explanation.sections[0]

    @property
    def rules(self) -> Section | None:
        return self.explanation.section("rules")

    @property
    def caveats(self) -> Section | None:
        return self.explanation.section("caveats")

    @property
    def recipe_ids(self) -> list[int]:
        return [d.recipe_id for d in self.days]
