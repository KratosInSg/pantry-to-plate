"""Lexical matcher: ingredient name -> best USDA FoodData Central food.

USDA descriptions follow "Primary, qualifier, qualifier, state" (e.g. "Oil, olive,
salad or cooking", "Onions, raw"). We score a query against every non-branded
description with IDF-weighted token coverage, then adjust for the things that
make a USDA entry a poor generic stand-in (cooked/canned/baby-food/restaurant
variants the query never asked for, long descriptions, FNDDS composites).

The scorer is deliberately transparent: every candidate comes back with its score so
low-confidence matches can be reviewed or dropped, never silently trusted.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

STOP = {"a", "an", "the", "of", "and", "or", "in", "with", "for", "to", "from", "by", "at", "on", "style", "type",
        "nfs", "ns", "as", "form", "all", "other", "kind", "any", "brand"}
# Words that describe prep/size/quality only; they never change which USDA food we want.
QUERY_NOISE = {"fresh", "freshly", "fine", "finely", "coarse", "coarsely", "chopped", "minced", "diced", "sliced",
               "shredded", "grated", "crushed", "large", "medium", "small", "big", "extra", "organic", "good", "quality",
               "optional", "divided", "packed", "softened", "melted", "thinly", "thick", "thin", "whole", "plain",
               "pure", "natural", "homemade", "store", "bought", "boneless", "skinless", "lean", "ripe", "firm"}
# Words that signal a USDA entry is a specific *variant*. They are penalised unless the query contains them.
VARIANT_WORDS = {"babyfood", "baby", "infant", "formula", "toddler", "restaurant", "fast", "school", "commodity",
                 "imitation", "substitute", "dehydrated", "canned", "frozen", "cooked", "boiled", "fried", "roasted",
                 "baked", "stewed", "sauteed", "breaded", "toasted", "sweetened", "flavored", "microwaved", "broiled",
                 "braised", "smoked", "pickled", "prepared", "instant", "mix", "restaurant", "nfs", "diet", "reduced",
                 "low", "nonfat", "fat", "free", "light", "lowfat", "dry", "dried", "sprouted", "juice", "puree",
                 "flour", "powder", "drink", "beverage", "sandwich", "salad", "soup", "sauce", "pie", "cake", "cookie",
                 "candy", "cereal", "snack", "bar", "dessert", "pudding", "stuffed", "creamed", "scalloped", "casserole",
                 "gravy", "dressing", "spread", "topping", "filling", "glaze", "wrap", "burrito", "taco", "pizza",
                 "enriched", "fortified", "unenriched", "heated", "steamed", "grilled", "battered", "ready-to-eat",
                 "ready-to-drink", "ready-to-serve", "concentrate", "condensed", "evaporated", "reconstituted"}
UNIT_NOISE = re.compile(r"\b(\d+\s*%|\d+/\d+|\d+(\.\d+)?)\b")


def singular(w: str) -> str:
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "xes", "sses", "zes")):
        return w[:-2]
    if w.endswith("oes"):
        return w[:-2]
    if w.endswith(("ss", "us", "is", "ous")):
        return w
    if w.endswith("s"):
        return w[:-1]
    return w


def tokens(text: str, drop_noise: bool = False) -> list[str]:
    t = text.lower().replace("&", " and ")
    t = UNIT_NOISE.sub(" ", t)
    t = re.sub(r"[^a-z\- ]", " ", t)
    out = []
    for w in t.split():
        w = w.strip("-")
        if not w or w in STOP:
            continue
        w = singular(w)
        if drop_noise and w in QUERY_NOISE:
            continue
        out.append(w)
    return out


class UsdaIndex:
    def __init__(self, foods):
        """foods: DataFrame with fdc_id, description, data_type, category."""
        self.foods = foods.reset_index(drop=True)
        self.desc_tokens = [tokens(d) for d in self.foods.description]
        segs = [[tokens(x) for x in d.split(",")] for d in self.foods.description]
        self.desc_head = [set(sg[0]) if sg else set() for sg in segs]
        self.desc_head2 = [set(sg[0]) | set(sg[1]) if len(sg) > 1 else set(sg[0]) if sg else set() for sg in segs]
        self.sets = [set(t) for t in self.desc_tokens]
        df = defaultdict(int)
        self.inv = defaultdict(list)
        for i, s in enumerate(self.sets):
            for w in s:
                df[w] += 1
                self.inv[w].append(i)
        n = len(self.sets)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1.0 for w, c in df.items()}
        self.default_idf = math.log(n + 1) + 1.0
        self.source_bonus = {"foundation": 0.0, "sr_legacy": 0.03, "survey_fndds": -0.20}
        # SR Legacy contains many branded/ready-meal rows; generic ingredients are what we want.
        self.cat_penalty = {"Baby Foods": 0.25, "Fast Foods": 0.25, "Restaurant Foods": 0.25, "Snacks": 0.1,
                            "Meals, Entrees, and Side Dishes": 0.15, "American Indian/Alaska Native Foods": 0.1,
                            "Breakfast Cereals": 0.1}

    def _score(self, q: list[str], qset: set[str], i: int) -> float:
        d = self.sets[i]
        idf = self.idf
        tot = sum(idf.get(w, self.default_idf) for w in qset)
        hit = sum(idf.get(w, self.default_idf) for w in qset if w in d)
        cover = hit / tot if tot else 0.0
        if cover == 0:
            return -1.0
        extra = [w for w in d if w not in qset]
        variant_pen = 0.12 * sum(1 for w in extra if w in VARIANT_WORDS)
        extra_pen = 0.03 * min(len(extra), 10)
        raw_bonus = 0.08 if ("raw" in d and "raw" not in qset) else 0.0
        head = self.desc_head[i]
        head_bonus = 0.10 if (head & qset) else 0.0
        # query IS the USDA head segment ("Butter, salted") or head + first qualifier ("Oil, olive")
        if head == qset:
            head_bonus += 0.30
        elif self.desc_head2[i] == qset:
            head_bonus += 0.25
        # query's last token is usually the noun ("olive OIL", "parmesan CHEESE")
        noun_bonus = 0.05 if q and q[-1] in d else 0.0
        row = self.foods.iloc[i]
        score = (cover + head_bonus + noun_bonus + raw_bonus - variant_pen - extra_pen
                 + self.source_bonus.get(row.data_type, 0.0)
                 - self.cat_penalty.get(row.category, 0.0))
        return score

    def match(self, name: str, topk: int = 5, data_types: tuple[str, ...] | None = None):
        q = tokens(name, drop_noise=True) or tokens(name)
        qset = set(q)
        if not qset:
            return []
        cand: set[int] = set()
        # candidates must contain the rarest-informative query tokens
        ranked = sorted(qset, key=lambda w: -self.idf.get(w, self.default_idf))
        for w in ranked[:3]:
            cand.update(self.inv.get(w, ()))
        if not cand:
            return []
        scored = []
        for i in cand:
            if data_types and self.foods.data_type.iat[i] not in data_types:
                continue
            s = self._score(q, qset, i)
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], len(self.foods.description.iat[x[1]])))
        out = []
        for s, i in scored[:topk]:
            r = self.foods.iloc[i]
            out.append({"fdc_id": int(r.fdc_id), "description": r.description, "data_type": r.data_type,
                        "score": round(float(s), 3)})
        return out
