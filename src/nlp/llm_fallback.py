"""LLM fallback for the pantry parser: let a language model *re-read* the fragments the rules could not understand.

Role (and its limits)
---------------------
The rules parser (``pantry_parser.py``) is deterministic and handles most typing. Some fragments defeat it - "that
purple cabbage thing", "a tub of kimchi", a word it has never seen. For exactly those, this module asks the LLM to
*normalise* the text into three fields: name, amount, unit. Then comes the part that keeps the project's
non-negotiable ("the LLM only parses input"):

1. **Everything the model says is validated against the user's own words.** A name whose words are not in the text, or
   a number that does not occur in it, is dropped - the model cannot invent food or quantities.
2. **The model never produces ids, grams or urgency.** Its fields are turned back into a plain sentence ("6 eggs",
   "2 lb potatoes") and run through the *same rules parser* again, so ingredient matching, the grams ladder and every
   "assumed" label are the rules' own. Urgency comes only from the user's own cue words, found by the rules.
3. **Only confident results replace anything.** If the re-parse is still unresolved, the original item is kept.
4. **Any failure keeps the rules result** (server down, timeout, bad JSON): the app works, just less cleverly.

Replaced items carry a warning so the UI can say "we re-read this with the language model - please check".

What it cannot do
-----------------
It fixes *extraction* (number words, units, odd phrasing, segmentation). It cannot fix a *vocabulary* gap: if the
dataset has no "kimchi", re-parsing "kimchi" is still unresolved and the original item is kept (and shown to the user as
needing attention). Closing vocabulary gaps is a curation job: add a row to ``reference/ingredient_synonyms.csv``.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from nlp.pantry_parser import PantryParser
from nlp.quantities import FRACTION_WORDS, NUMBER_WORDS, UNIT_ALIASES, parse_number_token
from nlp.schemas import MatchStatus, ParsedItem, ParseResult, Urgency
from nlp.urgency import find_urgency

logger = logging.getLogger(__name__)

NO_UNIT = "none"


def extraction_schema(source: str) -> dict[str, Any]:
    """JSON schema for one call: ``has_quantity`` + ``quantity`` (a number) + an **enum of the unit words in the text**.

    Why the enum is built per call: an enum of canonical names ("lb", "pint") made the model map "2 pounds" to "pint"
    (the nearest listed word) - a silent, plausible-looking error. Offering only the unit words that actually occur in
    the text (plus "none") removes that failure by construction; the rules then map the word to a canonical unit.
    """
    return {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "has_quantity": {"type": "boolean"},
                "quantity": {"type": "number"},
                "unit": {"type": "string", "enum": unit_words_in(source) + [NO_UNIT]}},
            "required": ["name", "has_quantity", "quantity", "unit"]}}},
        "required": ["items"],
    }


def unit_words_in(text: str) -> list[str]:
    """Unit words (aliases such as "pounds", "tbsp") that occur as words in ``text``, in order of appearance."""
    seen: list[str] = []
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in UNIT_ALIASES and word not in seen:
            seen.append(word)
    return seen

SYSTEM_PROMPT = (
    "Extract every pantry item from the text. Copy each number EXACTLY as written (convert number words to digits). "
    "If an item has no number, set has_quantity=false and quantity=0. Use the unit written in the text, else 'none'. "
    "Output JSON only.")

_FEW_SHOT_USER = "3 cloves of garlic, half a loaf of bread and some milk"
_FEW_SHOT_ANSWER = (
    '{"items": [{"name": "garlic", "has_quantity": true, "quantity": 3, "unit": "clove"}, '
    '{"name": "bread", "has_quantity": true, "quantity": 0.5, "unit": "loaf"}, '
    '{"name": "milk", "has_quantity": false, "quantity": 0, "unit": "none"}]}')

_VULGAR = {"½": " 1/2 ", "¼": " 1/4 ", "¾": " 3/4 ", "⅓": " 1/3 ", "⅔": " 2/3 "}
_EXTRA_NUMBER_WORDS = {"a": 1.0, "an": 1.0, "dozen": 12.0, "couple": 2.0}
WARNING = "re-read by the language model - please check this is what you meant"


class JsonLlm(Protocol):
    """What the fallback needs from an LLM client (``llm.LlmClient`` satisfies it; tests pass a stub)."""

    def complete_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]: ...


class LlmPantryFallback:
    """Implements ``pantry_parser.LlmFallback``.

    Usage::

        rules = PantryParser()                                   # rules only
        parser = PantryParser(llm_fallback=LlmPantryFallback(LlmClient(), rules))
    """

    def __init__(self, client: JsonLlm, rules_parser: PantryParser) -> None:
        self._client = client
        self._rules = rules_parser           # must be a parser WITHOUT a fallback (no recursion)

    # ------------------------------------------------------------------------------------------------ public API
    def refine(self, text: str, result: ParseResult) -> ParseResult:
        problems = [i for i in result.items if _needs_help(i)]
        fragments = [i.raw_text for i in problems] + list(result.unparsed)
        if not fragments:
            return result
        source = "; ".join(fragments)
        logger.info("asking the LLM to re-read %d fragment(s) the rules could not understand", len(fragments))
        try:
            answer = self._client.complete_json(_messages(source), extraction_schema(source))
        except Exception as exc:             # noqa: BLE001 - any LLM failure means "keep the rules result"
            logger.warning("LLM re-read failed (%s: %s); keeping the rules result", type(exc).__name__, exc)
            return result
        raw_items = answer.get("items") if isinstance(answer, dict) else None
        if not isinstance(raw_items, list):
            logger.warning("LLM answer has no 'items' list; keeping the rules result")
            return result

        items = list(result.items)
        unparsed = list(result.unparsed)
        replaced: set[int] = set()           # positions in ``items`` already taken by a replacement
        for raw in raw_items:
            checked = _validate(raw, fragments)
            if checked is None:
                logger.debug("dropped LLM item %r: not supported by the user's words", raw)
                continue
            reparsed = [i for i in self._rules.parse(_sentence(checked)).items if i.match_status is MatchStatus.MATCHED]
            if len(reparsed) != 1:
                logger.debug("LLM item %r still does not resolve to one ingredient: kept the rules' version",
                             _sentence(checked))
                continue                     # unresolved or oddly split: keep the rules' version
            new = reparsed[0]
            slot = _find_slot(checked["name"], items, replaced)
            if slot is not None:
                original = items[slot]
                new.raw_text = original.raw_text
                if original.urgency is not Urgency.NONE:     # keep the cue the rules read from the user's words
                    new.urgency, new.urgency_cue = original.urgency, original.urgency_cue
                    new.days_left_hint, new.days_left_explicit = original.days_left_hint, original.days_left_explicit
                new.warnings.append(WARNING)
                logger.debug("LLM re-read %r as %r -> %s", original.raw_text, _sentence(checked), new.canonical_name)
                items[slot] = new
                replaced.add(slot)
                continue
            leftover = next((u for u in unparsed if _words_in_text(checked["name"], u)), None)
            new.raw_text = leftover or checked["name"]
            cue, _ = find_urgency(new.raw_text)               # the user's own words, read by the rules
            if cue is not None:
                new.urgency, new.urgency_cue = cue.level, cue.cue
                new.days_left_hint, new.days_left_explicit = cue.days_left, cue.explicit
            new.warnings.append(WARNING)
            logger.debug("LLM found %r -> %s", new.raw_text, new.canonical_name)
            items.append(new)
            if leftover is not None:
                unparsed.remove(leftover)
        added = len(items) - len(result.items)
        logger.info("LLM re-read: %d item(s) replaced, %d added, %d of %d suggestion(s) not used", len(replaced),
                    added, len(raw_items) - len(replaced) - added, len(raw_items))
        return ParseResult(source_text=result.source_text, items=items, unparsed=unparsed)


# ==================================================================================================================
# helpers
# ==================================================================================================================
def _needs_help(item: ParsedItem) -> bool:
    """Same trigger as the parser's own: not confidently matched, or low overall confidence."""
    return item.match_status is not MatchStatus.MATCHED or item.confidence < PantryParser.LLM_CONFIDENCE_THRESHOLD


def _messages(source: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _FEW_SHOT_USER},
            {"role": "assistant", "content": _FEW_SHOT_ANSWER},
            {"role": "user", "content": source}]


def _stem(word: str) -> str:
    return word[:-2] if word.endswith("es") and len(word) > 4 else word[:-1] if word.endswith("s") and len(word) > 3 else word


def _words_in_text(name: str, text: str) -> bool:
    """Every content word of ``name`` occurs in ``text`` (plural/singular tolerant)."""
    words = re.findall(r"[a-z]+", name.lower())
    haystack = text.lower()
    return bool(words) and all(_stem(w) in haystack for w in words)


def _numbers_in(text: str) -> set[float]:
    """Every number the user could have meant: digits, fractions, "1 1/2", number words, "half a dozen"."""
    t = text.lower()
    for ch, repl in _VULGAR.items():
        t = t.replace(ch, repl)
    found: list[float] = []
    for tok in re.findall(r"\d+(?:\.\d+)?(?:/\d+)?|[a-z]+", t):
        parsed = parse_number_token(tok)
        if parsed is not None:
            found.append(parsed[0])
        elif tok in NUMBER_WORDS:
            found.append(float(NUMBER_WORDS[tok]))
        elif tok in FRACTION_WORDS:
            found.append(float(FRACTION_WORDS[tok]))
        elif tok in _EXTRA_NUMBER_WORDS:
            found.append(_EXTRA_NUMBER_WORDS[tok])
    numbers = set(found)
    numbers.update(a + b for a, b in zip(found, found[1:]) if a >= 1 and b < 1)        # "1 1/2", "two and a half"
    if "dozen" in t and "half" in t:
        numbers.add(6.0)                                                                # "half a dozen"
    return numbers


def _validate(raw: Any, fragments: list[str]) -> dict[str, Any] | None:
    """Keep only what the user's own words support. Returns a clean dict or ``None`` to drop the item.

    The checks run against the *one fragment that names the food*, so a number or unit that belongs to a different
    item ("1 jar" next to "potatoes") is not accepted.
    """
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip().lower()
    fragment = next((f for f in fragments if name and _words_in_text(name, f)), None)
    if fragment is None:
        return None                                              # a food the user never mentioned
    quantity: float | None = None
    unit: str | None = None
    if raw.get("has_quantity") is True and isinstance(raw.get("quantity"), (int, float)):
        value = float(raw["quantity"])
        if value > 0 and any(abs(value - n) < 1e-6 for n in _numbers_in(fragment)):
            quantity = value                                     # else: ignore the number, the rules will assume
    word = str(raw.get("unit", NO_UNIT)).lower()
    written = unit_words_in(fragment)
    if quantity is not None:
        if word in written:
            unit = word                                          # a unit word the user really wrote
        elif word != NO_UNIT or written:
            quantity = None                                      # a unit we cannot confirm, or one it ignored: the
                                                                 # number's meaning is unknown, so do not use it
    return {"name": name, "quantity": quantity, "unit": unit}


def _sentence(checked: dict[str, Any]) -> str:
    """Rebuild a plain phrase the rules parser already understands ("2 lb purple cabbage")."""
    parts: list[str] = []
    if checked["quantity"] is not None:
        parts.append(f"{checked['quantity']:g}")
        if checked["unit"]:
            parts.append(checked["unit"])
    parts.append(checked["name"])
    return " ".join(parts)


def _find_slot(name: str, items: list[ParsedItem], taken: set[int]) -> int | None:
    """The not-yet-replaced item that needs help and whose text contains ``name``."""
    for pos, item in enumerate(items):
        if pos not in taken and _needs_help(item) and _words_in_text(name, item.raw_text):
            return pos
    return None


def parser_with_llm(client: JsonLlm | None, store=None, resolver=None) -> PantryParser:
    """A parser that uses the LLM fallback *if the model is reachable*, else the plain rules parser.

    The application calls this once at start-up: an unreachable or unconfigured LLM is a normal situation, not an
    error, and must never stop pantry parsing.
    """
    rules = PantryParser(store=store, resolver=resolver)
    available = getattr(client, "is_available", None)
    if client is None:
        logger.info("pantry parser: rules only (no LLM configured)")
        return rules
    if callable(available) and not available():
        logger.warning("pantry parser: the LLM is not reachable, so parsing uses the rules only")
        return rules
    logger.info("pantry parser: rules + LLM fallback for fragments the rules cannot read")
    return PantryParser(store=rules._store, resolver=rules._resolver,        # noqa: SLF001 - share the built index
                        llm_fallback=LlmPantryFallback(client, rules))
