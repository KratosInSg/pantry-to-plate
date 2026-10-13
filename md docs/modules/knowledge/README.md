# `src/knowledge/` — the knowledge layer

## Purpose

Everything the application *knows*: ingredients, nutrition, unit weights, shelf life, recipes. It has two halves:

| Half | Where | When it runs |
| --- | --- | --- |
| **Runtime access** | `store.py`, `recipes.py`, `ingredient_names.py` | every request; read-only, no planning |
| **Offline build** | `build/` | when the raw data or the curated reference CSVs change |

The build produces `data/canonical/` (documented in `data/canonical/README.md`); the store reads it.

## Files

| File | Role | Doc |
| --- | --- | --- |
| `store.py` | `KnowledgeStore`: typed, cached, read-only dataset access | [store.md](store.md) |
| `recipes.py` | `RecipeCatalog`: the dinner pool as numpy arrays + inverted index for the planning path | [recipes.md](recipes.md) |
| `ingredient_names.py` | `core_name`: the normaliser shared by the build and the NLP resolver | [ingredient_names.md](ingredient_names.md) |
| `build/` | Raw downloads → `data/canonical` (steps 01-07) | [build/README.md](build/README.md) |

## Rules

* The runtime half **never imports from `build/`**; anything both need (like `core_name`) lives at this level.
* The store never mutates data and never raises for "not found" — missing knowledge is normal and callers must decide
  and record what they assume.

## Change log

- 2026-10-12 — `ingredient_names.py` moved up from `build/` so the runtime resolver and the build share one
  implementation. Added `store.py`.
- 2026-10-12 — Added `recipes.py` (`RecipeCatalog`) for the planning path.
