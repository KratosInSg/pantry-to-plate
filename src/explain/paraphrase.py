"""Optional LLM paraphrase of explanation sections - accepted only if it adds nothing and drops nothing checkable.

The rule this module enforces
-----------------------------
CLAUDE.md: the LLM "only parses input and writes explanations", and "every LLM answer is validated against the user's
words or the solver's facts". Here the LLM is given the *template sentences* of one section (``render.py``) and asked to
reword them. Its answer replaces the template text **only if all of these hold**; otherwise the template text is kept
and ``Section.note`` records why:

=====================  =========================================================================================
check                  what it catches
=====================  =========================================================================================
numbers                an invented number, or a number the facts contained that was dropped (so a shortfall or
                       quantity cannot silently vanish). Number words ("seven") count as numbers
foods                  an ingredient the facts do not mention, or one they mention that was dropped
weekdays / "tomorrow"  a day the facts do not name; relative days ("today", "tomorrow") are never allowed
warnings               a warning in the facts ("below", "short", "dislike", "estimate", "unused") with no
                       equivalent word left in the rewrite
claims                 health / taste claims the facts do not support ("healthy", "delicious", ...)
form                   markup, line breaks, or an answer far longer than the facts
=====================  =========================================================================================

What this can **not** guarantee
-------------------------------
It is a check on *content words and numbers*, not on meaning. A rewrite could still attach a true number to the wrong
noun inside the same section. Mitigations: sections are small (one dinner, or the week summary), only that section's own
facts are allowed, and the safety sections (``rules``, ``caveats``) are never sent to the model at all. The template
text is always available and is what the evaluation scores.

Failure model
-------------
Any LLM failure (server down, timeout, empty answer) means "no paraphrase": the template stays. After the first
transport failure the paraphraser stops calling the model for the rest of the explanation, so an unreachable server
costs one timeout, not eight.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Protocol

from explain.facts import WEEKDAY_NAMES
from explain.render import Explanation, Section

logger = logging.getLogger(__name__)

# Section keys that may be paraphrased. ``rules`` and ``caveats`` are safety statements: never reworded.
PARAPHRASE_KEYS = ("overview", "day:")

# --- validation vocabularies ------------------------------------------------------------------------------------
NUMBER_WORDS = {w: float(i) for i, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"))}
# Everyday ways to say 0. They may *satisfy* a fact's "0" but are never counted as an invented number.
ZERO_WORDS = frozenset({"no", "none", "nothing", "without"})

# Claims the facts never make. Allowed only if the facts themselves contain the word.
CLAIM_WORDS = frozenset({
    "healthy", "healthier", "healthiest", "nutritious", "wholesome", "superfood", "detox", "cure", "cures",
    "doctor", "medical", "weight", "slimming", "delicious", "tasty", "yummy", "flavorful", "flavourful", "lovely",
    "amazing", "perfect", "best", "ideal", "great", "guaranteed", "favourite", "favorite", "enjoy", "enjoyable"})

# Relative days would be new facts (the plan names weekdays). Never allowed.
RELATIVE_DAY_WORDS = frozenset({"today", "tonight", "tomorrow", "yesterday"})

# If the facts contain the key word, the rewrite must keep *some* word from its group (a synonym is fine). This stops
# a warning being paraphrased away ("is 120 kcal below your range" -> "has 480 kcal").
WARNING_GROUPS: dict[str, frozenset[str]] = {
    "below": frozenset({"below", "under", "short", "lower", "less", "beneath", "shy"}),
    "above": frozenset({"above", "over", "higher", "exceeds", "beyond", "more"}),
    "short": frozenset({"short", "below", "under", "lacks", "less", "missing", "shy"}),
    "longer": frozenset({"longer", "over", "exceeds", "beyond", "more"}),
    "dislike": frozenset({"dislike", "dislikes", "disliked", "avoid", "avoids", "hate", "hates"}),
    "unused": frozenset({"unused", "waste", "wasted", "spoil", "spoils", "spoiled", "expire", "expires", "left"}),
    "estimate": frozenset({"estimate", "estimated", "estimates", "guess", "guessed", "assumed", "approximate"}),
}
# The templates say "estimated" (and "an estimate"); the trigger is whichever word the facts actually used.
WARNING_GROUPS["estimated"] = WARNING_GROUPS["estimate"]

# Single-word canonical "ingredients" that are also ordinary English ("a meal", "a piece of", "low fat"). Counting them as
# foods would reject harmless rewrites, so they are not checked. Found by running the real model (2026-10-13); the
# other 530 single-word names are real foods.
GENERIC_WORDS = frozenset({"meal", "mix", "cold", "slice", "piece", "bar", "roll", "topping", "fat", "extract",
                           "spice", "herb"})

MAX_LENGTH_FACTOR = 1.6        # a rewrite longer than this x the facts is padding (and a place to hide new claims)
LENGTH_SLACK_CHARS = 80
DEFAULT_MAX_TOKENS = 400       # a full section reworded without dropping anything is ~150-250 tokens

# Tested against qwen3:8b on real sections (2026-10-13): asking for "2 to 4 short sentences" made the model summarise,
# and every rewrite then dropped numbers (0 of 8 accepted). "Every fact must stay, you may join sentences" accepts
# most sections. The prompt asks for completeness *because* the validator requires it.
SYSTEM_PROMPT = (
    "Reword the facts below in a warm, natural tone. Every single fact must stay: do not drop, summarise or merge "
    "away any number, food, dish name, weekday, or warning (below, above, short, longer, dislike, unused, estimated). "
    "You may join sentences. Do not add anything new: no advice, opinions, or health or taste claims. "
    "Plain text, no lists.")

_NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_WORD_RE = re.compile(r"[a-z]+")
_MARKUP_RE = re.compile(r"[*#`_>\[\]{}|]")


class TextLlm(Protocol):
    """What the paraphraser needs from an LLM client (``llm.LlmClient`` satisfies it; tests pass a stub)."""

    def complete_text(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> str: ...


@dataclass(frozen=True, slots=True)
class Paraphrase:
    """Result of one attempt: the accepted text, or ``None`` with the reasons it was not used."""

    text: str | None
    problems: tuple[str, ...] = ()


# ==================================================================================================================
# validation
# ==================================================================================================================
def stem(word: str) -> str:
    """Crude singularisation used on both sides of every comparison ("tomatoes" == "tomato")."""
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def numbers_in(text: str, loose: bool = True) -> set[float]:
    """Digit numbers (``1,200`` -> 1200) and number words (``seven`` -> 7) occurring in ``text``.

    ``one`` and ``no`` / ``none`` / ``nothing`` / ``without`` are ordinary words ("this one", "no problem"). With
    ``loose=True`` they count as 1 and 0, which is right when asking "did the rewrite *keep* the number?" ("one extra
    item" satisfies "1 extra item"; "no protein" satisfies "0 g protein"). Pass ``loose=False`` when asking "did the
    rewrite *invent* a number?", so a pronoun is never mistaken for one.
    """
    words = _WORD_RE.findall(text.lower())
    found = {round(float(m.group().replace(",", "")), 2) for m in _NUMBER_RE.finditer(text)}
    found |= {NUMBER_WORDS[w] for w in words if w in NUMBER_WORDS and (loose or w != "one")}
    if loose:
        found |= {0.0 for w in words if w in ZERO_WORDS}
    return found


def check_paraphrase(candidate: str, title: str, facts_text: str, vocabulary: frozenset[str]) -> list[str]:
    """Problems with ``candidate`` as a rewrite of ``facts_text``; an empty list means it may be used.

    Args:
        candidate: the model's answer.
        title: the section title (e.g. ``"Monday: Garlic Pasta"``). Words and days in it are allowed in the rewrite,
            but not *required* (a rewrite may omit the heading's words).
        facts_text: the section's template sentences - the only source of allowed content, and what must be kept.
        vocabulary: single-word ingredient names (``ingredient_vocabulary``), already stemmed.
    """
    text = candidate.strip()
    if not text:
        return ["empty answer"]
    problems: list[str] = []
    if "\n" in text or _MARKUP_RE.search(text):
        problems.append("contains markup or line breaks")
    if len(text) > MAX_LENGTH_FACTOR * len(facts_text) + LENGTH_SLACK_CHARS:
        problems.append("much longer than the facts it was given")

    allowed_text = f"{title} {facts_text}"
    out_words = _WORD_RE.findall(text.lower())
    src_words = _WORD_RE.findall(facts_text.lower())
    allowed_words = set(_WORD_RE.findall(allowed_text.lower()))

    # numbers: none invented, none dropped
    # strict on the facts' side (their "nothing" / "one" are words, not quantities), loose on the rewrite's side
    # when asking whether a quantity was kept
    invented_nums = numbers_in(text, loose=False) - numbers_in(allowed_text, loose=False)
    dropped_nums = numbers_in(facts_text, loose=False) - numbers_in(text, loose=True)
    if invented_nums:
        problems.append("invented number(s): " + ", ".join(f"{n:g}" for n in sorted(invented_nums)))
    if dropped_nums:
        problems.append("dropped number(s): " + ", ".join(f"{n:g}" for n in sorted(dropped_nums)))

    # foods: none invented, none dropped
    out_foods = {stem(w) for w in out_words} & vocabulary
    allowed_foods = {stem(w) for w in allowed_words} & vocabulary
    src_foods = {stem(w) for w in src_words} & vocabulary
    if out_foods - allowed_foods:
        problems.append("food(s) not in the facts: " + ", ".join(sorted(out_foods - allowed_foods)))
    if src_foods - out_foods:
        problems.append("dropped food(s): " + ", ".join(sorted(src_foods - out_foods)))

    # days: none invented (the heading's weekday is allowed), none of the facts' deadline days dropped
    weekdays = {d.lower() for d in WEEKDAY_NAMES}
    out_set, src_set = set(out_words), set(src_words)
    invented_days = (out_set & weekdays) - allowed_words
    dropped_days = (src_set & weekdays) - out_set
    if invented_days:
        problems.append("weekday(s) not in the facts: " + ", ".join(sorted(invented_days)))
    if dropped_days:
        problems.append("dropped weekday(s): " + ", ".join(sorted(dropped_days)))
    if (out_set & RELATIVE_DAY_WORDS) - allowed_words:
        problems.append("relative day word(s) not in the facts")

    # warnings kept (some synonym is enough)
    for trigger, group in WARNING_GROUPS.items():
        if trigger in src_set and not (out_set & group):
            problems.append(f"warning '{trigger}' no longer expressed")

    # unsupported claims
    claims = (out_set & CLAIM_WORDS) - allowed_words
    if claims:
        problems.append("unsupported claim(s): " + ", ".join(sorted(claims)))
    return problems


def ingredient_vocabulary(store) -> frozenset[str]:
    """Stemmed single-word canonical ingredient names: the foods whose presence is checked in a rewrite.

    Multi-word names are not added whole: their food word ("chicken" in "chicken breast") is usually also a
    single-word name, and matching on parts such as "fresh" or "ground" would reject harmless rewrites.
    """
    names = store.all_ingredients()["canonical_name"].astype(str).str.lower()
    return frozenset(stem(n) for n in names if re.fullmatch(r"[a-z]{3,}", n) and n not in GENERIC_WORDS)


# ==================================================================================================================
# paraphraser
# ==================================================================================================================
class Paraphraser:
    """Rewrites one section at a time with the LLM and validates the answer (see the module docstring)."""

    def __init__(self, client: TextLlm, vocabulary: frozenset[str], max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        self._client = client
        self._vocabulary = vocabulary
        self._max_tokens = max_tokens
        self._down = False                      # set after the first transport failure; stops further calls

    def rewrite(self, section: Section) -> Paraphrase:
        """Ask the model to reword ``section``'s statements and validate the answer."""
        if self._down:
            return Paraphrase(None, ("language model unavailable",))
        facts = section.template_text
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Section: {section.title}\nFacts:\n"
                     + "\n".join(f"- {s.text}" for s in section.statements)}]
        try:
            answer = self._client.complete_text(messages, self._max_tokens)
        except Exception as exc:                # noqa: BLE001 - any LLM failure means "keep the template"
            self._down = True
            logger.warning("paraphrase: the LLM failed (%s: %s); template text kept for the rest of this explanation",
                           type(exc).__name__, exc)
            return Paraphrase(None, (f"language model failed ({type(exc).__name__})",))
        problems = check_paraphrase(answer, section.title, facts, self._vocabulary)
        if problems:
            logger.debug("paraphrase of %r rejected: %s", section.key, "; ".join(problems))
        return Paraphrase(None, tuple(problems)) if problems else Paraphrase(answer.strip())


def paraphrase_explanation(explanation: Explanation, paraphraser: Paraphraser) -> Explanation:
    """Return ``explanation`` with each eligible section's text replaced by an accepted paraphrase.

    Rejected sections keep their template text and carry the reasons in ``Section.note``.
    """
    sections: list[Section] = []
    tried = accepted = 0
    for section in explanation.sections:
        if section.statements and section.key.startswith(PARAPHRASE_KEYS):
            tried += 1
            result = paraphraser.rewrite(section)
            if result.text is not None:
                accepted += 1
                section = replace(section, text=result.text, source="llm")
            else:
                section = replace(section, note="paraphrase not used: " + "; ".join(result.problems))
        sections.append(section)
    logger.info("paraphrase: %d of %d section(s) accepted; the rest keep their template text", accepted, tried)
    return replace(explanation, sections=tuple(sections))


def build_paraphraser(client: TextLlm | None, store) -> Paraphraser | None:
    """A paraphraser if the model is reachable, else ``None`` (an unreachable LLM is a normal situation)."""
    if client is None:
        return None
    available = getattr(client, "is_available", None)
    if callable(available) and not available():
        logger.warning("paraphrase: the LLM is not reachable; explanations keep their template text")
        return None
    return Paraphraser(client, ingredient_vocabulary(store))
