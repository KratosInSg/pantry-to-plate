"""Typed objects that cross the NLP module boundary.

Why pydantic models and not dicts
---------------------------------
The parser's output is consumed by the UI, by the planner (which turns it into pantry inventory) and by the
evaluation harness (which compares it with hand-labelled ground truth). A typed, validated, JSON-serialisable object
keeps all three honest and makes ``result.model_dump()`` a one-liner for logging and for the labelled test set.

The "never guess silently" rule
-------------------------------
Every field that the parser had to *assume* has a companion that says so (``grams_source``, ``match_method``,
``warnings``). The explainer and the evaluation rely on this: "we assumed 200 g because you did not say" is a very
different statement from "you told us 200 g".
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Urgency(str, Enum):
    """How soon the user needs this item used. Drives the waste term of the optimiser."""

    NONE = "none"        # no cue in the text
    SOON = "soon"        # "getting old", "should use it up": use within a few days
    URGENT = "urgent"    # "going bad", "expires tomorrow": use first, today/tomorrow


class MatchStatus(str, Enum):
    """Outcome of mapping the user's words to a canonical ingredient."""

    MATCHED = "matched"      # confident: exact / normalised / suffix / high-score fuzzy
    AMBIGUOUS = "ambiguous"  # a plausible but not confident fuzzy match; ``suggestions`` has alternatives
    UNKNOWN = "unknown"      # nothing close; the UI should ask the user


class GramsSource(str, Enum):
    """How ``grams`` was obtained, ordered roughly from most to least trustworthy."""

    EXPLICIT_MASS = "explicit_mass"                  # "500 g", "1 lb", "(400g)"
    VOLUME_UNIT_WEIGHT = "volume_unit_weight"        # "2 cups flour" via the USDA cup weight for flour
    ITEM_UNIT_WEIGHT = "item_unit_weight"            # "3 eggs" via the weight of one egg
    VOLUME_DENSITY_ASSUMED = "volume_density_assumed"  # volume with no weight data: assumed 1 g per ml
    ASSUMED_DEFAULT = "assumed_default"              # quantity missing/vague: typical amount for the food group
    UNKNOWN = "unknown"                              # could not estimate (unknown ingredient, no mass)


class Suggestion(BaseModel):
    """One alternative ingredient the user might have meant (for 'did you mean ...?')."""

    ingredient_id: int
    canonical_name: str
    score: float = Field(ge=0, le=1)


class ParsedItem(BaseModel):
    """One pantry item understood from the user's text."""

    # --- what the user typed ---------------------------------------------------
    raw_text: str                       # the fragment this item came from, as typed
    name_text: str                      # the part we tried to resolve to an ingredient

    # --- which ingredient --------------------------------------------------------
    ingredient_id: int | None = None
    canonical_name: str | None = None
    match_status: MatchStatus = MatchStatus.UNKNOWN
    match_method: str = "none"          # exact | normalised | singular | suffix | prefix | fuzzy | none
    match_confidence: float = Field(default=0.0, ge=0, le=1)
    suggestions: list[Suggestion] = Field(default_factory=list)

    # --- how much ----------------------------------------------------------------
    quantity_value: float | None = None  # number the user gave, in ``quantity_unit`` (None = none given)
    quantity_unit: str | None = None     # canonical unit ("cup", "g", "clove"); None = a count of whole items
    quantity_text: str | None = None     # the words that expressed it ("half a", "2 cups")
    size: str | None = None              # small | medium | large when stated ("a large onion")
    grams: float | None = None           # best estimate of the amount in grams (None = could not estimate)
    grams_source: GramsSource = GramsSource.UNKNOWN
    quantity_is_assumed: bool = False    # True when ``grams`` is not something the user told us

    # --- state / urgency -----------------------------------------------------------
    modifiers: list[str] = Field(default_factory=list)  # chopped, frozen, cooked, dried ... as typed
    storage_hint: str | None = None      # "freezer" when the user said frozen, "refrigerator" for cooked/leftover
    urgency: Urgency = Urgency.NONE
    urgency_cue: str | None = None       # the phrase that triggered it ("going bad")
    days_left_hint: int | None = None    # explicit or implied days until it must be used (0 = today)
    days_left_explicit: bool = False     # True = the user gave a date/duration (known); False = our estimate

    # --- diagnostics --------------------------------------------------------------
    confidence: float = Field(default=0.0, ge=0, le=1)  # overall: match confidence x quantity trust
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        """True when we have an ingredient id we can plan with."""
        return self.ingredient_id is not None


class ParseResult(BaseModel):
    """Everything understood from one block of pantry text."""

    source_text: str
    items: list[ParsedItem] = Field(default_factory=list)
    unparsed: list[str] = Field(default_factory=list)  # fragments we could make no sense of at all

    @property
    def resolved_items(self) -> list[ParsedItem]:
        return [i for i in self.items if i.is_resolved]

    @property
    def needs_attention(self) -> list[ParsedItem]:
        """Items the UI should ask the user about (unknown / ambiguous ingredient)."""
        return [i for i in self.items if i.match_status is not MatchStatus.MATCHED]
