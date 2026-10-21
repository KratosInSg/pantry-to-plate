"""Synthetic pantry messages: each v3 kitchen written the way a person might type it, with the answer key kept.

Why this exists
---------------
Evaluation measure 7 (ingredient NLP: precision, recall, F1) needs pantry text with known answers. The proposal
planned a manually written and labelled set; that set was never built. This module builds the next best thing, and
says so: a **synthetic** set. Every message is generated from a frozen benchmark kitchen (``data/evaluation/v3``), so
its answer key - which ingredients, how much, how urgent - comes from the generator rather than from a human
annotator. The same messages double as realistic demo input: paste one into the app and it plans that kitchen's week.

What a message looks like
-------------------------
    "We've got 2 onions, 450g chicken breast, half a cabbage that's going bad, some spinach (use by Friday),
     a can of kidney beans and 300 ml milk"

Each pantry item becomes one phrase: a *name*, an optional *amount* and an optional *urgency cue*.

* **Names** (``name_variant``): mostly the ingredient's most common name in the recipe data (``top``); some use a less
  common real alias (``variant``: "yellow onion", "firm tofu"); some use Singapore/British usage the US-sourced
  vocabulary may not know (``regional``: "prawns", "courgette", "minced beef", "capsicum"); some add a harmless word
  (``descriptor``: "fresh", "organic", "local"); a few carry one typing error (``typo``). The variants exist so the
  score says *where* the parser fails, not just how often.
* **Amounts** (``quantity.form``): metric mass ("450g", "1.2 kg"), whole items ("2 onions", "half a cabbage"),
  volume ("300 ml milk", "2 cups of rice"), containers ("a can of", "a bunch of", "a pack of") or none ("some
  spinach").
* **Urgency**: a stated date for items whose use-by date the kitchen *knows* ("expires tomorrow", "use by Friday"),
  a qualitative cue for items whose estimate says they must go within a day ("going bad", "getting old"), nothing
  otherwise.

Independence from the parser
----------------------------
The phrasing lists below were written from how people describe food, not from the parser's vocabulary, and the set is
frozen (SHA-256) before the parser ever sees it (``freeze_messages``). Nothing here imports the NLP layer. A cue the
parser does not know, or a name the alias table lacks, is meant to count against it.

Answer key conventions
----------------------
* ``ingredient_id``: the kitchen's canonical ingredient (the name variant never changes it).
* ``quantity``: what the *text* says - ``{"form", "value", "unit"}`` plus ``grams`` for metric mass and ``ml`` for
  metric volume. ``unit`` is ``None`` for a bare count of whole items. ``form == "none"`` means no amount was given.
* ``urgency``: ``none`` / ``soon`` / ``urgent``. Stated dates follow the parser's documented scale (<= 1 day urgent,
  <= 4 days soon), qualitative cues are labelled by their wording (``URGENT_CUES`` / ``SOON_CUES``).
* ``days_left``: only for stated dates (``explicit``), counted from the message's ``today`` (day 0).

Usage::

    python src/evaluation/pantry_messages.py --eval-dir data/evaluation/v3      # write + freeze (refuses if frozen)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zlib
from datetime import date, timedelta
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/pantry_messages.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from domain.models import PantryItem, Scenario
from knowledge.store import KnowledgeStore

MESSAGES_VERSION = "m1"
DEFAULT_SEED = 20261021
# Day 0 of each kitchen's week is the date in the week of this Monday that has the kitchen's start weekday, so
# "use by Friday" means the same day to the generator and to anyone parsing the text.
REFERENCE_MONDAY = date(2026, 10, 26)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# ----------------------------------------------------------------------------------------------- phrasing lists
URGENT_CUES = ("going bad", "about to go off", "going off", "on its last legs")
SOON_CUES = ("getting old", "needs using soon", "should be used soon", "not so fresh anymore")
_VERB_CUES = frozenset({"needs using soon", "should be used soon"})       # read "that needs ...", not "that's needs"
TODAY_PHRASES = ("expires today", "use by today", "has to be used today")
TOMORROW_PHRASES = ("expires tomorrow", "use by tomorrow", "best before tomorrow")
WEEKDAY_PHRASES = ("use by {day}", "expires on {day}", "good until {day}")
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
OPENINGS = ("I have ", "We've got ", "In my fridge: ", "Pantry: ", "Got ", "Things at home: ")
CLOSINGS = (" and that's it", ". That's all", " - that's everything")
DESCRIPTORS = {"produce": ("fresh", "organic", "local"), "perishable": ("fresh", "organic"), "other": ("organic",)}
PRODUCE_GROUPS = frozenset({"vegetable", "fruit", "herb_spice"})
PERISHABLE_GROUPS = frozenset({"meat", "poultry", "seafood", "dairy", "egg"})

# Singapore / British names for foods the vocabulary knows by their US name (canonical name -> what a user here types).
REGIONAL_NAMES: dict[str, tuple[str, ...]] = {
    "zucchini": ("courgette", "courgettes"), "shrimp": ("prawns",), "scallion": ("spring onions",),
    "green onion": ("spring onions",), "ground beef": ("minced beef", "beef mince"),
    "lean ground beef": ("lean minced beef",), "ground pork": ("minced pork", "pork mince"),
    "ground chicken": ("minced chicken",), "ground turkey": ("minced turkey",), "all-purpose flour": ("plain flour",),
    "green pepper": ("green capsicum",), "red bell pepper": ("red capsicum",), "yellow bell pepper": ("yellow capsicum",),
    "bell pepper": ("capsicum",), "eggplant": ("brinjal", "aubergine"), "cilantro": ("coriander leaves",),
    "corn": ("sweetcorn",), "powdered sugar": ("icing sugar",), "cornstarch": ("cornflour",), "arugula": ("rocket",),
    "beet": ("beetroot",), "snow pea": ("mangetout",), "heavy cream": ("double cream",),
}
REGIONAL_SHARE = 0.5           # share of eligible items written with a regional name
NAME_VARIANT_P = {"top": 0.68, "variant": 0.15, "descriptor": 0.10, "typo": 0.07}
FORM_P = {"mass": 0.40, "count": 0.25, "volume": 0.10, "container": 0.10, "none": 0.15}
# people count eggs and most fruit/veg, and measure liquids by volume - the form mix follows the food
FORM_P_EGG = {"count": 0.85, "none": 0.15}
FORM_P_COUNTABLE_PRODUCE = {"count": 0.50, "mass": 0.25, "container": 0.10, "none": 0.15}
FORM_P_LIQUID = {"volume": 0.45, "mass": 0.15, "container": 0.20, "none": 0.20}

# whole-item units that read naturally as "2 X" (bare count) or "2 <unit>s of X"
_BARE_COUNT_UNITS = frozenset({"each", "piece", "fillet"})
_OF_COUNT_UNITS = frozenset({"head", "bunch", "stalk", "bulb"})
_BARE_COUNT_GROUPS = frozenset({"vegetable", "fruit", "egg"})
_CUT_WORDS = ("breast", "thigh", "drumstick", "wing", "fillet", "leg", "steak", "chop")   # countable meat/fish cuts
_LIQUID_WORDS = frozenset({"milk", "cream", "broth", "stock", "juice", "oil", "sauce", "yogurt", "buttermilk", "vinegar",
                           "soup", "water", "wine"})
_NOT_LIQUID = ("cream cheese", "sour cream", "ice cream", "whipped cream", "cream of ")
_DRY_CUP_GROUPS = frozenset({"grain_pasta", "legume", "nut_seed", "sweetener"})
_SPICE_WORDS = ("ground", "dried", "powder", "flake", "seed", "paprika", "cumin", "cinnamon", "nutmeg", "turmeric",
                "masala", "curry", "pepper", "oregano", "chili", "chilli", "allspice", "cardamom", "bay", "clove")
_ML_PER_CUP = 236.588
_WORD_RE = re.compile(r"^[a-z][a-z' -]*[a-z]$")


def _is_liquid(canonical: str) -> bool:
    if any(canonical.startswith(x) or canonical == x.strip() for x in _NOT_LIQUID):
        return False
    return canonical.split()[-1] in _LIQUID_WORDS


def _containers(canonical: str, group: str) -> tuple[tuple[str, str], ...]:
    """Containers a person would name for this food: (word written, unit recorded in the answer key)."""
    if _is_liquid(canonical):
        if group == "soup_broth":
            return (("can", "can"), ("carton", "carton"))
        if canonical.split()[-1] in ("sauce", "vinegar", "oil", "wine"):
            return (("bottle", "bottle"),)
        return (("carton", "carton"),)
    if group == "legume":
        if "tofu" in canonical:
            return (("block", "block"),)
        return (("bag", "bag"),) if "dried" in canonical else (("can", "can"), ("tin", "can"))
    if group == "soup_broth":
        return (("can", "can"), ("tin", "can"))
    if group == "sauce_condiment":
        return (("jar", "jar"), ("bottle", "bottle"))
    if group == "dairy":
        if "cheese" in canonical and not canonical.startswith(("cream cheese", "cottage")):
            return (("block", "block"), ("pack", "package"))
        return (("tub", "tub"),)
    if group == "grain_pasta":
        return (("packet", "package"), ("bag", "bag"))
    if group == "bakery":
        if "crumb" in canonical:
            return (("packet", "package"), ("bag", "bag"))
        return (("loaf", "loaf"),) if canonical.split()[-1] == "bread" else (("pack", "package"),)
    if group in ("meat", "poultry"):
        return (("pack", "package"), ("tray", "tray"))
    if group == "seafood":
        return (("pack", "package"),)
    if group == "herb_spice":
        return (("jar", "jar"),) if any(w in canonical for w in _SPICE_WORDS) else (("bunch", "bunch"),)
    if group in ("vegetable", "fruit", "nut_seed"):
        return (("bag", "bag"),)
    return ()


# ================================================================================================================
# names
# ================================================================================================================
class _Names:
    """Surface names per ingredient, from the alias table (cached per store)."""

    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        a = store._aliases                                                     # noqa: SLF001 - read-only table
        a = a[a.alias_source.isin(["foodcom_raw", "foodcom_canonical", "canonical", "synonym"]) & ~a.is_split]
        self._by_id: dict[int, list[tuple[str, int]]] = {}
        for alias, iid, n in zip(a.alias, a.ingredient_id, a.n_occurrences):
            if _WORD_RE.match(alias) and len(alias.split()) <= 4 and store.lookup_alias(alias) == (int(iid),):
                self._by_id.setdefault(int(iid), []).append((alias, int(n)))

    def top(self, iid: int) -> str:
        """The most frequent short alias (at most 3 words), else the canonical name."""
        info = self.store.ingredient(iid)
        options = [(a, n) for a, n in self._by_id.get(iid, []) if len(a.split()) <= 3]
        if not options:
            return info.canonical_name
        best = max(n for _, n in options)
        if best == 0:
            return info.canonical_name
        return sorted((a for a, n in options if n == best), key=len)[0]

    def variants(self, iid: int, top: str) -> list[tuple[str, int]]:
        """Other real aliases people use (seen at least 20 times), excluding the top name and its plural."""
        plural = pluralise(top)
        return [(a, n) for a, n in self._by_id.get(iid, []) if n >= 20 and a not in (top, plural)]

    def plural(self, iid: int, name: str) -> str:
        """Plural of ``name`` (spelling rule; the alias table's plurals follow the same rule)."""
        return pluralise(name)


def pluralise(name: str) -> str:
    """English plural of the last word ("tomato" -> "tomatoes", "chicken breast" -> "chicken breasts")."""
    words = name.split()
    w = words[-1]
    if w.endswith(("s", "x", "z", "ch", "sh")):
        w = w + "es" if not w.endswith("s") else w
    elif w.endswith("y") and len(w) > 1 and w[-2] not in "aeiou":
        w = w[:-1] + "ies"
    elif w.endswith("o") and w in ("tomato", "potato", "mango"):
        w = w + "es"
    else:
        w = w + "s"
    return " ".join(words[:-1] + [w])


def _typo(name: str, rng: np.random.Generator) -> str:
    """One realistic typing error in the longest word (not its first letter): swap, drop or double a letter."""
    words = name.split()
    k = max(range(len(words)), key=lambda j: len(words[j]))
    w = words[k]
    if len(w) < 5:
        return name
    i = int(rng.integers(1, len(w) - 1))
    kind = int(rng.integers(0, 3))
    if kind == 0:
        w = w[:i] + w[i + 1] + w[i] + w[i + 2:]
    elif kind == 1:
        w = w[:i] + w[i + 1:]
    else:
        w = w[:i] + w[i] + w[i:]
    words[k] = w
    return " ".join(words)


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


# ================================================================================================================
# one item
# ================================================================================================================
def _pick(rng: np.random.Generator, options: dict[str, float]) -> str:
    keys = list(options)
    p = np.array([options[k] for k in keys], dtype=float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def _name(item: PantryItem, names: _Names, group: str, rng: np.random.Generator) -> tuple[str, str]:
    """(surface name, name_variant)."""
    canonical = names.store.ingredient(item.ingredient_id).canonical_name
    top = names.top(item.ingredient_id)
    if canonical in REGIONAL_NAMES and rng.random() < REGIONAL_SHARE:
        options = REGIONAL_NAMES[canonical]
        return options[int(rng.integers(0, len(options)))], "regional"
    kind = _pick(rng, NAME_VARIANT_P)
    if kind == "variant":
        vs = names.variants(item.ingredient_id, top)
        if vs:
            w = np.sqrt(np.array([n for _, n in vs], dtype=float))
            return vs[int(rng.choice(len(vs), p=w / w.sum()))][0], "variant"
        kind = "top"
    if kind == "descriptor":
        pool = DESCRIPTORS["produce" if group in PRODUCE_GROUPS else
                           "perishable" if group in PERISHABLE_GROUPS else "other"]
        return f"{pool[int(rng.integers(0, len(pool)))]} {top}", "descriptor"
    if kind == "typo":
        typed = _typo(top, rng)
        if typed != top:
            return typed, "typo"
    return top, "top"


def _is_plural(name: str) -> bool:
    last = name.split()[-1]
    return last.endswith("s") and not last.endswith(("ss", "us"))


def _quantity(item: PantryItem, name: str, variant: str, names: _Names, group: str, rng: np.random.Generator
              ) -> tuple[str, dict, bool]:
    """(phrase containing the name, answer-key quantity, whether the phrase is grammatically plural)."""
    store, iid, grams = names.store, item.ingredient_id, float(item.grams)
    canonical = store.ingredient(iid).canonical_name
    whole = store.whole_item_weight(iid)
    cup = store.unit_weight(iid, "cup")
    produce_count = whole is not None and whole.unit in _BARE_COUNT_UNITS and group in _BARE_COUNT_GROUPS
    countable = whole is not None and whole.grams > 0 and (
        produce_count
        or (group in ("poultry", "seafood", "meat") and any(w in canonical for w in _CUT_WORDS))
        or (whole.unit in _OF_COUNT_UNITS and group in ("vegetable", "fruit")))
    liquid = _is_liquid(canonical)
    if group == "egg" and countable:
        forms = dict(FORM_P_EGG)
    elif liquid:
        forms = dict(FORM_P_LIQUID)
    elif produce_count:
        forms = dict(FORM_P_COUNTABLE_PRODUCE)
    else:
        forms = dict(FORM_P)
    if "count" in forms and not (countable and 0.4 <= grams / whole.grams <= 12):
        forms.pop("count")
    if "volume" in forms and not (liquid or (group in _DRY_CUP_GROUPS and cup is not None and cup.grams > 0)):
        forms.pop("volume")
    containers = _containers(canonical, group)
    if "container" in forms and not containers:
        forms.pop("container")
    if not forms:
        forms = {"mass": 0.8, "none": 0.2}
    form = _pick(rng, forms)
    plural_ok = variant in ("top", "descriptor")          # pluralise only names we know the shape of
    name_pl = names.plural(iid, name) if (produce_count and plural_ok) else name

    if form == "mass":
        style = int(rng.integers(0, 4))
        if grams >= 1000 and rng.random() < 0.6:
            kg = round(grams / 1000, 1)
            text = f"{kg:g} kg" if style % 2 == 0 else f"{kg:g}kg"
        else:
            g = int(round(grams))
            text = (f"{g} g", f"{g}g", f"{g} grams", f"{g}g")[style]
        r = rng.random()
        phrase = f"{name_pl} ({text})" if r < 0.12 else (f"{text} of {name_pl}" if r < 0.3 else f"{text} {name_pl}")
        return phrase, {"form": "mass", "value": grams, "unit": "g", "grams": grams}, _is_plural(name_pl)
    if form == "count":
        n = grams / whole.grams
        if n < 0.75:
            value, words = 0.5, "half"
        elif n < 1.5:
            value, words = 1.0, "one" if rng.random() < 0.3 else "a"
        else:
            value = float(round(n))
            words = NUMBER_WORDS.get(int(value), str(int(value))) if rng.random() < 0.35 else str(int(value))
        unit = whole.unit
        spice_like = any(w in canonical for w in ("ground", "dried", "powder", "seed"))
        if unit in _OF_COUNT_UNITS and unit not in name and group in ("vegetable", "fruit") and not spice_like:
            unit_word = pluralise(unit) if value >= 2 else unit
            lead = {"a": _article(unit), "half": f"half {_article(unit)}"}.get(words, words)
            return (f"{lead} {unit_word} of {name}", {"form": "count", "value": value, "unit": unit}, value >= 2)
        shown = names.plural(iid, name) if (value >= 2 and plural_ok) else name
        lead = {"a": _article(shown), "half": f"half {_article(shown)}"}.get(words, words)
        return f"{lead} {shown}", {"form": "count", "value": value, "unit": None}, value >= 2
    if form == "volume":
        if liquid:
            if grams >= 1000 and rng.random() < 0.6:
                litres = round(grams / 1000, 1)
                value_ml = litres * 1000
                text = f"{litres:g} litre{'s' if litres > 1 else ''} of"
            else:
                step = 10 if grams < 100 else 50
                value_ml = float(max(step, int(round(grams / step)) * step))
                text = f"{int(value_ml)} ml" if rng.random() < 0.5 else f"{int(value_ml)}ml"
            return f"{text} {name}", {"form": "volume", "value": value_ml, "unit": "ml", "ml": value_ml}, False
        cups = max(0.5, round(grams / cup.grams * 2) / 2)
        text = "half a cup of" if cups == 0.5 else f"{cups:g} cup{'s' if cups > 1 else ''} of"
        return (f"{text} {name}", {"form": "volume", "value": cups, "unit": "cup", "ml": cups * _ML_PER_CUP},
                _is_plural(name))
    if form == "container":
        word, unit = containers[int(rng.integers(0, len(containers)))]
        n = 2 if grams > 600 and rng.random() < 0.5 else 1
        lead = f"{_article(word)} {word}" if n == 1 else f"two {pluralise(word)}"
        return f"{lead} of {name_pl}", {"form": "container", "value": float(n), "unit": unit}, n > 1
    phrase = f"some {name_pl}" if rng.random() < 0.4 else name_pl
    return phrase, {"form": "none", "value": None, "unit": None}, _is_plural(name_pl)


def _cue(item: PantryItem, today: date, horizon: int, rng: np.random.Generator) -> dict:
    """Urgency cue for an item, from what the kitchen says about its deadline."""
    d = item.last_use_day
    if item.expiry_known and d is not None and d < horizon:
        if d == 0:
            text = TODAY_PHRASES[int(rng.integers(0, len(TODAY_PHRASES)))]
        elif d == 1:
            text = TOMORROW_PHRASES[int(rng.integers(0, len(TOMORROW_PHRASES)))]
        else:
            day = WEEKDAYS[(today + timedelta(days=d)).weekday()]
            day = day.capitalize() if rng.random() < 0.5 else day
            text = WEEKDAY_PHRASES[int(rng.integers(0, len(WEEKDAY_PHRASES)))].format(day=day)
        urgency = "urgent" if d <= 1 else ("soon" if d <= 4 else "none")
        return {"kind": "explicit", "text": text, "urgency": urgency, "days_left": int(d)}
    if not item.expiry_known and d is not None and d <= 1:
        pool, urgency = (URGENT_CUES, "urgent") if d == 0 else (SOON_CUES, "soon")
        return {"kind": "qualitative", "text": pool[int(rng.integers(0, len(pool)))], "urgency": urgency,
                "days_left": None}
    return {"kind": "none", "text": None, "urgency": "none", "days_left": None}


def _attach(phrase: str, cue: dict, plural: bool, rng: np.random.Generator) -> str:
    """Put the cue next to the item the way people write it (a comma-separated cue is a deliberate hard case).

    Agreement follows the phrase ("eggs that are going bad", "milk that's going bad"); ``cue["text"]`` is updated to
    the words actually written.
    """
    if cue["kind"] == "none":
        return phrase
    t = cue["text"]
    if plural:
        t = t.replace("needs ", "need ").replace("expires", "expire").replace("has to", "have to")
    cue["text"] = t
    paren_ok = not phrase.endswith(")")
    if cue["kind"] == "qualitative" and cue["text"] not in _VERB_CUES and not t.startswith("need "):
        styles = {"that's": 0.4, "paren": 0.2, "dash": 0.15, "which": 0.15, "comma": 0.1}
    else:
        styles = {"paren": 0.35, "dash": 0.3, "comma": 0.1}
        if cue["kind"] == "qualitative" or t.startswith(("expire", "has to", "have to")):
            styles["that"] = 0.25
    if not paren_ok:
        styles.pop("paren")
    style = _pick(rng, styles)
    be = "are" if plural else "is"
    return {"that's": f"{phrase} that {be} {t}" if plural else f"{phrase} that's {t}",
            "which": f"{phrase} which {be} {t}", "that": f"{phrase} that {t}", "paren": f"{phrase} ({t})",
            "dash": f"{phrase} - {t}", "comma": f"{phrase}, {t}"}[style]


# ================================================================================================================
# one message, the whole set
# ================================================================================================================
def message_today(scenario: Scenario) -> date:
    """Day 0 of the kitchen's week: the date in the reference week with the scenario's start weekday."""
    return REFERENCE_MONDAY + timedelta(days=scenario.start_weekday)


def render_message(scenario: Scenario, store: KnowledgeStore, seed: int = DEFAULT_SEED,
                   _names: _Names | None = None) -> dict:
    """Write one kitchen as a pantry message. Pure function of ``(scenario, seed)`` and the dataset.

    Returns ``{"scenario_id", "family", "today", "text", "items": [answer key per item]}``.
    """
    names = _names or _Names(store)
    rng = np.random.default_rng([seed, zlib.crc32(scenario.scenario_id.encode())])
    today = message_today(scenario)
    phrases, key = [], []
    order = list(range(len(scenario.pantry)))
    rng.shuffle(order)                                    # people do not list food in generator order
    for k in order:
        item = scenario.pantry[k]
        info = store.ingredient(item.ingredient_id)
        name, variant = _name(item, names, info.food_group, rng)
        phrase, quantity, plural = _quantity(item, name, variant, names, info.food_group, rng)
        cue = _cue(item, today, scenario.horizon_days, rng)
        phrases.append(_attach(phrase, cue, plural, rng))
        key.append({"ingredient_id": int(item.ingredient_id), "canonical_name": info.canonical_name,
                    "surface": name, "name_variant": variant, "quantity": quantity, "urgency": cue["urgency"],
                    "cue_kind": cue["kind"], "cue_text": cue["text"], "days_left": cue["days_left"],
                    "phrase": phrases[-1]})
    style = _pick(rng, {"comma_and": 0.5, "comma": 0.2, "lines": 0.15, "semicolon": 0.1, "plus": 0.05})
    if style == "lines":
        text = "\n".join(phrases)
    elif style == "semicolon":
        text = "; ".join(phrases)
    elif style == "plus":
        text = " + ".join(phrases)
    elif style == "comma_and" and len(phrases) > 1:
        text = ", ".join(phrases[:-1]) + " and " + phrases[-1]
    else:
        text = ", ".join(phrases)
    if style != "lines" and rng.random() < 0.25:
        text = OPENINGS[int(rng.integers(0, len(OPENINGS)))] + text
    elif rng.random() < 0.3:
        text = text[:1].upper() + text[1:]
    if style != "lines" and rng.random() < 0.10:
        text += CLOSINGS[int(rng.integers(0, len(CLOSINGS)))]
    return {"scenario_id": scenario.scenario_id, "family": scenario.family, "today": today.isoformat(),
            "separator": style, "text": text, "items": key}


def build_messages(scenarios: list[Scenario], store: KnowledgeStore, seed: int = DEFAULT_SEED) -> list[dict]:
    names = _Names(store)
    return [render_message(s, store, seed, names) for s in scenarios]


# ================================================================================================================
# freeze / load
# ================================================================================================================
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def messages_path(eval_dir: Path, version: str = MESSAGES_VERSION) -> Path:
    return eval_dir / f"pantry_messages_{version}.jsonl"


def freeze_messages(messages: list[dict], eval_dir: Path, seed: int, version: str = MESSAGES_VERSION) -> Path:
    """Write the messages and ``MESSAGES_FROZEN.json`` (SHA-256). Refuses to overwrite a frozen set."""
    frozen = eval_dir / "MESSAGES_FROZEN.json"
    if frozen.exists():
        raise FileExistsError(f"{frozen} already exists: the message set is frozen. Use a new version.")
    path = messages_path(eval_dir, version)
    path.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in messages) + "\n", encoding="utf-8")
    meta = {"version": version, "created": date.today().isoformat(), "n_messages": len(messages),
            "n_items": sum(len(m["items"]) for m in messages), "seed": seed,
            "source": "scenarios of this directory's FROZEN.json", "files": {path.name: _sha256(path)},
            "labels": "synthetic: generated from the kitchens, not written or labelled by people"}
    frozen.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return frozen


def load_messages(eval_dir: Path) -> list[dict]:
    """Load the frozen messages, verifying the SHA-256 first."""
    meta = json.loads((eval_dir / "MESSAGES_FROZEN.json").read_text(encoding="utf-8"))
    for name, expected in meta["files"].items():
        if _sha256(eval_dir / name) != expected:
            raise RuntimeError(f"{name} does not match MESSAGES_FROZEN.json - the frozen message set was modified")
    path = messages_path(eval_dir, meta["version"])
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    from evaluation.scenarios import load_split
    from knowledge.store import get_default_store
    from logging_setup import configure_logging

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-dir", type=Path, required=True, help="frozen benchmark folder, e.g. data/evaluation/v3")
    ap.add_argument("--split", default="test")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--dry-run", action="store_true", help="print a few messages, write nothing")
    args = ap.parse_args()
    configure_logging()
    store = get_default_store()
    messages = build_messages(load_split(args.split, args.eval_dir), store, args.seed)
    print(f"{len(messages)} messages, {sum(len(m['items']) for m in messages)} items")
    if args.dry_run:
        for m in messages[:: max(1, len(messages) // 8)]:
            print(f"\n[{m['scenario_id']}] today {m['today']}\n{m['text']}")
        return
    print("frozen:", freeze_messages(messages, args.eval_dir, args.seed))


if __name__ == "__main__":
    main()
