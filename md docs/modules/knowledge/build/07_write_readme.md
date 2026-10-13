# `build/07_write_readme.py`

## Purpose

Generate `data/canonical/README.md` (the dataset card) **from the real tables** so the schema, row counts, caveats and
quality numbers can never go stale.

## How it works

* Table list and one-line descriptions: `TABLE_DOC` in the script.
* Column meanings: `COL_DOC`; `*_stated` / `*_computed` columns get generated descriptions.
* Types come from the Parquet schemas; row/column counts from `MANIFEST.json`; numbers from
  `_meta/quality_gates.json` and `_meta/grams_estimation_report.json`.

## When to edit

* New table or column → add it to `TABLE_DOC` / `COL_DOC` (blank meaning = it will show empty in the card).
* New caveat → add to the "Read this before using the data" block.

## Change log

- 2026-10-12 — Created (docs backfilled). Added `grams_basis`, `kcal_share`, interaction keys.
