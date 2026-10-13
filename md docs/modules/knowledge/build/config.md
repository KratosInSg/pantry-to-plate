# `build/config.py`

## Purpose

Single place for paths and constants shared by all build steps.

## Contents

| Name | What |
| --- | --- |
| `ROOT`, `RAW_FDC`, `RAW_RECIPES`, `RAW_FOODKEEPER` | raw input locations (read-only) |
| `OUT`, `OUT_INGREDIENTS`, `OUT_NUTRITION`, `OUT_RECIPES`, `OUT_INTERACTIONS`, `OUT_SHELF_LIFE`, `OUT_REFERENCE`, `OUT_META` | output folders under `data/canonical/` |
| `NUTRIENT_COLUMNS` | USDA nutrient id → output column (15 nutrients; two ids map to `sugars_g`) |
| `ENERGY_IDS_PRIORITY` | energy fallback order: 1008 → 2047 (Atwater general) → 2048 (Atwater specific) |
| `ATWATER` | 4/4/9 kcal per g, last-resort energy |
| `CORE_DATA_TYPES` | the non-branded USDA data types we keep |
| `write_parquet(df, path)` | zstd Parquet writer that prints rows/cols |

## Notes

To add a nutrient: add its USDA id to `NUTRIENT_COLUMNS` and its output name to `NUTRIENT_OUTPUT_ORDER`, then rebuild.

## Change log

- 2026-10-12 — Created (docs backfilled).
