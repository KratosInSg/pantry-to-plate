# `build/01_usda_nutrition.py`

## Purpose

Reduce USDA FoodData Central to what the planner uses: nutrients per 100 g and household-unit weights for the
**13,694 non-branded foods** (SR Legacy 7,793 · FNDDS 5,432 · Foundation 469). Branded foods (2M rows) are out of
scope for the MVP.

## Outputs (`data/canonical/nutrition/`)

| File | Rows | Content |
| --- | --- | --- |
| `usda_food_nutrient_per100g.parquet` | 13,694 | `fdc_id`, `data_type`, `description`, `category`, 15 nutrients, `energy_source`, `qc_flag` |
| `usda_food_portion_weight.parquet` | ~21K | `fdc_id`, `unit`, `size`, `prep`, `grams_per_unit`, `label_raw` |

## Decisions

* **Streams `food_nutrient.csv`** (1.7 GB) in chunks, keeping only core foods × needed nutrients (~200K rows).
* **Energy fallback:** 1008 → Atwater general (2047) → Atwater specific (2048) → computed 4/4/9 (tolerates one missing
  macro). `energy_source` records which. Foundation foods often lack 1008.
* **Portion text lives in three places:** `modifier` (SR Legacy, amount in `amount`), `portion_description` (FNDDS,
  number inside the text) and `measure_unit_id` (Foundation). One parser (`parse_label`) normalises them to
  cup / tbsp / tsp / fl_oz / each(+size) / slice / clove / can … Mass units are dropped (physical constants).
* **`qc_flag`:** `no_energy` (58 foods) and `energy_out_of_range` (> 925 kcal). Flagged rows are excluded from
  ingredient matching but kept in the table.

## Limits

Foundation foods have portions for only ~25% of items, so SR Legacy carries most gram conversions.

## Change log

- 2026-10-12 — Created (docs backfilled). Energy ceiling raised to 925 kcal (pure fats are ~900).
