"""Resolve free-text ingredient names ("baby spinach", "tomatos", "chicken breasts") to canonical ingredients.

Where this sits
---------------
After the segmenter, quantity and urgency modules have peeled away everything that is *not* the food, what remains is
a short name phrase. This module maps it onto an ``ingredient_id`` using the alias table built into the dataset
(``data/canonical/ingredients/ingredient_alias.parquet``) and says *how* it got there.

Strategy - cheapest, most trustworthy first
-------------------------------------------
1. ``exact``       the normalised phrase is a known alias                                   score 1.00
2. ``normalised``  after stripping prep/size words with the build's own normaliser          score 0.97
3. ``singular``    plural -> singular of the head noun ("tomatoes" -> "tomato")              score 0.95
4. ``suffix``      drop leading *modifier* words ("organic free range eggs" -> "eggs")        score 0.90 -
5. ``prefix``      drop trailing *modifier* words ("spinach leaves washed" -> "spinach")     score 0.88 -
6. ``fuzzy``       typo-tolerant match (rapidfuzz) against reliable aliases only             score ratio/100

Only words from ``_DROPPABLE`` may be dropped in steps 4-5. That is deliberate: "peanut butter" must never degrade
to "butter", and "kimchi paste" must never degrade to "paste". If dropping is not safe we fall through to fuzzy
matching and, failing that, report ``UNKNOWN`` with suggestions so the UI can ask the user.

Honest uncertainty
------------------
The result always carries ``method`` and ``score``; fuzzy hits below ``auto_accept_score`` are returned as
``AMBIGUOUS`` (a suggestion), never as a silent match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from rapidfuzz.distance import OSA

from knowledge.ingredient_names import core_name
from knowledge.store import KnowledgeStore
from nlp.schemas import MatchStatus, Suggestion

# Words that describe *how* a food is prepared / how good it is / what colour or size it is, but never *which* food
# it is. Only these may be dropped when looking for a shorter alias. (Colours are included because "purple cabbage"
# should fall back to "cabbage"; "red onion" never reaches this step because the full phrase is an exact alias.)
_DROPPABLE = frozenset({
    # preparation
    "chopped", "diced", "sliced", "minced", "grated", "shredded", "crushed", "cubed", "peeled", "washed", "trimmed",
    "halved", "quartered", "mashed", "melted", "softened", "cooked", "uncooked", "raw", "roasted", "toasted",
    "boiled", "steamed", "fried", "baked", "leftover", "leftovers", "opened", "frozen", "thawed", "defrosted",
    "dried", "canned", "tinned", "bottled", "jarred", "packaged", "pre-cooked", "ready-to-eat", "boneless",
    "skinless", "deseeded", "pitted",
    # quality / provenance
    "fresh", "organic", "free-range", "free", "range", "natural", "homemade", "store-bought", "good", "quality",
    "extra", "virgin", "pure", "plain", "unsweetened", "sweetened", "unsalted", "salted", "low-fat", "lowfat",
    "reduced-fat", "fat-free", "skimmed", "semi-skimmed", "whole", "light", "lite", "lean", "premium", "mature",
    "ripe", "unripe", "baby", "young", "new", "old", "big", "small", "large", "medium", "mini", "jumbo", "thick",
    "thin", "fine", "coarse", "wild", "farmed", "local", "imported", "seasonal",
    # colour
    "red", "green", "yellow", "white", "black", "brown", "orange", "purple", "pink", "golden",
    # trailing noise
    "leaves", "leaf", "pieces", "piece", "chunks", "chunk", "florets", "sprigs", "stalks", "stems", "bits", "cubes",
    "slices", "strips", "wedges", "halves",
})
_STOPWORDS = frozenset({"of", "the", "a", "an", "some", "my", "any", "few", "bit", "bits"})


@dataclass(frozen=True, slots=True)
class Resolution:
    """Outcome of resolving one name phrase."""

    status: MatchStatus
    ingredient_ids: tuple[int, ...]       # empty when UNKNOWN; >1 only for deliberate splits ("salt and pepper")
    method: str                           # exact | normalised | singular | suffix | prefix | fuzzy | none
    score: float                          # 0..1
    matched_alias: str | None             # the alias text that matched
    suggestions: tuple[Suggestion, ...] = ()


def normalise_name(text: str) -> str:
    """Lower-case, strip punctuation (keeping hyphens/apostrophes), collapse spaces, drop leading fillers."""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9\-' %]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -'")
    tokens = [w for w in t.split() if w not in _STOPWORDS]
    return " ".join(tokens)


def _singular_variants(word: str) -> list[str]:
    """Plausible singular forms of an English noun, most likely first. Cheap rules; wrong guesses are harmless
    because every variant is checked against the alias table."""
    out: list[str] = []
    if word.endswith("ies") and len(word) > 4:
        out.append(word[:-3] + "y")                      # berries -> berry
    if word.endswith("ves"):
        out += [word[:-3] + "f", word[:-1]]              # leaves -> leaf, olives -> olive
    if word.endswith("oes"):
        out.append(word[:-2])                            # tomatoes -> tomato
    if word.endswith(("ches", "shes", "xes", "sses")):
        out.append(word[:-2])                            # peaches -> peach
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        out.append(word[:-1])                            # eggs -> egg
    return out


class IngredientResolver:
    """Map a name phrase to canonical ingredient(s). Stateless apart from the shared knowledge store."""

    def __init__(self, store: KnowledgeStore, auto_accept_score: float = 90.0, suggest_score: float = 70.0,
                 min_fuzzy_length: int = 4) -> None:
        """
        Args:
            store: dataset access (alias table, ingredient names).
            auto_accept_score: fuzzy score (0-100) at/above which a typo match is accepted as MATCHED.
            suggest_score: fuzzy score at/above which a candidate is offered as a suggestion.
            min_fuzzy_length: names shorter than this are never fuzzy-matched (too many false friends: "oil", "tea").
        """
        self._store = store
        self._auto = auto_accept_score
        self._suggest = suggest_score
        self._min_fuzzy_len = min_fuzzy_length

    # ------------------------------------------------------------------------------------------- public API
    def resolve(self, name_text: str) -> Resolution:
        """Resolve ``name_text``; never raises. See the module docstring for the strategy."""
        name = normalise_name(name_text)
        if not name:
            return Resolution(MatchStatus.UNKNOWN, (), "none", 0.0, None)

        for text, method, score in self._deterministic_candidates(name):
            ids = self._store.lookup_alias(text)
            if ids:
                return Resolution(MatchStatus.MATCHED, ids, method, score, text)

        return self._fuzzy(name)

    # ------------------------------------------------------------------------------------------- internals
    def _deterministic_candidates(self, name: str):
        """Yield (text_to_look_up, method, score) in the order described in the module docstring."""
        yield name, "exact", 1.0
        if "-" in name:
            yield name.replace("-", " "), "exact", 1.0

        core = core_name(name)
        if core and core != name:
            yield core, "normalised", 0.97

        tokens = name.split()
        head_variants = _singular_variants(tokens[-1]) if tokens else []
        for v in head_variants:
            yield " ".join(tokens[:-1] + [v]), "singular", 0.95
        if len(tokens) > 1:                                # "tomatoes puree" -> "tomato puree"
            all_sing = [(_singular_variants(t) or [t])[0] for t in tokens]
            yield " ".join(all_sing), "singular", 0.94

        # drop leading modifier words, longest remaining phrase first
        for k in range(1, len(tokens)):
            if all(t in _DROPPABLE for t in tokens[:k]):
                rest = tokens[k:]
                yield " ".join(rest), "suffix", max(0.80, 0.90 - 0.03 * (k - 1))
                for v in _singular_variants(rest[-1]):
                    yield " ".join(rest[:-1] + [v]), "suffix", max(0.78, 0.88 - 0.03 * (k - 1))
        # drop trailing modifier words
        for k in range(len(tokens) - 1, 0, -1):
            if all(t in _DROPPABLE for t in tokens[k:]):
                head = tokens[:k]
                yield " ".join(head), "prefix", 0.88
                for v in _singular_variants(head[-1]):
                    yield " ".join(head[:-1] + [v]), "prefix", 0.86

    def _fuzzy(self, name: str) -> Resolution:
        """Typo-tolerant lookup. Auto-accepts only a clear, unambiguous winner."""
        aliases, id_tuples = self._store.fuzzy_candidates
        if len(name) < self._min_fuzzy_len:
            return Resolution(MatchStatus.UNKNOWN, (), "none", 0.0, None)

        # token_sort_ratio tolerates word-order changes ("pepper black"), ratio punishes unrelated substrings
        hits = process.extract(name, aliases, scorer=fuzz.token_sort_ratio, limit=8, score_cutoff=60)
        if not hits:
            return Resolution(MatchStatus.UNKNOWN, (), "none", 0.0, None)

        # collapse aliases that point at the same ingredient, keeping the best score per ingredient
        best: dict[tuple[int, ...], tuple[float, str]] = {}
        for alias, score, idx in hits:
            ids = id_tuples[idx]
            if ids not in best or score > best[ids][0]:
                best[ids] = (score, alias)
        ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
        suggestions = tuple(
            Suggestion(ingredient_id=ids[0], canonical_name=self._name(ids[0]), score=round(s / 100, 3))
            for ids, (s, _) in ranked if s >= self._suggest)[:3]

        top_ids, (top_score, top_alias) = ranked[0]
        clear_winner = len(ranked) == 1 or top_score - ranked[1][1][0] >= 4
        # A short word with one typo ("spinich") scores only ~86 on a ratio scale, so ratio alone would reject
        # obvious typos. Edit distance is the right yardstick: 1 edit for words up to 7 letters, 2 beyond.
        allowed_edits = 1 if len(name) < 8 else 2
        is_typo = OSA.distance(name, top_alias) <= allowed_edits
        if clear_winner and (top_score >= self._auto or is_typo):
            return Resolution(MatchStatus.MATCHED, top_ids, "fuzzy", round(top_score / 100, 3), top_alias, suggestions)
        if top_score >= self._suggest:
            # plausible but not certain: expose the best guess as ids too, so the UI can pre-select it
            return Resolution(MatchStatus.AMBIGUOUS, top_ids, "fuzzy", round(top_score / 100, 3), top_alias, suggestions)
        return Resolution(MatchStatus.UNKNOWN, (), "none", round(top_score / 100, 3), None, suggestions)

    def _name(self, ingredient_id: int) -> str:
        info = self._store.ingredient(ingredient_id)
        return info.canonical_name if info else str(ingredient_id)
