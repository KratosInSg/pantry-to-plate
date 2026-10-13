"""Turn one block of free text into one fragment per pantry item.

Where this sits
---------------
First stage of the NLP pipeline. Input is whatever the user typed ("I have half a cabbage, paneer, four eggs and
spinach that's going bad"); output is a list of short fragments that the rest of the pipeline handles one at a time:
``["half a cabbage", "paneer", "four eggs", "spinach that's going bad"]``.

Why splitting is the hard part
------------------------------
People separate items with commas, "and", "&", "plus", newlines and bullets - but the same words also live *inside*
ingredient names and quantities:

* "salt **and** pepper", "half **and** half", "macaroni **and** cheese"  -> names; must stay whole.
* "one **and** a half cups of milk"                                        -> a quantity; must stay whole.
* "1,000 g flour", "1.5 kg potatoes"                                       -> numbers; no split at ``,`` / ``.``.
* "spinach (going bad, a bit slimy)"                                       -> commas inside brackets.

We solve this by *protecting* those spans with placeholder characters before splitting and restoring them after.
The list of protected ingredient phrases comes from the dataset's own alias table, so it is not hand-maintained.

Output fragments are lower-cased and whitespace-normalised.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# Characters that cannot occur in normalised input, used as placeholders while we split.
_PH_AND = "\u0001"      # protects " and " inside protected phrases / quantities
_PH_COMMA = "\u0002"    # protects "," inside brackets and thousands separators
_PH_DOT = "\u0003"      # protects "." inside decimals

_VULGAR_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅕": "1/5", "⅛": "1/8", "⅜": "3/8"}

# Lead-in phrases that carry no item ("I have ...", "In my fridge: ...").
_LEAD_INS = re.compile(
    r"^\s*(?:(?:so|well|ok(?:ay)?|hi|hello|hey|um|erm)[\s,]+)?"
    r"(?:i\s*(?:'ve|’ve|\s+have)\s+(?:got\s+)?|i\s+got\s+|we\s*(?:'ve|’ve|\s+have)\s+(?:got\s+)?|"
    r"there\s+(?:is|are)\s+|there's\s+|we\s+got\s+|my\s+(?:fridge|pantry|kitchen|cupboard)\s+(?:has|contains)\s+|"
    r"in\s+(?:my|the)\s+(?:fridge|pantry|freezer|kitchen|cupboard)\s*(?:i\s+have\s+|there\s+(?:is|are)\s+)?[:,-]?\s*|"
    r"(?:fridge|pantry|freezer|cupboard)\s*[:\-]\s*|(?:also|and\s+also|plus|oh\s+and)\s+)",
    re.I)

# Item separators. " with " is deliberately NOT here ("chicken with skin").
_SEPARATORS = re.compile(r"\s*(?:[,;\n]+|\s&\s|\band\b|\bplus\b|\balso\b|\bas well as\b|\.\s+|\s+/\s+)\s*", re.I)

# "1 and a half", "one and half" -> "1 1/2": a number phrase, not two items.
_NUMBER_WORD_DIGITS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                       "eight": "8", "nine": "9", "ten": "10"}
_AND_A_HALF = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+and\s+(?:a\s+)?half\b", re.I)

_BULLET = re.compile(r"^\s*(?:[-*•–·]|\d+[.)])\s+", re.M)


def normalise_input(text: str) -> str:
    """Canonicalise raw user text: unicode, quotes, fractions, case, whitespace.

    Kept separate from splitting so other modules (and tests) can reuse the exact same normalisation.
    """
    # Vulgar fractions FIRST: NFKC would rewrite "1½" as "11⁄2" (digits glued, fraction-slash U+2044) and lose it.
    # "1½" -> "1 1/2", "½" -> "1/2"
    for glyph, ascii_frac in _VULGAR_FRACTIONS.items():
        text = re.sub(rf"(\d){glyph}", rf"\1 {ascii_frac}", text)
        text = text.replace(glyph, ascii_frac)
    text = unicodedata.normalize("NFKC", text).replace("⁄", "/")
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.lower()
    text = _AND_A_HALF.sub(lambda m: f"{_NUMBER_WORD_DIGITS.get(m.group(1), m.group(1))} 1/2", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _protect(text: str, protected_phrases: Iterable[str]) -> str:
    """Replace separators that live inside protected phrases / brackets / numbers with placeholders."""
    # thousands separators and decimals: "1,000" and "1.5" must not be split
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", _PH_COMMA, text)
    text = re.sub(r"(?<=\d)\.(?=\d)", _PH_DOT, text)
    # anything inside brackets is one unit
    text = re.sub(r"\(([^)]*)\)",
                  lambda m: "(" + m.group(1).replace(",", _PH_COMMA).replace(" and ", _PH_AND) + ")", text)
    # known ingredient names that contain a connector, longest first so "salt and black pepper" beats "salt and pepper"
    for phrase in sorted(protected_phrases, key=len, reverse=True):
        if phrase in text:
            text = re.sub(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])",
                          lambda m: m.group(0).replace(" and ", _PH_AND).replace(" & ", _PH_AND), text)
    return text


def _restore(fragment: str) -> str:
    return fragment.replace(_PH_AND, " and ").replace(_PH_COMMA, ",").replace(_PH_DOT, ".")


def split_items(text: str, protected_phrases: Iterable[str] = ()) -> list[str]:
    """Split ``text`` into per-item fragments.

    ``protected_phrases`` are lower-case ingredient names containing a connector ("salt and pepper"); pass
    ``store.connector_phrases``. Empty fragments and bare filler words are dropped.

    >>> split_items("I have half a cabbage, paneer, four eggs and spinach getting old")
    ['half a cabbage', 'paneer', 'four eggs', 'spinach getting old']
    >>> split_items("salt and pepper, 1 and a half cups of milk", ["salt and pepper"])
    ['salt and pepper', '1 1/2 cups of milk']
    """
    text = normalise_input(text)
    text = _BULLET.sub("", text)
    # strip a leading lead-in on the whole message, and on every line ("fridge: ...")
    lines = [_LEAD_INS.sub("", ln) for ln in text.split("\n")]
    text = "\n".join(lines)
    protected = _protect(text, protected_phrases)
    pieces = _SEPARATORS.split(protected)
    out: list[str] = []
    for piece in pieces:
        frag = _restore(piece or "").strip(" .,:;-–")
        frag = _LEAD_INS.sub("", frag).strip()            # "... and also some milk" -> lead-in after a separator
        if frag and frag not in ("and", "also", "plus", "the", "a", "some"):
            out.append(frag)
    return out
