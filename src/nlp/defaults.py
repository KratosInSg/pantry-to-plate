"""Named assumptions the NLP layer makes when the user is vague.

Everything here is a *planning assumption*, not data. They live in one file so they are easy to find, argue about and
change, and so that every guess the parser makes can be traced back to a number with a stated rationale.

Rule of thumb for all of them: be modest. Over-estimating what the user has makes the planner schedule meals the
user cannot cook; under-estimating only costs an extra grocery item. When the true amount matters, the UI should ask.
"""
from __future__ import annotations

# --------------------------------------------------------------------------------------------------------------
# "paneer" / "some spinach": no quantity at all -> assume roughly one typical retail pack / handful of leftovers.
# Keyed by ``food_group`` from data/canonical/ingredients/ingredient.parquet.
# --------------------------------------------------------------------------------------------------------------
ASSUMED_GRAMS_BY_GROUP: dict[str, float] = {
    "vegetable": 250.0,      # a small bag of salad leaves / 2-3 mid-size vegetables
    "fruit": 250.0,          # ~2 pieces
    "dairy": 250.0,          # a tub of yoghurt / a small block of cheese / a cup of milk
    "egg": 300.0,            # six eggs (a half-dozen box)
    "meat": 400.0,           # a typical family pack
    "poultry": 400.0,
    "seafood": 300.0,        # two fillets
    "grain_pasta": 500.0,    # a standard dry pack
    "legume": 400.0,         # one can drained, or a small dry pack
    "bakery": 300.0,         # a loaf-ish
    "herb_spice": 30.0,      # a jar / a small bunch
    "oil_fat": 250.0,
    "sauce_condiment": 250.0,
    "sweetener": 500.0,
    "nut_seed": 150.0,
    "beverage": 500.0,
    "soup_broth": 500.0,
    "alcohol": 500.0,
    "snack_sweet": 150.0,
    "mixed_dish": 300.0,
    "water": 1000.0,
    "other": 250.0,
}
FALLBACK_ASSUMED_GRAMS = 250.0

# Weight of ONE whole item when the dataset has no unit weight for it ("3 carrots" but no carrot weight on file).
ASSUMED_ITEM_GRAMS_BY_GROUP: dict[str, float] = {
    "vegetable": 100.0, "fruit": 130.0, "egg": 50.0, "meat": 150.0, "poultry": 170.0, "seafood": 150.0,
    "bakery": 60.0, "dairy": 100.0, "grain_pasta": 100.0, "legume": 100.0, "herb_spice": 10.0,
}
FALLBACK_ASSUMED_ITEM_GRAMS = 100.0

# --------------------------------------------------------------------------------------------------------------
# Container / informal units when the ingredient has no specific weight on file.
# --------------------------------------------------------------------------------------------------------------
ASSUMED_GRAMS_BY_CONTAINER: dict[str, float] = {
    "can": 400.0,        # a standard 14-15 oz can of beans / tomatoes (drained weight is lower; we stay simple)
    "jar": 350.0,        # a typical sauce/pickle jar
    "bottle": 500.0,
    "package": 400.0,    # packs, packets, packages
    "bag": 500.0,
    "box": 400.0,
    "carton": 500.0,
    "tub": 250.0,
    "container": 250.0,
    "bunch": 60.0,       # a bunch of herbs; vegetables with a known "bunch" weight use that instead
    "head": 500.0,       # lettuce/cabbage/cauliflower default when no per-ingredient head weight is on file
    "handful": 30.0,
    "stick": 113.0,      # a US stick of butter
    "loaf": 450.0,
    "slice": 30.0,       # a slice of bread / cheese
    "clove": 3.0,        # a garlic clove
    "stalk": 40.0,       # celery
    "sprig": 2.0,
    "fillet": 150.0,
    "breast": 170.0,
    "thigh": 110.0,
    "leg": 200.0,
    "piece": 100.0,
    "strip": 15.0,
    "leaf": 2.0,
    "ear": 150.0,        # corn on the cob
    "bulb": 50.0,
    "pod": 5.0,
    "cube": 10.0,
    "patty": 110.0,
    "bar": 100.0,
    "roll": 60.0,
    "wedge": 30.0,
}

# When a volume has no weight data, treat the ingredient as water-like. Coarse (flour is ~0.5 g/ml, honey ~1.4)
# but better than refusing; the result is flagged VOLUME_DENSITY_ASSUMED so it is never presented as measured.
ASSUMED_DENSITY_G_PER_ML = 1.0

# --------------------------------------------------------------------------------------------------------------
# Vague amount words. Two families:
#   COUNT words stand for a number of whole items ("a couple of eggs" = 2).
#   AMOUNT words scale the group default ("a little milk" = 0.3 x the default).
# --------------------------------------------------------------------------------------------------------------
VAGUE_COUNT: dict[str, float] = {
    "a couple of": 2, "a couple": 2, "couple of": 2, "a pair of": 2, "a few": 3, "few": 3, "several": 4,
}
VAGUE_AMOUNT_FACTOR: dict[str, float] = {
    "some": 1.0, "a bit of": 0.3, "a little": 0.3, "a little bit of": 0.3, "a splash of": 0.15, "a drizzle of": 0.15,
    "a dash of": 0.1, "a knob of": 0.25, "lots of": 1.5, "plenty of": 1.5, "loads of": 1.5,
    "a lot of": 1.5, "the last of": 0.2, "last bit of": 0.2, "the rest of": 0.5, "leftover": 0.5, "leftovers": 0.5,
    }

# --------------------------------------------------------------------------------------------------------------
# Which size "one X" means when the user gives none. The dataset default is "medium" (USDA's produce reference),
# which is wrong for eggs: recipes and shops mean LARGE (50 g, not 44 g). Add an entry only with a reason.
# --------------------------------------------------------------------------------------------------------------
PREFERRED_ITEM_SIZE: dict[str, str] = {
    "egg": "large",
}
