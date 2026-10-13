"""Ingredient-name normalisation shared by the build scripts and (later) the NLP layer.

core_name() strips words that never change *which food* an ingredient is
(fresh, chopped, large, ...) so "diced tomato", "fresh tomato" and "tomato" land
on the same key. It deliberately keeps words that do change the food
(dried, canned, cooked, smoked, whole wheat, low-fat, unsalted ...).
"""
import re

# Food.com's own lemmatiser corrupted many words (flour->flmy, olive->olife, pasta->pastum, ...).
TYPO_FIX = {
    "flmy": "flour", "cornflmy": "cornflour", "olife": "olive", "pastum": "pasta", "spaghettus": "spaghetti",
    "asparagu": "asparagus", "couscou": "couscous", "lemongras": "lemongrass", "watercres": "watercress",
    "hummu": "hummus", "octopu": "octopus", "cactu": "cactus", "schnapp": "schnapps", "carcas": "carcass",
    "blackberrie": "blackberry", "tomatoe": "tomato", "chily": "chili", "chilie": "chili", "chile": "chili",
    "nestl": "nestle", "litchi": "lychee", "molass": "molasses", "gingerroot": "ginger",
    "fetum": "feta", "tamarus": "tamari", "slouse": "zest", "polentum": "polenta", "manicottus": "manicotti",
    "leave": "leaf", "ature": "",
}

# prep / size / quality words - never identity-changing
IDENTITY_NOISE = {
    "fresh", "freshly", "fine", "finely", "coarse", "coarsely", "chopped", "minced", "diced", "sliced", "thinly",
    "large", "medium", "small", "big", "extra-large", "jumbo", "optional", "organic", "good", "quality", "pure",
    "ripe", "packed", "softened", "melted", "divided", "boneless", "skinless", "skin-on", "bone-in", "cubed",
    "halved", "quartered", "trimmed", "peeled", "seeded", "pitted", "rinsed", "drained", "cut", "torn", "crumbled",
    "freshly-ground", "cracked", "homemade", "store-bought", "storebought", "prepared", "firmly", "lightly",
    "heaping", "scant", "level", "generous", "roughly", "uncooked",
}
# "ground" is noise for spices (ground cumin) but identity for meat (ground beef)
MEAT_AFTER_GROUND = {"beef", "turkey", "pork", "chicken", "lamb", "veal", "sausage", "meat", "bison", "round",
                     "sirloin", "chuck", "venison", "buffalo", "steak", "mutton", "ham"}


def core_name(name: str) -> str:
    toks = re.sub(r"[^a-z0-9\-&' ]", " ", name.lower().replace("&", " and ")).split()
    toks = [TYPO_FIX.get(t, t) for t in toks]
    out = []
    for i, t in enumerate(toks):
        t = t.strip("'")
        if not t or t in IDENTITY_NOISE:
            continue
        if t == "ground" and not (i + 1 < len(toks) and toks[i + 1] in MEAT_AFTER_GROUND):
            continue
        out.append(t)
    s = " ".join(out)
    s = re.sub(r"\bgarlic cloves?\b", "garlic", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
