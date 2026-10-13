"""Turn the NLP layer's parse of a pantry description into planner-ready ``PantryItem`` objects.

Where this sits
---------------
``nlp.PantryParser`` says *what the user typed* ("spinach, ~250 g assumed, getting old"). The planner needs *what is
in the kitchen and by when it must go* in grams and day indices. This module is that translation, and it is the one
place that decides how much to believe about expiry.

How the deadline (``last_use_day``) is chosen, in order
-------------------------------------------------------
1. **The user stated a date/duration** ("expires tomorrow"): ``expiry_known=True`` - a hard constraint.
2. **The user used a qualitative cue** ("going bad" = 1 day, "getting old" = 3 days): an estimate, confidence 0.6.
3. **Leftover / cooked food**: assume 3 days (the usual food-safety advice), confidence 0.6.
4. **Frozen** (the user said so): no deadline inside the week.
5. **Otherwise** the FoodKeeper default shelf life for the ingredient, assuming we do not know how old the item is:
   we take *half* of the typical (min+max)/2 as remaining time. Confidence depends on how the shelf-life link was made
   (high 0.7 / medium 0.5 / low 0.3) - it is never presented as a known date.

Shelf lives that reach past the horizon become ``None`` (no deadline), so long-life staples never create waste.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from domain.models import HORIZON_DAYS, PantryItem
from knowledge.store import KnowledgeStore, ShelfLife
from nlp.schemas import MatchStatus, ParsedItem, ParseResult, Urgency

# Remaining life assumed for an item of unknown age: this fraction of the typical shelf life.
UNKNOWN_AGE_REMAINING_FRACTION = 0.5
LEFTOVER_DAYS = 3
_SHELF_LIFE_CONFIDENCE = {"high": 0.7, "medium": 0.5, "low": 0.3}
_QUALITATIVE_CUE_CONFIDENCE = 0.6

# Why an item was left out of the pantry (``PantryBuild.skipped``). Constants so a UI can branch on them without
# matching free text.
SKIP_UNKNOWN = "ingredient not recognised"
SKIP_AMBIGUOUS = "ingredient match not confident; ask the user"
SKIP_NO_AMOUNT = "no amount"
SKIP_UNSAFE = "may be unsafe to eat"


@dataclass
class PantryBuild:
    """Result of the conversion: usable items plus everything we deliberately left out (and why)."""

    items: list[PantryItem] = field(default_factory=list)
    skipped: list[tuple[ParsedItem, str]] = field(default_factory=list)


def pantry_from_parse(result: ParseResult, store: KnowledgeStore, horizon_days: int = HORIZON_DAYS) -> PantryBuild:
    """Convert a parse into planner pantry items.

    Skipped (with a reason): unresolved/ambiguous ingredients, items with no weight, and food flagged as possibly
    unsafe. Duplicates of the same ingredient are merged: grams add up and the *earliest* deadline wins.
    """
    build = PantryBuild()
    merged: dict[int, PantryItem] = {}

    for item in result.items:
        if item.ingredient_id is None or item.match_status is MatchStatus.UNKNOWN:
            build.skipped.append((item, SKIP_UNKNOWN))
            continue
        if item.match_status is MatchStatus.AMBIGUOUS:
            build.skipped.append((item, SKIP_AMBIGUOUS))
            continue
        if item.grams is None or item.grams <= 0:
            build.skipped.append((item, SKIP_NO_AMOUNT))
            continue
        if any("unsafe" in w for w in item.warnings):
            build.skipped.append((item, SKIP_UNSAFE))
            continue

        last_day, known, conf = _deadline(item, store, horizon_days)
        new = PantryItem(ingredient_id=item.ingredient_id, grams=item.grams, last_use_day=last_day,
                         expiry_known=known, expiry_confidence=conf, urgency=item.urgency,
                         quantity_assumed=item.quantity_is_assumed)
        merged[item.ingredient_id] = _merge(merged[item.ingredient_id], new) if item.ingredient_id in merged else new

    build.items = list(merged.values())
    return build


def merge_pantry_items(items: list[PantryItem]) -> list[PantryItem]:
    """Merge several stocks of one ingredient: grams add, the earliest deadline wins, known beats estimated.

    The same rule ``pantry_from_parse`` applies; exposed so a UI that lets the user edit rows can re-apply it.
    Order of first appearance is kept.
    """
    merged: dict[int, PantryItem] = {}
    for item in items:
        merged[item.ingredient_id] = _merge(merged[item.ingredient_id], item) if item.ingredient_id in merged else item
    return list(merged.values())


def make_pantry_item(ingredient_id: int, grams: float, store: KnowledgeStore, days_left: int | None = None,
                     urgency: Urgency = Urgency.NONE, horizon_days: int = HORIZON_DAYS,
                     days_left_explicit: bool = True) -> PantryItem:
    """A pantry item built without free text to parse (the UI's "add item", or a corrected ingredient choice).

    ``days_left`` is a deadline the user gave (``0`` = must be used today). With ``days_left_explicit=True`` it is a
    known, hard deadline; with ``False`` it is a qualitative cue ("going bad" -> 1) and is an estimate, exactly as the
    parser treats it. Without ``days_left`` the deadline is the FoodKeeper estimate for an item of unknown age.
    """
    if days_left is not None:
        last = None if days_left >= horizon_days else max(0, days_left)
        return PantryItem(ingredient_id=ingredient_id, grams=grams, last_use_day=last, expiry_known=days_left_explicit,
                          expiry_confidence=1.0 if days_left_explicit else _QUALITATIVE_CUE_CONFIDENCE, urgency=urgency)
    last, conf = estimate_last_use_day(store.default_shelf_life(ingredient_id), horizon_days)
    return PantryItem(ingredient_id=ingredient_id, grams=grams, last_use_day=last, expiry_known=False,
                      expiry_confidence=conf, urgency=urgency)


def _deadline(item: ParsedItem, store: KnowledgeStore, horizon_days: int) -> tuple[int | None, bool, float]:
    """Return ``(last_use_day, expiry_known, confidence)`` following the ladder in the module docstring."""
    # 1-2. the user's own words (a stated date, or a qualitative cue the parser turned into assumed days)
    if item.days_left_hint is not None:
        day = item.days_left_hint
        confidence = 1.0 if item.days_left_explicit else _QUALITATIVE_CUE_CONFIDENCE
        if day >= horizon_days:                  # e.g. "expires in 2 weeks": real, but outside this plan
            return None, item.days_left_explicit, confidence
        return max(0, day), item.days_left_explicit, confidence
    # 3. leftovers / cooked food
    if "leftover" in item.modifiers or "leftovers" in item.modifiers or "cooked" in item.modifiers:
        return LEFTOVER_DAYS, False, _QUALITATIVE_CUE_CONFIDENCE
    # 4. frozen: keeps well beyond a week
    if item.storage_hint == "freezer":
        return None, False, 0.7
    # 5. FoodKeeper default for an item of unknown age
    shelf = store.default_shelf_life(item.ingredient_id) if item.ingredient_id is not None else None
    day, conf = estimate_last_use_day(shelf, horizon_days)
    return day, False, conf


def estimate_last_use_day(shelf: ShelfLife | None, horizon_days: int = HORIZON_DAYS) -> tuple[int | None, float]:
    """Deadline estimate for an item of *unknown age* from its FoodKeeper default: ``(last_use_day, confidence)``.

    Used by the app (via ``pantry_from_parse``) and by the benchmark generator, so what the planner is told in the
    benchmark is exactly what it would be told for a real user. Remaining life is
    ``UNKNOWN_AGE_REMAINING_FRACTION`` of the typical (min+max)/2 shelf life; ``None`` when that outlasts the horizon.
    """
    if shelf is None or shelf.is_indefinite or shelf.max_days is None:
        return None, 0.5
    typical = (shelf.min_days + shelf.max_days) / 2 if shelf.min_days is not None else shelf.max_days
    remaining = math.ceil(typical * UNKNOWN_AGE_REMAINING_FRACTION)
    conf = _SHELF_LIFE_CONFIDENCE.get(shelf.confidence, 0.3)
    if remaining >= horizon_days:
        return None, conf
    return max(0, remaining - 1), conf        # "n days remaining" => last usable day index n-1


def _merge(a: PantryItem, b: PantryItem) -> PantryItem:
    """Combine two stocks of one ingredient: grams add, the earliest deadline wins, known dates beat estimates."""
    days = [d for d in (a.last_use_day, b.last_use_day) if d is not None]
    known = a.expiry_known or b.expiry_known
    urgency_rank = {Urgency.NONE: 0, Urgency.SOON: 1, Urgency.URGENT: 2}
    return PantryItem(
        ingredient_id=a.ingredient_id, grams=a.grams + b.grams, last_use_day=min(days) if days else None,
        expiry_known=known, expiry_confidence=max(a.expiry_confidence, b.expiry_confidence) if known else
        min(a.expiry_confidence, b.expiry_confidence),
        urgency=max((a.urgency, b.urgency), key=lambda u: urgency_rank[u]),
        quantity_assumed=a.quantity_assumed or b.quantity_assumed)
