# `build/ingredient_flags.py`

## Purpose

Rule-based **food group** and **allergen / diet flags** for a canonical ingredient. This is the "knowledge rule"
layer behind the hard-constraint filter: a recipe is vegetarian only if *every* ingredient is.

## Public API

| Name | What |
| --- | --- |
| `classify(name, usda_desc=None, usda_category=None) -> dict` | `food_group`, `contains_*` booleans, `is_vegetarian`, `is_vegan` |
| `food_group(name, usda_desc, usda_category)` | one of 22 coarse groups (dairy, meat, vegetable, herb_spice …) |

## Flags

`contains_dairy · egg · gluten · peanut · tree_nut · soy · sesame · fish · shellfish · meat · poultry · pork ·
alcohol · honey · gelatin`, plus derived `is_vegetarian` (no meat/poultry/fish/shellfish/gelatin **and no egg**) and
`is_vegan` (vegetarian and no dairy/honey).

**Project definition of vegetarian:** no meat, no fish, no eggs; dairy is fine (lacto-vegetarian, as Indian
cooking uses the word). This differs from the Western lacto-ovo convention on purpose.

## Design

* **Conservative on purpose.** A false alarm costs a recipe; a miss costs a user's safety. Worcestershire sauce
  flags fish; marshmallow flags gelatin; generic `broth` flags meat.
* **Looks at name + USDA description**, with parenthetical USDA remarks removed ("(includes oyster, soda, soup)").
* **Exclusion patterns** stop look-alikes: eggplant ≠ egg, goat cheese ≠ meat, coconut ≠ tree nut (FDA 2024),
  ginger ale ≠ alcohol, hot-dog bun ≠ meat, turkey bacon ≠ pork, refined soybean oil ≠ soy allergen,
  `vegetarian`/`vegan`/`meatless` guard against animal words.
* **Maybe-dairy** items (chocolate, cake, caramel, margarine) do not set `contains_dairy`.

## Limits

No hidden-allergen knowledge for branded foods; no cross-contamination; keyword rules miss unusual names.
Spot-audited against Food.com's `vegetarian` tag (351 of ~6,100 tagged recipes derived non-veg: broth, sausage, bacon
— conservative, as intended).

## Gotcha for editors

Regexes containing `\b` must be written with the Edit/Write tools; in some shells a doubled backslash inside a Python
heredoc becomes a literal backspace byte (it happened once here; fixed).

## Change log

- 2026-10-12 — Created (docs backfilled). Added parenthetical stripping, turkey-bacon / hot-dog-bun / steak-sauce /
  goat-cheese / oyster-mushroom guards, vegetarian guard.
- 2026-10-14 — `is_vegetarian` now also excludes egg (project definition: no meat, fish or eggs; dairy fine). Dataset rebuilt.
