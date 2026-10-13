"""Quantity extraction from one pantry fragment ("2 cups chopped spinach", "half a cabbage", "4 eggs").

Where this sits
---------------
``segmenter`` has already split the user's message into one fragment per item. This module peels the *amount* off the
front (or back) of a fragment and returns the rest, which is then handed to the ingredient resolver. It is pure text
processing: no dataset, no I/O, easy to unit test.

What it understands
-------------------
* digits, decimals, fractions, mixed numbers:   ``2``  ``1.5``  ``1/2``  ``1 1/2``
* ranges (lower bound is used - see below):      ``2-3``  ``2 to 3``
* number words:                                  ``four``  ``twelve``  ``a dozen``  ``half a dozen``
* fraction words:                                ``half a cabbage``  ``a quarter of an onion``  ``three quarters``
* units, glued or spaced:                        ``500g``  ``2 tbsp``  ``1 lb``  ``3 cloves``  ``1 can``  ``fl oz``
* pack multipliers:                              ``2 x 400g tins tomatoes``  (= 800 g)
* an explicit weight in brackets:                ``1 can (400g) chickpeas``
* trailing forms:                                ``eggs x4``  ``milk 1l``  ``carrots - 5``
* vague words:                                   ``some``  ``a few``  ``a couple of``  ``a little``

Design decisions worth knowing
------------------------------
1. **Ranges use the lower bound.** "2-3 carrots" -> 2. For *supply* planning it is safer to assume the user has what
   they are sure of; over-counting leads to a plan they cannot cook.
2. **Vague words are returned as words, not numbers.** The parser decides what "some" means because that depends on
   the ingredient (some salt != some chicken). We only report which word was used.
3. **"a" / "an" means 1** when it leads the fragment ("a can of tuna").
4. **No guessing about the ingredient here.** We never look at the name; "5 spice powder" is the one guarded
   exception because a leading digit there is part of the name, not a quantity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from nlp.defaults import VAGUE_AMOUNT_FACTOR, VAGUE_COUNT

# ---------------------------------------------------------------------------------------------------------------
# Unit vocabulary. Canonical names for the physical units MUST match data/canonical/reference/unit_conversion.csv
# (a test enforces this) because the knowledge store converts them to grams/ml using that file.
# ---------------------------------------------------------------------------------------------------------------
_PHYSICAL_UNIT_ALIASES: dict[str, tuple[str, ...]] = {
    "g": ("g", "gr", "gm", "gms", "gram", "grams"),
    "kg": ("kg", "kgs", "kilo", "kilos", "kilogram", "kilograms"),
    "mg": ("mg", "milligram", "milligrams"),
    "oz": ("oz", "ounce", "ounces"),
    "lb": ("lb", "lbs", "pound", "pounds"),
    "ml": ("ml", "milliliter", "milliliters", "millilitre", "millilitres"),
    "l": ("l", "liter", "liters", "litre", "litres", "ltr"),
    "tsp": ("tsp", "tsps", "teaspoon", "teaspoons"),
    "tbsp": ("tbsp", "tbsps", "tbs", "tbl", "tablespoon", "tablespoons"),
    "cup": ("cup", "cups"),
    "fl_oz": ("floz",),  # "fl oz" is two tokens and is handled separately
    "pint": ("pint", "pints", "pt"),
    "quart": ("quart", "quarts", "qt"),
    "gallon": ("gallon", "gallons", "gal"),
    "pinch": ("pinch", "pinches"),
    "dash": ("dash", "dashes"),
}
_COUNT_UNIT_ALIASES: dict[str, tuple[str, ...]] = {
    "can": ("can", "cans", "tin", "tins"),
    "jar": ("jar", "jars"),
    "bottle": ("bottle", "bottles"),
    "package": ("package", "packages", "pack", "packs", "packet", "packets", "pkt", "pkts"),
    "bag": ("bag", "bags"),
    "box": ("box", "boxes"),
    "carton": ("carton", "cartons"),
    "tub": ("tub", "tubs"),
    "container": ("container", "containers"),
    "bunch": ("bunch", "bunches"),
    "head": ("head", "heads"),
    "clove": ("clove", "cloves"),
    "slice": ("slice", "slices"),
    "piece": ("piece", "pieces", "pc", "pcs"),
    "stalk": ("stalk", "stalks"),
    "sprig": ("sprig", "sprigs"),
    "stick": ("stick", "sticks"),
    "fillet": ("fillet", "fillets", "filet", "filets"),
    "breast": ("breast", "breasts"),
    "thigh": ("thigh", "thighs"),
    "leg": ("leg", "legs"),
    "loaf": ("loaf", "loaves"),
    "handful": ("handful", "handfuls"),
    "bulb": ("bulb", "bulbs"),
    "ear": ("ear", "ears"),
    "strip": ("strip", "strips"),
    "wedge": ("wedge", "wedges"),
    "leaf": ("leaf", "leaves"),
    "pod": ("pod", "pods"),
    "cube": ("cube", "cubes"),
    "patty": ("patty", "patties"),
    "bar": ("bar", "bars"),
    "roll": ("roll", "rolls"),
}
UNIT_ALIASES: dict[str, str] = {a: u for u, al in {**_PHYSICAL_UNIT_ALIASES, **_COUNT_UNIT_ALIASES}.items() for a in al}
PHYSICAL_UNITS: frozenset[str] = frozenset(_PHYSICAL_UNIT_ALIASES)
MASS_UNITS: frozenset[str] = frozenset({"g", "kg", "mg", "oz", "lb"})
# Containers that merely *wrap* an explicit weight: in "2 x 400g tins tomatoes" the word "tins" adds nothing.
_CONTAINER_WORDS = frozenset(a for u in ("can", "jar", "bottle", "package", "bag", "box", "carton", "tub", "container")
                             for a in _COUNT_UNIT_ALIASES[u])

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}
_FRACTION_WORDS = {"half": 0.5, "halves": 0.5, "quarter": 0.25, "quarters": 0.25, "third": 1 / 3, "thirds": 1 / 3}
# Public read-only views, used by ``nlp.llm_fallback`` to check that a number the LLM reports is really in the text.
NUMBER_WORDS = _NUMBER_WORDS
FRACTION_WORDS = _FRACTION_WORDS
_SIZE_WORDS = {"small": "small", "medium": "medium", "large": "large", "big": "large", "huge": "xlarge",
               "xl": "xlarge", "extra-large": "xlarge", "mini": "small"}
_FILLERS = frozenset({"of", "the", "my", "our", "some", "these", "those", "this", "that", "about", "approx", "approximately",
                      "around", "roughly", "~"})
_PACK_SEPARATORS = frozenset({"x", "×", "*"})

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_FRAC_RE = re.compile(r"^(\d+)/(\d+)$")
_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?(?:/\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?(?:/\d+)?)$")

# Vague phrases as token tuples, longest first so "a little bit of" wins over "a little".
_VAGUE_PHRASES: tuple[tuple[str, ...], ...] = tuple(sorted(
    (tuple(p.split()) for p in {*VAGUE_COUNT, *VAGUE_AMOUNT_FACTOR}), key=len, reverse=True))


@dataclass(frozen=True, slots=True)
class Quantity:
    """The amount found in a fragment. All fields are optional because users are vague."""

    value: float | None            # number in ``unit``; None when only a vague word was given
    unit: str | None               # canonical unit ("cup", "g", "clove"); None = whole items
    explicit_grams: float | None   # a mass the user stated, even if the unit is a container ("1 can (400g)")
    vague_word: str | None         # "some", "a few" ... when no exact number was given
    is_range: bool                 # "2-3": value holds the lower bound
    size: str | None               # small | medium | large | xlarge when stated
    text: str                      # the words consumed, e.g. "half a" or "2 x 400 g tins"


# ================================================================================================================
# Token helpers
# ================================================================================================================
def _tokenise(fragment: str) -> list[str]:
    """Lower-case and split into tokens, un-gluing "500g" -> "500 g", "x4" -> "x 4", "(400g)" -> "( 400 g )"."""
    s = fragment.lower().replace("×", " x ")
    s = re.sub(r"(\d)([a-z])", r"\1 \2", s)       # 500g, 2tbsp, 1.5kg
    s = re.sub(r"\b(x)(\d)", r"\1 \2", s)          # x4
    # "eggs6" -> "eggs 6", but leave "b12" / "v8" alone: the digits there belong to the name (vitamin b12, v8 juice)
    s = re.sub(r"([a-z])(\d)", lambda m: m.group(0) if m.group(1) in "bv" else f"{m.group(1)} {m.group(2)}", s)
    s = s.replace("(", " ( ").replace(")", " ) ")
    s = re.sub(r"\bfl\.?\s*oz\.?\b", "floz", s)    # make "fl oz" one token
    s = re.sub(r"[,;:]", " ", s)
    s = re.sub(r"(?<=[a-z])\.(?=\s|$)", "", s)     # "tbsp." -> "tbsp"
    return s.split()


def parse_number_token(token: str) -> tuple[float, bool] | None:
    """Parse one token as a number. Returns ``(value, is_range)`` or ``None``.

    Handles ``2``, ``1.5``, ``1/2`` and ranges ``2-3`` / ``1/2-1``. Ranges return their lower bound.
    """
    if _NUM_RE.match(token):
        return float(token), False
    m = _FRAC_RE.match(token)
    if m and int(m.group(2)) != 0:
        return int(m.group(1)) / int(m.group(2)), False
    m = _RANGE_RE.match(token)
    if m:
        lo = parse_number_token(m.group(1))
        return (lo[0], True) if lo else None
    return None


def _is_unit(token: str) -> bool:
    return token in UNIT_ALIASES


def _number_phrase(tokens: list[str], i: int) -> tuple[float, bool, int] | None:
    """Parse a numeric phrase starting at ``i``. Returns ``(value, is_range, next_index)`` or ``None``.

    Grammar (informal):  NUMBER [FRACTION-OF-1/2] ["and a half"] [fraction-word ["of"] ["a"|"an"]] ["dozen"]
    e.g. "2", "1 1/2", "one and a half", "half a", "three quarters of a", "a dozen", "half a dozen".
    """
    n = len(tokens)
    if i >= n:
        return None
    t = tokens[i]
    is_range = False
    j = i + 1
    parsed = parse_number_token(t)
    if parsed is not None:
        base, is_range = parsed
        # mixed number: "1 1/2"
        if not is_range and float(base).is_integer() and j < n and _FRAC_RE.match(tokens[j]):
            frac = parse_number_token(tokens[j])
            if frac:
                base += frac[0]
                j += 1
    elif t in _NUMBER_WORDS:
        base = float(_NUMBER_WORDS[t])
    elif t in ("a", "an"):
        base = 1.0
    elif t in _FRACTION_WORDS:
        base, j = 1.0, i          # let the fraction branch below consume the word itself
    else:
        return None

    # "one and a half" / "two and a half"
    if j + 1 < n and tokens[j] == "and":
        k = j + 1
        if k < n and tokens[k] in ("a", "an"):
            k += 1
        if k < n and tokens[k] == "half":
            base += 0.5
            j = k + 1

    # fraction word: "half", "quarter(s)", "third(s)" -> scale, then swallow "of"/"a"/"an"
    if j < n and tokens[j] in _FRACTION_WORDS:
        base *= _FRACTION_WORDS[tokens[j]]
        j += 1
        while j < n and tokens[j] in ("of", "a", "an"):
            j += 1

    # "a dozen", "2 dozen", "half a dozen"
    if j < n and tokens[j] in ("dozen", "dozens"):
        base *= 12
        j += 1
    return base, is_range, j


def _match_vague(tokens: list[str], i: int) -> tuple[str, int] | None:
    """Return (phrase, next_index) if a vague phrase starts at ``i``."""
    for phrase in _VAGUE_PHRASES:
        if tuple(tokens[i:i + len(phrase)]) == phrase:
            return " ".join(phrase), i + len(phrase)
    return None


def _take_unit(tokens: list[str], j: int) -> tuple[str | None, int]:
    """If a unit word is at ``j`` consume it (skipping a following "of")."""
    if j < len(tokens) and _is_unit(tokens[j]):
        unit = UNIT_ALIASES[tokens[j]]
        j += 1
        if j < len(tokens) and tokens[j] == "of":
            j += 1
        return unit, j
    return None, j


def _to_grams(value: float, unit: str) -> float | None:
    """Convert a mass to grams using fixed physical constants (volumes need an ingredient, so return None)."""
    factors = {"g": 1.0, "kg": 1000.0, "mg": 0.001, "oz": 28.3495, "lb": 453.592}
    return round(value * factors[unit], 2) if unit in factors else None


# ================================================================================================================
# Public API
# ================================================================================================================
_LEAD_CHATTER = frozenset({"i", "have", "got", "there", "is", "are", "we", "ive", "about", "approx", "approximately",
                           "around", "roughly", "~", "the", "my", "our"})


def extract_quantity(fragment: str) -> tuple[Quantity | None, str]:
    """Split ``fragment`` into its quantity and the remaining words.

    Returns ``(quantity, remainder)``. ``quantity`` is ``None`` when the fragment states no amount at all
    ("paneer"); ``remainder`` is the fragment with the amount (and size words) removed, lower-cased.

    >>> extract_quantity("2 cups chopped baby spinach")[1]
    'chopped baby spinach'
    >>> q, rest = extract_quantity("half a cabbage"); (q.value, q.unit, rest)
    (0.5, None, 'cabbage')
    >>> q, rest = extract_quantity("2 x 400g tins chopped tomatoes"); (q.explicit_grams, rest)
    (800.0, 'chopped tomatoes')
    """
    tokens = _tokenise(fragment)
    if not tokens:
        return None, ""

    tokens, explicit_grams, bracket_text = _pull_bracketed_weight(tokens)

    # Leading chatter and approximators are not part of the amount ("about 200g", "i have 3 eggs").
    i = 0
    while i < len(tokens) and tokens[i] in _LEAD_CHATTER:
        i += 1

    found = _leading_quantity(tokens, i)
    if found is not None:
        value, unit, vague, is_range, qty_tokens, i = found
        remainder = tokens[i:]
        if unit in MASS_UNITS and value is not None and explicit_grams is None:
            explicit_grams = _to_grams(value, unit)
    else:
        remainder, value, unit, is_range, qty_tokens, explicit_grams = _trailing_quantity(tokens[i:], explicit_grams)
        vague = None

    size, rest = _pull_size(remainder)
    # a dangling "of"/article is a leftover of the quantity phrase ("2 cups OF milk", "a can OF tuna")
    while rest and rest[0] in ("of", "a", "an", "the"):
        rest = rest[1:]
    remainder_text = " ".join(rest)

    if value is None and vague is None and explicit_grams is None and size is None:
        return None, remainder_text

    text = " ".join(([bracket_text] if bracket_text else []) + qty_tokens).strip()
    return Quantity(value=value, unit=unit, explicit_grams=explicit_grams, vague_word=vague, is_range=is_range,
                    size=size, text=text), remainder_text


# ----------------------------------------------------------------------------------------------------------------
# Steps of extract_quantity (kept separate so each can be read, and tested, on its own)
# ----------------------------------------------------------------------------------------------------------------
def _pull_bracketed_weight(tokens: list[str]) -> tuple[list[str], float | None, str]:
    """Remove ``( 400 g )`` style brackets; return (tokens_without, grams_if_a_mass, text_consumed).

    A bracket holding a mass is an explicit weight for the container ("1 can (400g) chickpeas"). A bracket holding
    anything else ("(going bad)", "(frozen)") keeps its words but loses the bracket characters.
    """
    out: list[str] = []
    grams: float | None = None
    consumed = ""
    k = 0
    while k < len(tokens):
        if tokens[k] != "(":
            out.append(tokens[k])
            k += 1
            continue
        end = tokens.index(")", k) if ")" in tokens[k:] else len(tokens)
        inner = [t for t in tokens[k + 1:end] if t not in _FILLERS]
        num = parse_number_token(inner[0]) if len(inner) == 2 else None
        if num and inner[1] in UNIT_ALIASES and UNIT_ALIASES[inner[1]] in MASS_UNITS and grams is None:
            grams = _to_grams(num[0], UNIT_ALIASES[inner[1]])
            consumed = "(" + " ".join(inner) + ")"
        else:
            out.extend(tokens[k + 1:end])
        k = end + 1
    return out, grams, consumed


def _leading_quantity(tokens: list[str], i: int):
    """Parse an amount that starts at ``i``.

    Returns ``(value, unit, vague_word, is_range, consumed_tokens, next_index)`` or ``None`` if the fragment does
    not start with an amount.
    """
    n = len(tokens)
    if i >= n:
        return None

    # (a) pack multiplier: "2 x 400 g"
    if (i + 3 < n and parse_number_token(tokens[i]) and tokens[i + 1] in _PACK_SEPARATORS
            and parse_number_token(tokens[i + 2]) and tokens[i + 3] in UNIT_ALIASES
            and UNIT_ALIASES[tokens[i + 3]] in PHYSICAL_UNITS):
        value = parse_number_token(tokens[i])[0] * parse_number_token(tokens[i + 2])[0]
        j = i + 4
        # "tins"/"cans" after the weight only describe the packaging
        if j < n and tokens[j] in _CONTAINER_WORDS:
            j += 1
        return value, UNIT_ALIASES[tokens[i + 3]], None, False, tokens[i:j], j

    # (b) vague phrase: "some", "a few", "a couple of", "a little"
    hit = _match_vague(tokens, i)
    if hit:
        phrase, j = hit
        value = float(VAGUE_COUNT[phrase]) if phrase in VAGUE_COUNT else None   # "a few" -> 3 items
        k = j
        while k < n and tokens[k] in _FILLERS:
            k += 1
        unit, k2 = _take_unit(tokens, k)                                           # "a few cloves of garlic"
        end = k2 if unit else j
        return value, unit, phrase, False, tokens[i:end], end

    # (c) numeric phrase: "2", "1 1/2", "half a", "a dozen", ...
    num = _number_phrase(tokens, i)
    if num is None:
        return None
    value, is_range, j = num
    # "5 spice powder", "7 up": the digit belongs to the name, it is not a count
    if parse_number_token(tokens[i]) and j < n and tokens[j] in ("spice", "up"):
        return None
    k = j
    while k < n and tokens[k] in _FILLERS and tokens[k] != "of":
        k += 1
    unit, k2 = _take_unit(tokens, k)
    if unit:
        j = k2
        # "400 g tins": a container word right after a physical unit is just packaging
        if unit in PHYSICAL_UNITS and j < n and tokens[j] in _CONTAINER_WORDS:
            j += 1
    return value, unit, None, is_range, tokens[i:j], j


def _pull_size(tokens: list[str]) -> tuple[str | None, list[str]]:
    """Remove the first size word ("large", "small") from ``tokens`` and return it."""
    size = None
    rest: list[str] = []
    for t in tokens:
        if t in _SIZE_WORDS and size is None:
            size = _SIZE_WORDS[t]
        else:
            rest.append(t)
    return size, rest


def _trailing_quantity(tokens: list[str], explicit_grams: float | None):
    """Find an amount at the end of the fragment ("eggs x 4", "milk 1 l", "carrots - 5") or embedded in it.

    Returns ``(remaining_tokens, value, unit, is_range, consumed_tokens, explicit_grams)``.
    """
    n = len(tokens)

    def mass(v: float, u: str | None) -> float | None:
        return _to_grams(v, u) if (u in MASS_UNITS and explicit_grams is None) else explicit_grams

    # "... x 4"
    if n >= 3 and tokens[-2] in _PACK_SEPARATORS and parse_number_token(tokens[-1]):
        v, rng = parse_number_token(tokens[-1])
        return tokens[:-2], v, None, rng, tokens[-2:], explicit_grams
    # "... 1 l" / "... 6 pcs"
    if n >= 3 and parse_number_token(tokens[-2]) and tokens[-1] in UNIT_ALIASES:
        v, rng = parse_number_token(tokens[-2])
        u = UNIT_ALIASES[tokens[-1]]
        return tokens[:-2], v, u, rng, tokens[-2:], mass(v, u)
    # "... - 5" or "... 5": a bare trailing number reads as a count of items
    if n >= 2 and parse_number_token(tokens[-1]):
        v, rng = parse_number_token(tokens[-1])
        body = tokens[:-1]
        if body and body[-1] in ("-", "–"):
            body = body[:-1]
        return body, v, None, rng, tokens[-1:], explicit_grams
    # embedded: "chopped 2 cups spinach"
    for k in range(n - 1):
        if parse_number_token(tokens[k]) and tokens[k + 1] in UNIT_ALIASES:
            v, rng = parse_number_token(tokens[k])
            u = UNIT_ALIASES[tokens[k + 1]]
            return tokens[:k] + tokens[k + 2:], v, u, rng, tokens[k:k + 2], mass(v, u)
    return tokens, None, None, False, [], explicit_grams
