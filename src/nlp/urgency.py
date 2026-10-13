"""Urgency cue detection: "spinach getting old", "milk expires tomorrow", "use the eggs up today".

Where this sits
---------------
Runs on one fragment at a time, *before* quantity extraction, because cue phrases ("going bad", "a bit old") contain
words that would otherwise pollute the ingredient name. The result feeds the optimiser's waste term: an URGENT item
must be scheduled first; a SOON item gets a priority bump.

How urgency is expressed (and mapped)
-------------------------------------
* **Explicit time** - "expires tomorrow", "use by friday", "good for 3 days" -> an exact ``days_left`` and a level
  derived from it (<=1 day URGENT, <=4 days SOON, otherwise no urgency but the days are still reported).
* **Qualitative** - "going bad", "wilting" -> URGENT (assume 1 day); "getting old", "needs using up" -> SOON
  (assume 3 days). These two numbers are *assumptions* (see ``URGENT_DEFAULT_DAYS`` / ``SOON_DEFAULT_DAYS``); the
  FoodKeeper estimate for the ingredient can refine them downstream.

Safety
------
Words like "mouldy" or "gone off" mean the food may already be unsafe. We still report URGENT but set
``may_be_unsafe`` so the application can refuse to plan with it rather than cook it.

Negation
--------
"not going bad" must not trigger. A cue is ignored when a negator appears in the 3 words before it.

Limits
------
Only English; only weekday names and "today/tomorrow/in N days" dates (no calendar dates like "15 Oct").
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import date

from nlp.schemas import Urgency

URGENT_DEFAULT_DAYS = 1   # "going bad": assume it must be used within a day
SOON_DEFAULT_DAYS = 3     # "getting old": assume a few days of margin
SOON_THRESHOLD_DAYS = 4   # an explicit date further away than this is not treated as urgent at all

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_SMALL_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                  "eight": 8, "nine": 9, "ten": 10, "fourteen": 14}
_NEGATORS = {"not", "isn't", "isnt", "aren't", "arent", "never", "no", "don't", "dont", "hardly", "barely", "still",
             "nowhere", "far", "without"}

_WEEKDAY_RE = r"(?:this\s+|next\s+|on\s+)?(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*"
_DAY_WORD_RE = rf"(?:today|tonight|tomorrow|{_WEEKDAY_RE})"

# ----------------------------------------------------------------------------------------------------------------
# Explicit-time patterns. Each has a named group the code reads: "when" (a day word) or "n"+"unit" (a duration).
# ----------------------------------------------------------------------------------------------------------------
_EXPLICIT_WHEN = re.compile(
    r"\b(?:expires?|expiring|expired|use[- ]by|best[- ]before|bb|goes?\s+off|going\s+off|off)\s+(?:on\s+|by\s+)?"
    rf"(?P<when>{_DAY_WORD_RE})\b"
    r"|\b(?:use|eat|cook|finish)\s+(?:it\s+|them\s+|these\s+|this\s+)?(?:up\s+)?(?P<when2>today|tonight|tomorrow)\b"
    r"|\b(?:needs?|must|has\s+to|have\s+to|should)\s+(?:to\s+)?(?:be\s+)?(?:used|eaten|cooked|finished)(?:\s+up)?"
    r"\s+(?P<when3>today|tonight|tomorrow)\b",
    re.I)
_EXPLICIT_DURATION = re.compile(
    r"\b(?:expires?|expiring|goes?\s+off|good\s+for|lasts?|use\s+within|use\s+in)\s+(?:in\s+|within\s+|for\s+)?"
    r"(?P<n>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|fourteen)\s*(?P<unit>day|week)s?\b",
    re.I)
_USE_NOW = re.compile(r"\b(?:use|eat|cook)\s+(?:it\s+|them\s+|these\s+)?(?:up\s+)?(?:asap|now|first)\b", re.I)

# ----------------------------------------------------------------------------------------------------------------
# Qualitative cues. Order matters only for which phrase is *reported*; all matches are removed from the text.
# ----------------------------------------------------------------------------------------------------------------
_UNSAFE = re.compile(r"\b(?:mou?ldy|mouldy|moldy|rotten|rotting|gone\s+off|gone\s+bad|has\s+gone\s+bad|slimy|expired)\b",
                     re.I)
_URGENT = re.compile(
    r"\b(?:going\s+bad|about\s+to\s+(?:go\s+off|go\s+bad|expire|spoil|turn)|on\s+the\s+turn|going\s+off|"
    r"almost\s+(?:off|expired|gone\s+off)|expiring\s+soon|expires\s+soon|wilting|wilted|limp|going\s+soft|"
    r"over-?ripe|too\s+ripe|really\s+old|very\s+old|on\s+its\s+last\s+legs|spoiling|"
    r"must\s+(?:be\s+)?(?:use|used|eat|eaten|cook|cooked)(?:\s+up)?)\b", re.I)
_SOON = re.compile(
    r"\b(?:getting\s+(?:a\s+bit\s+|a\s+little\s+|rather\s+|pretty\s+)?old|a\s+bit\s+old|getting\s+on|ageing|aging|"
    r"past\s+(?:its|their)\s+best|starting\s+to\s+(?:go|turn|wilt|soften|go\s+off)|"
    r"(?:needs?|need)\s+(?:to\s+be\s+)?(?:using|used|eating|eaten|cooking|cooked|finishing|finished)(?:\s+up)?|"
    r"should\s+(?:be\s+)?(?:use|used|eat|eaten|cook|cooked|finish|finished)(?:\s+up)?|"
    r"(?:use|using|eat|finish)\s+(?:it\s+|them\s+|these\s+)?(?:up|soon)|from\s+last\s+week|"
    r"been\s+(?:there|here|in\s+the\s+(?:fridge|freezer|cupboard))\s+(?:a\s+while|for\s+ages|since\s+last\s+week)|"
    r"very\s+ripe|really\s+ripe|best\s+used\s+soon|need(?:s)?\s+using)\b", re.I)

# Words left dangling after a cue is cut out of "spinach that's going bad" -> "spinach that's".
_DANGLING_TAIL = re.compile(
    r"(?:\b(?:that|which|it|they|these|those|this|and|but|because|as|is|are|was|were|has|have|had|been|gone|going|"
    r"getting|a\s+bit|a\s+little|bit|very|quite|really|rather|pretty|the|are\s+all|both|all)\b"
    r"|'s|’s|'re|’re|,|;|-|–)\s*$", re.I)
_PRONOUN_ONLY = re.compile(r"^(?:it|they|them|these|those|this|that|both|all(?:\s+of\s+(?:it|them))?|everything)?$", re.I)
_SCOPE_BOTH = re.compile(r"\bboth\b", re.I)
_SCOPE_ALL = re.compile(r"\b(?:all\s+of\s+(?:it|them|that)|everything|they(?:'re|\s+are)\s+all|all\s+(?:of\s+)?the)\b", re.I)


@dataclass(frozen=True, slots=True)
class UrgencyCue:
    """A cue found in one fragment."""

    level: Urgency
    cue: str                       # the phrase as written, e.g. "going bad"
    days_left: int | None          # explicit or assumed days until it must be used (0 = today)
    may_be_unsafe: bool = False    # "mouldy", "gone off": do not plan with it blindly
    scope: str = "item"            # "item" | "both" | "all": which previous items a bare "they're going bad" covers
    explicit: bool = False         # True when the user stated a date/duration ("expires tomorrow"): a known date,
                                   # not a guess. The planner treats known dates as hard constraints.


def _days_for_weekday(word: str, today: date) -> int:
    """Days from ``today`` to the upcoming occurrence of the named weekday.

    "friday", "this friday" and "next friday" all mean the *coming* Friday: in everyday speech "next friday"
    said on a Monday almost always means this week's. The only special case is "next <today's weekday>", which
    must mean a week from today (otherwise it would be 0 and indistinguishable from "today").
    """
    text = word.strip().lower()
    key = re.sub(r"^(?:this|next|on)\s+", "", text)[:3]
    days = (_WEEKDAYS[key] - today.weekday()) % 7
    if days == 0 and text.startswith("next "):
        days = 7
    return days


def _level_for_days(days: int) -> Urgency:
    if days <= URGENT_DEFAULT_DAYS:
        return Urgency.URGENT
    if days <= SOON_THRESHOLD_DAYS:
        return Urgency.SOON
    return Urgency.NONE


def _negated(text: str, start: int) -> bool:
    """True if one of the 3 words before ``start`` is a negator ("not going bad")."""
    before = re.findall(r"[a-z’']+", text[:start].lower())[-3:]
    return any(w in _NEGATORS for w in before)


def _strip_dangling(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,;-–")
    prev = None
    while prev != text:
        prev = text
        text = _DANGLING_TAIL.sub("", text).strip(" ,;-–")
    return text


def find_urgency(fragment: str, today: date | None = None) -> tuple[UrgencyCue | None, str]:
    """Find an urgency cue in ``fragment``.

    Returns ``(cue, remainder)``. ``cue`` is ``None`` if nothing was found; ``remainder`` is the fragment with cue
    phrases (and the dangling words they leave behind) removed. If the remainder is empty or only a pronoun the
    fragment *was* just a cue ("they're going bad") and the caller should attach it to the previous item.

    >>> cue, rest = find_urgency("spinach getting old"); (cue.level.value, rest)
    ('soon', 'spinach')
    >>> from datetime import date
    >>> cue, rest = find_urgency("milk expires tomorrow", today=date(2026, 10, 12)); (cue.days_left, rest)
    (1, 'milk')
    """
    today = today or date.today()
    text = fragment
    spans: list[tuple[int, int]] = []
    best: UrgencyCue | None = None

    def consider(cue: UrgencyCue) -> None:
        nonlocal best
        rank = lambda c: (0 if c.level is Urgency.URGENT else 1 if c.level is Urgency.SOON else 2,  # noqa: E731
                          c.days_left if c.days_left is not None else 99)
        if best is None or rank(cue) < rank(best):
            best = cue

    # -- explicit "when" ------------------------------------------------------------------------------------------
    for m in _EXPLICIT_WHEN.finditer(text):
        if _negated(text, m.start()):
            continue
        when = (m.group("when") or m.group("when2") or m.group("when3")).lower().strip()
        if when in ("today", "tonight"):
            days = 0
        elif when == "tomorrow":
            days = 1
        else:
            days = _days_for_weekday(when, today)
        spans.append(m.span())
        consider(UrgencyCue(_level_for_days(days), m.group(0).strip(), days, explicit=True))

    # -- explicit duration -------------------------------------------------------------------------------------------
    for m in _EXPLICIT_DURATION.finditer(text):
        if _negated(text, m.start()):
            continue
        n_raw = m.group("n").lower()
        n = int(n_raw) if n_raw.isdigit() else _SMALL_NUMBERS[n_raw]
        days = n * (7 if m.group("unit").lower() == "week" else 1)
        spans.append(m.span())
        consider(UrgencyCue(_level_for_days(days), m.group(0).strip(), days, explicit=True))

    for m in _USE_NOW.finditer(text):
        if not _negated(text, m.start()):
            spans.append(m.span())
            consider(UrgencyCue(Urgency.URGENT, m.group(0).strip(), 0))

    # -- qualitative cues -----------------------------------------------------------------------------------------
    unsafe = False
    for m in _UNSAFE.finditer(text):
        if _negated(text, m.start()):
            continue
        unsafe = True
        spans.append(m.span())
        consider(UrgencyCue(Urgency.URGENT, m.group(0).strip(), 0, may_be_unsafe=True))
    for rx, level, days in ((_URGENT, Urgency.URGENT, URGENT_DEFAULT_DAYS), (_SOON, Urgency.SOON, SOON_DEFAULT_DAYS)):
        for m in rx.finditer(text):
            if _negated(text, m.start()):
                continue
            spans.append(m.span())
            consider(UrgencyCue(level, m.group(0).strip(), days))

    if best is None:
        return None, fragment

    scope = "all" if _SCOPE_ALL.search(text) else "both" if _SCOPE_BOTH.search(text) else "item"
    if unsafe and not best.may_be_unsafe:
        best = dataclasses.replace(best, may_be_unsafe=True)
    best = dataclasses.replace(best, scope=scope)

    # cut every matched span out of the text. Spans can overlap ("must be used" + "must be used today"),
    # so merge them first, then cut right-to-left so earlier offsets stay valid.
    merged: list[list[int]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in reversed(merged):
        text = text[:a] + " " + text[b:]
    remainder = _strip_dangling(text)
    if _PRONOUN_ONLY.match(remainder):
        remainder = ""
    return best, remainder
