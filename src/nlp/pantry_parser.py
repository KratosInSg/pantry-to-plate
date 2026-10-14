"""PantryParser - free-text pantry description -> structured, quantified, canonical pantry items.

Pipeline (one pass per fragment)
--------------------------------
    "half a cabbage, paneer, four eggs and spinach that's going bad"
        |  segmenter.split_items           one fragment per item
        v
    "spinach that's going bad"
        |  urgency.find_urgency            -> URGENT (assume 1 day);  remainder "spinach"
        |  quantities.extract_quantity     -> no amount;              remainder "spinach"
        |  resolver.IngredientResolver     -> ingredient 1234 "spinach" (exact, 1.00)
        |  _estimate_grams                 -> no amount, so assume the typical pack for "vegetable" (250 g)
        v
    ParsedItem(ingredient_id=1234, grams=250, grams_source=ASSUMED_DEFAULT, urgency=URGENT, ...)

Design principles
-----------------
* **Understand, never decide.** This module turns words into a structured pantry. It does not choose meals (the
  optimiser does) and it does not compute nutrition (the knowledge layer does).
* **Never guess silently.** Anything inferred is labelled: ``grams_source`` says how the weight was obtained,
  ``quantity_is_assumed`` is a boolean for the UI, ``match_method``/``match_confidence`` describe the ingredient
  match, and ``warnings`` carries human-readable notes.
* **Rules first, LLM optional.** Everything here is deterministic and testable. An LLM can be plugged in later
  through :class:`LlmFallback` to *re-read* low-confidence fragments; it is never required, and it can only refine
  extraction, not plan.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import date
from typing import Protocol

from knowledge.store import KnowledgeStore, get_default_store
from nlp import defaults
from nlp.quantities import MASS_UNITS, PHYSICAL_UNITS, Quantity, extract_quantity
from nlp.resolver import IngredientResolver, Resolution
from nlp.schemas import GramsSource, MatchStatus, ParsedItem, ParseResult, Urgency
from nlp.segmenter import split_items
from nlp.urgency import UrgencyCue, find_urgency

logger = logging.getLogger(__name__)

# Words that tell us *how the item is kept*; used later to pick the right FoodKeeper row (freezer vs fridge ...).
_STORAGE_FROM_MODIFIER = {
    "frozen": "freezer", "cooked": "refrigerator", "leftover": "refrigerator", "leftovers": "refrigerator",
    "opened": "refrigerator", "canned": "pantry", "tinned": "pantry", "dried": "pantry",
}
# Preparation / quality words worth reporting back (they do not change which food it is).
_REPORTABLE_MODIFIERS = frozenset({
    "chopped", "diced", "sliced", "minced", "grated", "shredded", "crushed", "mashed", "peeled", "cubed",
    "fresh", "raw", "ripe", "organic", "boneless", "skinless", "unsalted", "salted", "roasted", "toasted",
    "smoked", "thawed", "defrosted",
}) | frozenset(_STORAGE_FROM_MODIFIER)

# How much we trust a weight, by how it was obtained. Multiplied with the ingredient match score to give ``confidence``.
_GRAMS_TRUST = {
    GramsSource.EXPLICIT_MASS: 1.0,
    GramsSource.VOLUME_UNIT_WEIGHT: 0.95,
    GramsSource.ITEM_UNIT_WEIGHT: 0.9,
    GramsSource.VOLUME_DENSITY_ASSUMED: 0.7,
    GramsSource.ASSUMED_DEFAULT: 0.6,
    GramsSource.UNKNOWN: 0.5,
}
_ML_PER_CUP = 236.588  # US customary cup; matches reference/unit_conversion.csv


class LlmFallback(Protocol):
    """Extension point for an LLM that re-reads fragments the rules could not understand.

    Contract: return a ``ParseResult`` for the *same* text. It may fix unknown/ambiguous items and add missing
    ones; it must not invent quantities that are not in the text. Not implemented yet (no API key); see
    ``md docs/modules/nlp/pantry_parser.md``.
    """

    def refine(self, text: str, result: ParseResult) -> ParseResult: ...


class PantryParser:
    """Parse a block of pantry text into a :class:`ParseResult`. Thread-safe and cheap to reuse."""

    # An item below this overall confidence is handed to the optional LLM fallback.
    LLM_CONFIDENCE_THRESHOLD = 0.5

    def __init__(self, store: KnowledgeStore | None = None, resolver: IngredientResolver | None = None,
                 llm_fallback: LlmFallback | None = None) -> None:
        self._store = store or get_default_store()
        self._resolver = resolver or IngredientResolver(self._store)
        self._llm = llm_fallback

    # ------------------------------------------------------------------------------------------- public API
    def parse(self, text: str, today: date | None = None) -> ParseResult:
        """Parse ``text``.

        Args:
            text: what the user typed, e.g. ``"half a cabbage, paneer, four eggs and spinach getting old"``.
            today: reference date for weekday cues ("use by friday"); defaults to the real today. Pass a fixed
                date in tests so results are reproducible.
        """
        today = today or date.today()
        fragments = split_items(text, self._store.connector_phrases)
        items: list[ParsedItem] = []
        unparsed: list[str] = []

        for fragment in fragments:
            cue, remainder = find_urgency(fragment, today)
            if cue is not None and not remainder:
                # the fragment was only a cue ("they're going bad"): it describes items we already parsed
                if not self._attach_cue_to_previous(items, cue):
                    unparsed.append(fragment)
                continue

            new_items = self._parse_fragment(fragment, remainder, cue)
            if new_items:
                items.extend(new_items)
                for it in new_items:
                    logger.debug("%r -> %s (%s, %s, match %.2f); %s g (%s); urgency %s", fragment,
                                 it.canonical_name or "?", it.match_status.value, it.match_method, it.match_confidence,
                                 it.grams, it.grams_source.value, it.urgency.value)
            else:
                logger.debug("%r -> nothing that names a food", fragment)
                unparsed.append(fragment)

        result = ParseResult(source_text=text, items=items, unparsed=unparsed)
        logger.debug("rules parse: %d fragment(s) -> %d item(s), %d unparsed", len(fragments), len(items),
                     len(unparsed))
        if self._llm is not None and self._needs_llm(result):
            logger.debug("some fragments are unresolved or low-confidence: handing them to the LLM fallback")
            result = self._llm.refine(text, result)
        return result

    # ------------------------------------------------------------------------------------------- fragments
    def _parse_fragment(self, fragment: str, remainder: str, cue: UrgencyCue | None) -> list[ParsedItem]:
        """Turn one fragment into 0..n items (n>1 only for deliberate splits such as "salt and pepper")."""
        qty, name_text = extract_quantity(remainder)
        name_text = _trim_prepositional_tail(name_text)
        if not name_text:
            return []                                    # nothing that names a food ("2 cups")

        modifiers = _find_modifiers(f"{fragment} {name_text}")
        storage_hint = next((_STORAGE_FROM_MODIFIER[m] for m in modifiers if m in _STORAGE_FROM_MODIFIER), None)
        resolution = self._resolver.resolve(name_text)

        if not resolution.ingredient_ids:
            return [self._build_item(fragment, name_text, None, resolution, qty, modifiers, storage_hint, cue)]
        return [self._build_item(fragment, name_text, iid, resolution, qty, modifiers, storage_hint, cue)
                for iid in resolution.ingredient_ids]

    def _build_item(self, raw: str, name_text: str, ingredient_id: int | None, res: Resolution, qty: Quantity | None,
                    modifiers: list[str], storage_hint: str | None, cue: UrgencyCue | None) -> ParsedItem:
        info = self._store.ingredient(ingredient_id) if ingredient_id is not None else None
        warnings: list[str] = []
        if qty is not None and qty.size is None and info is not None and info.canonical_name in defaults.PREFERRED_ITEM_SIZE:
            # the user did not say a size: use the everyday one for this food (see defaults.PREFERRED_ITEM_SIZE)
            qty = dataclasses.replace(qty, size=defaults.PREFERRED_ITEM_SIZE[info.canonical_name])

        grams, source, assumed, notes = self._estimate_grams(qty, info.ingredient_id if info else None,
                                                             info.food_group if info else None)
        warnings.extend(notes)
        if res.status is MatchStatus.UNKNOWN:
            warnings.append(f"unknown ingredient '{name_text}'")
        elif res.status is MatchStatus.AMBIGUOUS:
            warnings.append(f"'{name_text}' matched '{info.canonical_name if info else '?'}' with low confidence")
        if cue is not None and cue.may_be_unsafe:
            warnings.append(f"'{cue.cue}': the food may already be unsafe - do not plan with it without checking")

        match_conf = res.score if res.status is not MatchStatus.UNKNOWN else 0.0
        return ParsedItem(
            raw_text=raw, name_text=name_text,
            ingredient_id=ingredient_id, canonical_name=info.canonical_name if info else None,
            match_status=res.status, match_method=res.method, match_confidence=round(match_conf, 3),
            suggestions=list(res.suggestions),
            quantity_value=qty.value if qty else None, quantity_unit=qty.unit if qty else None,
            quantity_text=(qty.text or qty.vague_word) if qty else None, size=qty.size if qty else None,
            grams=round(grams, 1) if grams is not None else None, grams_source=source, quantity_is_assumed=assumed,
            modifiers=modifiers, storage_hint=storage_hint,
            urgency=cue.level if cue else Urgency.NONE, urgency_cue=cue.cue if cue else None,
            days_left_hint=cue.days_left if cue else None,
            days_left_explicit=cue.explicit if cue else False,
            confidence=round(match_conf * _GRAMS_TRUST[source], 3), warnings=warnings,
        )

    # ------------------------------------------------------------------------------------------- grams
    def _estimate_grams(self, qty: Quantity | None, ingredient_id: int | None, group: str | None):
        """Return ``(grams, source, is_assumed, notes)`` for the quantity the user gave.

        Decision ladder (first rule that applies wins):
          1. a stated mass                    -> exact                                  EXPLICIT_MASS
          2. a volume                         -> USDA weight per cup/tbsp/tsp, else water-like density
          3. a container/informal unit        -> the ingredient's weight for that unit, else a typical container
          4. a count of whole items           -> weight of one item, else typical item for the food group
          5. a vague word / nothing           -> scaled typical pack for the food group (ASSUMED_DEFAULT)
        """
        group_default = defaults.ASSUMED_GRAMS_BY_GROUP.get(group or "", defaults.FALLBACK_ASSUMED_GRAMS)
        notes: list[str] = []

        if qty is None:
            return group_default, GramsSource.ASSUMED_DEFAULT, True, ["no quantity given: assumed a typical amount"]

        # 1. explicit mass --------------------------------------------------------------------------------------
        if qty.explicit_grams is not None:
            total = qty.explicit_grams
            if qty.unit is not None and qty.unit not in PHYSICAL_UNITS:       # "2 cans (400 g)": weight is per can
                total *= qty.value if qty.value is not None else 1.0
            return total, GramsSource.EXPLICIT_MASS, False, notes

        # vague amounts ("some", "a little", "leftover") without a number --------------------------------------
        if qty.value is None and qty.vague_word is not None:
            factor = defaults.VAGUE_AMOUNT_FACTOR.get(qty.vague_word, 1.0)
            return (group_default * factor, GramsSource.ASSUMED_DEFAULT, True,
                    [f"vague amount '{qty.vague_word}': assumed {factor:g} x a typical amount"])

        count = qty.value if qty.value is not None else 1.0                   # "large onion" -> one
        if qty.is_range:
            notes.append("range given: used the lower bound")

        # 2. volume --------------------------------------------------------------------------------------------
        if qty.unit in PHYSICAL_UNITS and qty.unit not in MASS_UNITS:
            return self._volume_to_grams(count, qty.unit, ingredient_id, notes)

        # 3. container / informal unit -------------------------------------------------------------------------
        if qty.unit is not None:
            if ingredient_id is not None:
                w = self._store.unit_weight(ingredient_id, qty.unit, qty.size)
                if w is not None:
                    return count * w.grams, GramsSource.ITEM_UNIT_WEIGHT, False, notes
            typical = defaults.ASSUMED_GRAMS_BY_CONTAINER.get(qty.unit)
            if typical is not None:
                notes.append(f"no weight on file for a '{qty.unit}' of this food: assumed {typical:g} g")
                return count * typical, GramsSource.ASSUMED_DEFAULT, True, notes
            return group_default, GramsSource.ASSUMED_DEFAULT, True, notes + [f"unknown unit '{qty.unit}'"]

        # 4. count of whole items -------------------------------------------------------------------------------
        if ingredient_id is not None:
            one = self._store.unit_weight(ingredient_id, "each", qty.size) or self._store.whole_item_weight(ingredient_id)
            if one is not None:
                return count * one.grams, GramsSource.ITEM_UNIT_WEIGHT, False, notes
        typical_item = defaults.ASSUMED_ITEM_GRAMS_BY_GROUP.get(group or "", defaults.FALLBACK_ASSUMED_ITEM_GRAMS)
        notes.append(f"no item weight on file: assumed {typical_item:g} g per item")
        return count * typical_item, GramsSource.ASSUMED_DEFAULT, True, notes

    def _volume_to_grams(self, value: float, unit: str, ingredient_id: int | None, notes: list[str]):
        """Volume -> grams using the ingredient's own USDA weights when they exist."""
        if ingredient_id is not None:
            direct = self._store.unit_weight(ingredient_id, unit)             # exact unit on file (cup, tbsp, tsp ...)
            if direct is not None:
                return value * direct.grams, GramsSource.VOLUME_UNIT_WEIGHT, False, notes
            defn = self._store.unit_definitions.get(unit)
            cup = self._store.unit_weight(ingredient_id, "cup")
            if defn is not None and cup is not None:                          # ml, l, pint ... via the cup weight
                return value * defn.to_base / _ML_PER_CUP * cup.grams, GramsSource.VOLUME_UNIT_WEIGHT, False, notes
        defn = self._store.unit_definitions.get(unit)
        ml = value * defn.to_base if defn else value
        notes.append(f"no density on file: assumed {defaults.ASSUMED_DENSITY_G_PER_ML:g} g per ml")
        return ml * defaults.ASSUMED_DENSITY_G_PER_ML, GramsSource.VOLUME_DENSITY_ASSUMED, True, notes

    # ------------------------------------------------------------------------------------------- helpers
    @staticmethod
    def _attach_cue_to_previous(items: list[ParsedItem], cue: UrgencyCue) -> bool:
        """Apply a bare cue ("they expire tomorrow") to the item(s) just before it. Returns False if none."""
        if not items:
            return False
        targets = items if cue.scope == "all" else items[-2:] if cue.scope == "both" else items[-1:]
        for it in targets:
            # never downgrade: keep the more urgent of the existing and the new cue
            order = {Urgency.NONE: 0, Urgency.SOON: 1, Urgency.URGENT: 2}
            if order[cue.level] >= order[it.urgency]:
                it.urgency, it.urgency_cue, it.days_left_hint = cue.level, cue.cue, cue.days_left
                it.days_left_explicit = cue.explicit
            if cue.may_be_unsafe:
                it.warnings.append(f"'{cue.cue}': the food may already be unsafe - do not plan with it without checking")
        return True

    def _needs_llm(self, result: ParseResult) -> bool:
        return bool(result.unparsed) or any(
            i.match_status is not MatchStatus.MATCHED or i.confidence < self.LLM_CONFIDENCE_THRESHOLD
            for i in result.items)


def _find_modifiers(text: str) -> list[str]:
    """Reportable preparation/state words in ``text``, in order of appearance, without duplicates."""
    seen: list[str] = []
    for word in text.lower().replace(",", " ").split():
        word = word.strip("()")
        if word in _REPORTABLE_MODIFIERS and word not in seen:
            seen.append(word)
    return seen


def _trim_prepositional_tail(name: str) -> str:
    """"tuna in olive oil" -> "tuna", "chicken with skin" -> "chicken". The tail describes packaging, not the food."""
    for sep in (" in ", " with ", " packed in ", " from "):
        if sep in f" {name} ":
            head = f" {name} ".split(sep, 1)[0].strip()
            if head:
                return head
    return name
