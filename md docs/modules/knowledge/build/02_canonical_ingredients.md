# `build/02_canonical_ingredients.py`

## Purpose

Build the **canonical ingredient layer**: every Food.com ingredient string → one canonical ingredient with USDA
nutrition, household-unit weights, food group, allergen/diet flags and aliases.

## Resolution chain

```
raw string ─► Food.com canonical (ingr_map.pkl) ─► core_name ─► hyphen fold ─► synonym/split ─► USDA food
                                                                              (curated override, else scored match)
```

1. **`ingr_map.pkl`** (11,659 raw → 8,023 ids). Needs a pandas-compat unpickler. Its names carry lemmatiser typos —
   repaired by `knowledge.ingredient_names`.
2. **`core_name`** strips prep/size words.
3. **`HYPHEN_FOLD`** maps "all purpose flour" onto curated "all-purpose flour".
4. **Synonyms** (`reference/ingredient_synonyms.csv`): `name → canonical`; `a + b` splits into two ingredients.
5. **USDA match:** curated override (`reference/ingredient_usda_overrides.csv`, exact or unique-prefix description)
   wins; otherwise `matcher.UsdaIndex` with score ≥ 0.80. Below that the ingredient stays **unmapped** (not guessed).
6. **Confidence:** curated 1.0; auto ≥ 1.2 → 0.85, ≥ 1.0 → 0.75, else 0.55.

## Outputs

`ingredients/ingredient`, `ingredient_alias`, `ingredient_unit_weight`; `nutrition/ingredient_nutrition_per100g`;
`_meta/ingredient_mapping_report.json`, `_meta/review_unmapped_or_low_confidence.csv` (the to-do list for curation).

## Decisions

* **Merge by name, not by FDC id.** Two names mapping to the same USDA food stay separate unless a synonym joins them
  (merging by FDC would collapse "cheese" into "cheddar").
* **Unit weights:** plain portion preferred, else median over prep variants; missing volume units are derived
  (cup = 16 tbsp = 48 tsp); remaining gaps use the food-group median (`source = group_median`).
* **Aliases:** raw strings, Food.com names, synonyms, canonical names, plus generated hyphen-free and plural variants.
* **Non-food** items (skewers, foil, tea bags) are flagged and dropped later.
* **`is_assumed_available`:** water, salt, black pepper.

## Current numbers

96.8% of Food.com ingredient occurrences map to USDA (87% via curated matches).

## Limits

Auto matches for the long tail are lexical and unreviewed; the recipe fit-quality gate (step 04) is the safety net.

## Change log

- 2026-10-12 — Created (docs backfilled). Added hyphen folding, generated alias variants, non-food flag; imports the
  shared `core_name` from `knowledge/`.
