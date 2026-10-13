# `src/knowledge/store.py`

## Purpose

`KnowledgeStore` is the **only** runtime reader of `data/canonical/`. Every module (NLP, hard-rule filter,
preference scorer, optimiser, explainer) asks it questions instead of opening Parquet files, so file layout and
lookup policies live in one place.

## Public API

| Member | Returns | Notes |
| --- | --- | --- |
| `KnowledgeStore(data_dir=None)` | store | `data_dir` → env `PTP_DATA_DIR` → `data/canonical`; raises `FileNotFoundError` if missing |
| `get_default_store()` | shared store | process-wide cache (`lru_cache`) |
| `ingredient(id)` / `ingredient_by_name(name)` | `IngredientInfo \| None` | id, name, group, `fdc_id`, diet flags, allergens, popularity |
| `lookup_alias(text)` | `tuple[int, ...]` | exact lower-case alias; 2+ ids = deliberate split ("salt and pepper") |
| `fuzzy_candidates` | `(aliases, id_tuples)` | reliable aliases only; parallel tuples for `rapidfuzz.process` |
| `connector_phrases` | `frozenset[str]` | aliases containing "and"/"&" (segmenter protects them) |
| `unit_weights(id)` / `unit_weight(id, unit, size=None)` | `UnitWeight(s)` | grams per cup/tbsp/each/… |
| `whole_item_weight(id)` | `UnitWeight \| None` | weight of "one of it" (each → head → bunch → …) |
| `unit_definitions` | `dict[alias, UnitDefinition]` | physical units: mass → g, volume → ml (from the reference CSV) |
| `nutrition_per_100g(id)` | `dict[str, float] \| None` | USDA nutrients; missing nutrients are absent |
| `default_shelf_life(id)` | `ShelfLife \| None` | the planner's default FoodKeeper row; an estimate |

## Policies it applies

* **Lazy + cached:** each table loads on first use (`cached_property`), so a test that only needs names does not
  load recipes.
* **Size preference** for `unit_weight`: requested size → generic → medium → regular → large → small → …. A weight
  for a nearby size is more useful than none; the weight's `source` says how trustworthy it is.
* **Fuzzy-eligible aliases:** canonical names, synonyms, generated variants, and raw Food.com strings seen ≥ 5 times
  (raw strings are noisy: brand names, marketing phrases).
* **Immutable return types:** frozen dataclasses with `slots`.

## Limits

* Recipes are not exposed yet (needed by the filter/optimiser; add accessors when those modules arrive).
* One dataset version at a time; no hot reload.

## Tests

[`tests/knowledge/test_store.py`](../tests/knowledge/test_store.md)

## Change log

- 2026-10-12 — Created (ingredients, aliases, unit weights, units, nutrition, default shelf life).
