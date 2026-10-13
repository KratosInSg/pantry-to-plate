# `build/run_all.py`

## Purpose

Run the whole data build, in order, from raw downloads to `data/canonical/`.

```bash
python src/knowledge/build/run_all.py
```

Runs steps 01 → 07 as subprocesses from the repo root, prints timing, and stops at the first failure. ≈ 5 minutes
(step 02's lexical matching is the long pole).

## Why subprocesses

Each step is a standalone script with its own imports and failure mode; running them in separate processes means a
crash cannot leave half-initialised module state behind, and any step can be run on its own while developing
(remembering the order caveat in [README.md](README.md)).

## Change log

- 2026-10-12 — Created (docs backfilled).
