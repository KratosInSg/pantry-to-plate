"""Rule-based food group + allergen/diet flags for a canonical ingredient.

These are *knowledge rules*, not statistics: every flag is a keyword rule over the
canonical name + the matched USDA description. They are intentionally
conservative - a flag errs towards "contains" (a false alarm costs a recipe, a
miss costs a user's safety). Hidden allergens inside branded/packaged products
are out of scope for the MVP (see docs/architecture.md).
"""
from __future__ import annotations

import re


def _rx(words: list[str]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(words) + r")\b")


# phrases that look like an allergen word but are not
_NOT_DAIRY = re.compile(
    r"\b(?:coconut|almond|soy|soya|oat|rice|cashew|hazelnut|flax|hemp|pea|nut|peanut|cocoa|cacao|shea|apple|seed|"
    r"sunflower|sesame|tahini|pumpkin|fruit)\s+(?:milk|milks|butter|cream|creamer|yogurt|yoghurt|cheese)\b"
    r"|\bsoymilk\b|\bnon-?dairy\b|\bbutternut\b|\bcream of tartar\b|\bcream of coconut\b|\bcream soda\b"
    r"|\bcocoa butter\b|\bbutter bean\b|\bbutter lettuce\b|\bbutterfly\b|\bbuttercup\b|\bpeanut butter\b|\bnut butter\b"
    r"|\bcreamed honey\b|\bbean curd\b|\bice\b(?! cream)")
_NOT_EGG = re.compile(r"\beggplant\b|\begg\s+roll\b|\bnoodles?\b(?=.*\bwithout egg\b)")
_NOT_GLUTEN_FLOUR = re.compile(
    r"\b(?:rice|corn|almond|coconut|chickpea|garbanzo|tapioca|potato|oat|buckwheat|sorghum|soy|cassava|arrowroot|"
    r"gluten-free|gluten free|millet|teff|quinoa|amaranth|lentil|banana)\s+(?:flour|pasta|noodles?|bread|crackers?)\b"
    r"|\bcornflour\b|\bcornstarch\b|\bcorn starch\b|\bgluten[- ]free\b|\brice noodles?\b|\bglass noodles?\b"
    r"|\bcellophane noodles?\b|\bcorn tortillas?\b|\bcorn bread\b|\bcornbread\b|\brice paper\b")
_NOT_NUT = re.compile(r"\bnutmeg\b|\bbutternut\b|\bwater ?chestnuts?\b|\bwaterchestnuts?\b|\bnuts?,? coconut\b"
                      r"|\bcoconut\b|\bnut ?free\b|\bpeanuts?\b|\bdoughnuts?\b|\bdonuts?\b|\bnutrition\w*\b"
                      r"|\bchestnut mushrooms?\b")
_NOT_SHELLFISH = re.compile(r"\bcrab ?apples?\b|\boyster mushrooms?\b|\bmushrooms?,? oyster\b|\bsquash,? summer,? scallop\b|\bscallop squash\b")
_NOT_POULTRY = re.compile(r"\bpoultry seasoning\b|\bchicken of the woods\b")

_MEAT = _rx(["beef", "veal", "pork", "lamb", "mutton", "bacon", "ham", "sausages?", "salami", "pepperoni", "prosciutto",
             "pancetta", "chorizo", "kielbasa", "hot dogs?", "hotdogs?", "frankfurters?", "bologna", "steaks?", "brisket",
             "venison", "bison", "buffalo", "rabbit", "meatballs?", "lard", "tallow", "suet", "jerky", "bratwurst",
             "corned beef", "spam", "mortadella", "ground meat", "meat sauce", "minced meat", "stew meat", "liver",
             "oxtail", "goat", "spare ribs",
             "short ribs", "baby back ribs", "prime rib", "pork ribs", "beef ribs", "tenderloin", "sirloin", "chuck",
             "hamburger", "burger", "pastrami", "capicola", "pate"])
_NOT_MEAT = re.compile(r"\bmeatless\b|\bmeat ?free\b|\bvegetarian\b|\bvegan\b|\bimitation\b|\bsubstitute\b|\bveggie\b"
                       r"|\bgoat'?s? (?:cheese|milk)\b|\bhot dog buns?\b|\bsteak sauce\b|\bsauce,? steak\b|\bcoconut meat\b|\bnut meats?\b|\bhamburger buns?\b|\bburger buns?\b"
                       r"|\bpate de fruit\b|\bplantain\b|\bcrab ?meat\b")
_NOT_PORK = re.compile(r"\b(?:turkey|chicken|beef|veggie|vegetarian|vegan|soy|tofu|meatless|imitation|mock) (?:bacon|ham|sausages?|pepperoni|salami|hot dogs?)\b")
_VEG_GUARD = re.compile(r"\b(?:vegetarian|vegan|meatless|meat-free|veggie|plant-based|mock)\b")
_PORK = _rx(["pork", "bacon", "ham", "prosciutto", "pancetta", "lard", "sausages?", "salami", "pepperoni", "chorizo",
             "kielbasa", "hot dogs?", "hotdogs?", "frankfurters?", "bologna", "mortadella", "bratwurst", "capicola",
             "gelatin", "gelatine", "marshmallows?"])
_POULTRY = _rx(["chicken", "turkey", "duck", "goose", "quail", "cornish hen", "poultry", "hen", "pheasant", "squab"])
_FISH = _rx(["fish", "salmon", "tuna", "cod", "tilapia", "trout", "halibut", "mackerel", "sardines?", "anchov(?:y|ies)",
             "herring", "catfish", "haddock", "snapper", "bass", "swordfish", "mahi", "flounder", "sole", "pollock",
             "perch", "eel", "carp", "pike", "caviar", "roe", "worcestershire", "caesar", "surimi", "bonito",
             "dashi", "nam pla", "fish sauce"])
_SHELLFISH = _rx(["shrimps?", "prawns?", "crabs?", "crabmeat", "lobster", "crawfish", "crayfish", "scallops?", "clams?",
                  "oysters?", "mussels?", "squid", "calamari", "octopus", "shellfish", "krill", "abalone", "conch",
                  "snails?", "escargot", "langoustine", "cockles?"])
_DAIRY = _rx(["milk", "cream", "butter", "cheese", "yogurt", "yoghurt", "whey", "casein", "ghee", "buttermilk", "custard",
              "kefir", "paneer", "ricotta", "mozzarella", "cheddar", "parmesan", "feta", "brie", "gouda", "swiss",
              "provolone", "mascarpone", "half and half", "half-and-half", "ice cream", "lactose", "curd",
              "cottage cheese", "creme fraiche", "gelato", "sherbet", "milkshake", "latte", "alfredo", "bechamel",
              "queso", "gruyere", "romano", "asiago", "gorgonzola", "monterey", "velveeta", "cool whip", "whipped topping",
              "margarine", "pudding", "caramel", "chocolate", "cocoa", "cake", "cookie", "brownie"])
# chocolate/caramel/cake etc. are *possible* dairy; handled via _MAYBE_DAIRY so they do not set the hard flag
_MAYBE_DAIRY_ONLY = {"chocolate", "cocoa", "cake", "cookie", "brownie", "caramel", "margarine", "pudding"}
_EGG = _rx(["eggs?", "egg yolks?", "egg whites?", "mayonnaise", "mayo", "meringue", "custard", "eggnog", "hollandaise",
            "aioli", "albumen", "egg noodles?", "quiche", "frittata", "omelet", "omelette", "souffle", "brioche",
            "challah", "pound cake", "angel food"])
_GLUTEN = _rx(["wheat", "flour", "bread", "breadcrumbs?", "pasta", "spaghetti", "macaroni", "noodles?", "couscous", "bulgur",
               "semolina", "farro", "barley", "rye", "malt", "beer", "seitan", "soy sauce", "teriyaki", "hoisin",
               "cracker", "crackers", "tortillas?", "pita", "bagels?", "cakes?", "cookies?", "biscuits?", "bisquick",
               "pie crust", "pie shell", "phyllo", "filo", "pastry", "panko", "croutons?", "pizza", "lasagna", "ravioli",
               "gnocchi", "orzo", "linguine", "fettuccine", "penne", "udon", "ramen", "pretzels?", "muffins?",
               "pancakes?", "waffles?", "cereal", "granola", "graham", "bun", "buns", "rolls?", "baguette", "dumpling",
               "wonton", "wontons", "tempura", "breaded", "batter", "pie", "tart", "scone", "cornbread", "stuffing"])
_PEANUT = _rx(["peanuts?", "peanut butter", "peanut oil", "groundnuts?"])
_TREE_NUT = _rx(["almonds?", "walnuts?", "pecans?", "cashews?", "pistachios?", "hazelnuts?", "filberts?", "macadamias?",
                 "brazil nuts?", "pine nuts?", "pignoli", "chestnuts?", "marzipan", "amaretto", "praline", "nut", "nuts",
                 "frangelico", "gianduja", "nougat", "mixed nuts"])
_SOY = _rx(["soy", "soya", "soybeans?", "tofu", "tempeh", "edamame", "miso", "tamari", "natto", "soymilk", "shoyu",
            "teriyaki", "hoisin"])
_SESAME = _rx(["sesame", "tahini", "hummus", "halva", "halvah", "gomashio"])
_NOT_ALCOHOL = re.compile(r"\bginger (?:ale|beer)\b|\broot beer\b|\bcream soda\b|\bwine vinegar\b|\bsherry vinegar\b"
                          r"|\bnon-?alcoholic\b|\balcohol[- ]free\b|\bvanilla extract\b|\bcooking spray\b")
_ALCOHOL = _rx(["wine", "beer", "rum", "vodka", "whiskey", "whisky", "bourbon", "brandy", "liqueur", "tequila", "sherry",
                "sake", "mirin", "vermouth", "kahlua", "amaretto", "cognac", "champagne", "gin", "schnapps", "triple sec",
                "grand marnier", "alcoholic", "port", "marsala", "madeira", "cointreau", "bailey", "irish cream",
                "prosecco", "stout", "ale", "lager", "cider(?= \\(alcoholic\\))", "everclear", "rye whiskey"])
_HONEY = _rx(["honey"])
_GELATIN = _rx(["gelatin", "gelatine", "marshmallows?", "jell-?o", "aspic"])
_LEGUME = _rx(["beans?", "lentils?", "chickpeas?", "peas?", "legumes?", "dal", "dahl", "soy", "tofu", "tempeh",
               "edamame", "hummus", "falafel", "peanuts?", "garbanzo"])


def _hit(rx: re.Pattern, text: str, exclude: re.Pattern | None = None) -> bool:
    if exclude is not None:
        text = exclude.sub(" ", text)
    return rx.search(text) is not None


# ---- food group ------------------------------------------------------------
_SR_GROUPS = {
    "Spices and Herbs": "herb_spice", "Fats and Oils": "oil_fat", "Poultry Products": "poultry",
    "Sausages and Luncheon Meats": "meat", "Breakfast Cereals": "grain_pasta", "Fruits and Fruit Juices": "fruit",
    "Pork Products": "meat", "Vegetables and Vegetable Products": "vegetable", "Nut and Seed Products": "nut_seed",
    "Beef Products": "meat", "Finfish and Shellfish Products": "seafood", "Legumes and Legume Products": "legume",
    "Lamb, Veal, and Game Products": "meat", "Baked Products": "bakery", "Cereal Grains and Pasta": "grain_pasta",
    "Fast Foods": "mixed_dish", "Meals, Entrees, and Side Dishes": "mixed_dish", "Restaurant Foods": "mixed_dish",
    "Snacks": "snack_sweet", "Alcoholic Beverages": "alcohol",
}
_NAME_GROUPS = [  # (group, regex) - first match wins; used for FNDDS categories and unmatched names
    ("water", re.compile(r"^(?:water|ice)\b|\bwater\b$|\bbottled water\b|\btap water\b")),
    ("alcohol", _ALCOHOL),
    ("egg", re.compile(r"\beggs?\b(?!plant)|\begg (?:white|yolk)")),
    ("oil_fat", re.compile(r"\b(?:oil|shortening|lard|margarine|ghee|cooking spray|tallow)\b|\bbutter\b(?! (?:bean|lettuce|nut))")),
    ("dairy", re.compile(r"\b(?:milk|cream|cheese|yogurt|yoghurt|buttermilk|whey|paneer|kefir|half and half|custard)\b")),
    ("poultry", _POULTRY),
    ("seafood", re.compile(_FISH.pattern + "|" + _SHELLFISH.pattern)),
    ("meat", _MEAT),
    ("herb_spice", re.compile(r"\b(?:spices?|herbs?|seasoning|cinnamon|cumin|paprika|oregano|basil|thyme|rosemary|sage|"
                              r"parsley|cilantro|coriander|dill|mint|turmeric|nutmeg|cloves?|cardamom|pepper(?:corns?)?|"
                              r"salt|garlic powder|curry|chili powder|saffron|allspice|bay leaf|tarragon|marjoram|"
                              r"chives?|vanilla|extract|baking powder|baking soda|yeast|garam masala|mustard seed)\b")),
    ("sweetener", re.compile(r"\b(?:sugar|sugars|syrup|honey|molasses|sweetener|agave|stevia|jaggery)\b")),
    ("sauce_condiment", re.compile(r"\b(?:sauce|ketchup|catsup|mustard|mayonnaise|dressing|vinegar|salsa|relish|pesto|"
                                   r"paste|marinade|chutney|hummus|tahini|gravy|jam|jelly|preserves?|spread)\b")),
    ("soup_broth", re.compile(r"\b(?:soup|broth|stock|bouillon|consomme)\b")),
    ("beverage", re.compile(r"\b(?:juice|coffee|tea|soda|cola|lemonade|smoothie|drink|beverage|punch|cocoa)\b")),
    ("legume", _LEGUME),
    ("nut_seed", re.compile(r"\b(?:nuts?|almonds?|walnuts?|pecans?|cashews?|pistachios?|hazelnuts?|macadamias?|seeds?|"
                            r"peanuts?|flax|chia|sesame|sunflower|pumpkin seeds?)\b")),
    ("bakery", re.compile(r"\b(?:bread|rolls?|bun|buns|bagels?|tortillas?|pita|cake|cookies?|crackers?|biscuits?|"
                          r"muffins?|pastry|pie|crust|breadcrumbs?|croutons?|waffles?|pancakes?)\b")),
    ("grain_pasta", re.compile(r"\b(?:rice|pasta|spaghetti|macaroni|noodles?|oats?|oatmeal|flour|cornmeal|cornstarch|"
                               r"couscous|quinoa|barley|bulgur|cereal|grits|semolina|polenta|farro|millet)\b")),
    ("fruit", re.compile(r"\b(?:apples?|bananas?|oranges?|lemons?|limes?|berr(?:y|ies)|grapes?|melons?|peach(?:es)?|"
                         r"pears?|plums?|cherr(?:y|ies)|mango(?:es|s)?|pineapples?|apricots?|raisins?|dates?|figs?|"
                         r"cranberr(?:y|ies)|coconut|avocados?|kiwi|papaya|pomegranate|fruit|zest|peel)\b")),
    ("vegetable", re.compile(r"\b(?:onions?|garlic|tomato(?:es)?|potato(?:es)?|carrots?|celery|peppers?|lettuce|spinach|"
                             r"cabbage|broccoli|cauliflower|mushrooms?|zucchini|squash|cucumbers?|corn|peas?|beans?|"
                             r"kale|beets?|radish(?:es)?|turnips?|eggplant|asparagus|leeks?|shallots?|scallions?|"
                             r"ginger|vegetables?|greens|sprouts?|artichokes?|okra|pumpkin|yam|cassava|jicama|"
                             r"lemongrass|arugula|chard|fennel|parsnips?|rutabaga)\b")),
]
_FNDDS_HINTS = [
    ("dairy", re.compile(r"\b(?:milk|cheese|yogurt|cream|dairy)\b")),
    ("egg", re.compile(r"\beggs?\b")),
    ("meat", re.compile(r"\b(?:beef|pork|lamb|veal|cured meats?|organ meats?|game|meat mixed|frankfurters|sausages?|bacon)\b")),
    ("poultry", re.compile(r"\b(?:chicken|turkey|poultry)\b")),
    ("seafood", re.compile(r"\b(?:fish|shellfish|seafood)\b")),
    ("legume", re.compile(r"\b(?:beans?|legumes?|tofu|soy)\b")),
    ("nut_seed", re.compile(r"\b(?:nuts?|seeds?)\b")),
    ("fruit", re.compile(r"\b(?:fruits?|juices?|apples?|bananas?|berries|citrus|melons?)\b")),
    ("vegetable", re.compile(r"\b(?:vegetables?|tomatoes|lettuce|carrots|potatoes|greens|onions)\b")),
    ("bakery", re.compile(r"\b(?:bread|rolls?|cakes?|cookies?|pastr(?:y|ies)|crackers?|pancakes?|biscuits?|muffins?)\b")),
    ("grain_pasta", re.compile(r"\b(?:rice|pasta|cereals?|oatmeal|grains?|noodles?)\b")),
    ("oil_fat", re.compile(r"\b(?:oils?|butter|margarine|fats?)\b")),
    ("sweetener", re.compile(r"\b(?:sugars?|syrups?|honey|sweeteners?)\b")),
    ("sauce_condiment", re.compile(r"\b(?:sauces?|condiments?|dressings?|gravy|gravies|salsa)\b")),
    ("soup_broth", re.compile(r"\bsoups?\b")),
    ("alcohol", re.compile(r"\b(?:alcohol|beer|wine|liquor|cocktails?)\b")),
    ("beverage", re.compile(r"\b(?:coffee|tea|soft drinks?|water|beverages?|juices?|energy drinks?|sports drinks?)\b")),
    ("snack_sweet", re.compile(r"\b(?:candy|candies|snacks?|chips|desserts?|ice cream|chocolate|pudding)\b")),
    ("mixed_dish", re.compile(r"\b(?:mixed dishes?|sandwiches?|pizza|burritos?|tacos?|soups?|salads?|pasta dishes)\b")),
]


def food_group(name: str, usda_desc: str | None, usda_category: str | None) -> str:
    n = name.lower()
    # name-level guards: an explicit water/ice name always wins
    if re.fullmatch(r"(?:water|ice|club soda|tonic water|sparkling water)", n):
        return "water"
    if usda_category in _SR_GROUPS:
        return _SR_GROUPS[usda_category]
    d = (usda_desc or "").lower()
    if usda_category == "Dairy and Egg Products":
        return "egg" if re.search(r"\begg\b", d) else "dairy"
    if usda_category == "Soups, Sauces, and Gravies":
        return "soup_broth" if re.search(r"\b(?:soup|broth|stock|bouillon)\b", d) else "sauce_condiment"
    if usda_category == "Beverages":
        return "water" if re.match(r"^(?:beverages, )?water\b", d) else "beverage"
    if usda_category == "Sweets":
        return "sweetener" if re.search(r"\b(?:sugar|sugars|syrup|honey|molasses|sweetener)\b", d) else "snack_sweet"
    if usda_category:  # FNDDS (WWEIA) category text
        c = usda_category.lower()
        for g, rx in _FNDDS_HINTS:
            if rx.search(c):
                return g
    for g, rx in _NAME_GROUPS:
        if rx.search(n):
            return g
    return "other"


def classify(name: str, usda_desc: str | None = None, usda_category: str | None = None) -> dict:
    """-> food_group plus conservative allergen / diet booleans for one ingredient."""
    n = name.lower()
    d = re.sub(r"\([^)]*\)", " ", (usda_desc or "").lower())  # drop "(includes ...)" remarks
    text = f"{n} {d}"
    group = food_group(n, usda_desc, usda_category)

    dairy = _hit(_DAIRY, text, _NOT_DAIRY)
    if dairy:  # chocolate/cocoa/cake/cookie/caramel/pudding/margarine only *may* contain dairy: not a hard flag
        hits = {m.group(0) for m in _DAIRY.finditer(_NOT_DAIRY.sub(" ", text))}
        dairy = bool(hits - _MAYBE_DAIRY_ONLY)
    egg = _hit(_EGG, text, _NOT_EGG) or group == "egg"
    gluten = _hit(_GLUTEN, text, _NOT_GLUTEN_FLOUR) and group != "oil_fat"
    peanut = _hit(_PEANUT, text)
    tree_nut = _hit(_TREE_NUT, text, _NOT_NUT)
    soy = _hit(_SOY, text)
    if soy and group == "oil_fat" and re.search(r"\bsoybean\b|\bvegetable\b", text) and not re.search(r"\bsoy\b", n):
        soy = False  # highly refined soybean oil is not an allergen under FDA labelling rules
    sesame = _hit(_SESAME, text)
    fish = _hit(_FISH, text) and not _VEG_GUARD.search(text)
    shellfish = _hit(_SHELLFISH, text, _NOT_SHELLFISH) and not _VEG_GUARD.search(text)
    poultry = _hit(_POULTRY, text, _NOT_POULTRY) and not _VEG_GUARD.search(text)
    meat = ((_hit(_MEAT, _NOT_PORK.sub(" ", text), _NOT_MEAT) or group == "meat") and not re.search(_NOT_MEAT, text)
            and not _NOT_PORK.search(text))  # turkey bacon / chicken sausage are poultry, not red meat
    pork = _hit(_PORK, text, _NOT_PORK) and not re.search(_NOT_MEAT, text) and not _NOT_PORK.search(text)
    alcohol = _hit(_ALCOHOL, text, _NOT_ALCOHOL) or (group == "alcohol" and not _NOT_ALCOHOL.search(text))
    honey = _hit(_HONEY, text)
    gelatin = _hit(_GELATIN, text) and not _VEG_GUARD.search(text)
    if re.search(r"vinegar", n):
        alcohol = False  # vinegars are not alcoholic beverages
    # broths/bouillon of an animal are animal products even if the name is just "broth"
    if re.search(r"\bbouillon\b|\bbroth\b|\bstock\b", n) and not re.search(r"\bvegetable|\bveggie|\bmushroom\b", n):
        meat = meat or poultry or "beef" in n
    non_veg = meat or poultry or fish or shellfish or gelatin
    return {
        "food_group": group,
        "contains_dairy": bool(dairy), "contains_egg": bool(egg), "contains_gluten": bool(gluten),
        "contains_peanut": bool(peanut), "contains_tree_nut": bool(tree_nut), "contains_soy": bool(soy),
        "contains_sesame": bool(sesame), "contains_fish": bool(fish), "contains_shellfish": bool(shellfish),
        "contains_meat": bool(meat), "contains_poultry": bool(poultry), "contains_pork": bool(pork),
        "contains_alcohol": bool(alcohol), "contains_honey": bool(honey), "contains_gelatin": bool(gelatin),
        "is_vegetarian": not non_veg,
        "is_vegan": (not non_veg) and not (dairy or egg or honey),
    }
