# `build/05_shelf_life.py`

## Purpose

Flatten USDA **FoodKeeper** (v128, 661 products) into days and link it to canonical ingredients, with a confidence
label. These are *estimates*, never known use-by dates (a project non-negotiable).

## Outputs (`data/canonical/shelf_life/`)

| File | Content |
| --- | --- |
| `foodkeeper_product` | product catalogue (name, subtitle, category) |
| `foodkeeper_shelf_life` | product × storage (pantry / refrigerator / freezer) × state (unopened / opened / thawed) × basis → min/max days |
| `ingredient_shelf_life` | the above joined to `ingredient_id`, with `confidence` and one `is_default` row per ingredient |

## Decisions

* **Units → days:** days ×1, weeks ×7, months ×30, years ×365.
* **Non-numeric FoodKeeper values** are kept as flags (`is_indefinite`, `is_when_ripe`, `is_package_date_only`,
  `is_not_recommended`) and given a usable `*_effective` number with its provenance in `effective_source`:
  `foodkeeper` · `foodkeeper_tip` (parsed from "Until ripe, then 7 days") · `indefinite_cap` (3650) ·
  `category_median` · `not_recommended`.
* **Linking:** curated product ids (`reference/ingredient_foodkeeper_overrides.csv`, **high**) → lexical match
  (score ≥ 0.95, **medium**) → median of the FoodKeeper category for the ingredient's food group (**low**).
* **Default row:** unopened; prefers a numeric value, then pantry > refrigerator > freezer, date-of-purchase basis
  first. Perishable groups (dairy, egg, meat, poultry, seafood, vegetable, fruit) never fall back to pantry.

## Current coverage

High-confidence links cover ~93% of recipe-ingredient usage, medium ~2%, low ~5%.

## Limits

Cooked/leftover states are not modelled separately; the planner should use `state` rows (`opened`, `thawed`) when it
needs them.

## Change log

- 2026-10-12 — Created (docs backfilled). Added `effective_*` columns and perishable fallback; paneer curated to
  soft cheese.
