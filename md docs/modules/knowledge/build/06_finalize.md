# `build/06_finalize.py`

## Purpose

Make the dataset **safe to ship**: prune to what is usable, verify integrity, compute the data-quality gates from
`docs/data.md`, and write the manifest.

## What it does

1. **Prune** ingredient tables to ingredients that are USDA-mapped or used by a retained recipe; add `n_recipes_pool`
   and rename Food.com-wide counts to `n_*_foodcom`.
2. **Integrity checks (build fails if any breaks):** unique keys; every recipe has ingredients and steps; every recipe
   ingredient exists in `ingredient`, has nutrition; no duplicate (recipe, ingredient/position); aliases, unit
   weights and shelf life reference real ingredients; interactions reference retained recipes; grams ≥ 0.
3. **Quality gates** → `_meta/quality_gates.json`: mapping coverage (from the pre-prune report), nutrition field
   coverage, shelf-life coverage by confidence, computed-vs-stated nutrition consistency, held-out error, pool diet
   composition.
4. **Manifest** → `MANIFEST.json`: every file with rows, columns, bytes, SHA-256.

## Why a separate step

Pruning before verifying would hide problems; verifying before pruning would reject harmless unused rows. Doing both
last means the checks describe exactly what ships.

## Change log

- 2026-10-12 — Created (docs backfilled). Mapping coverage now carried over from step 02 (it was meaningless after
  pruning).
