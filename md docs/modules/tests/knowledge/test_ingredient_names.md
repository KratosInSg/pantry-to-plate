# `tests/knowledge/test_ingredient_names.py`

Tests [`knowledge/ingredient_names.py`](../../knowledge/ingredient_names.md). Pure logic, no dataset.

| Test | Pins |
| --- | --- |
| `test_core_name` (parametrised) | prep/size words dropped; `ground` kept for meat only; `garlic clove` → `garlic` but the spice `cloves` stays; `flmy`/`olife` repaired; `dried` kept |
| `test_core_name_is_idempotent` | normalising twice changes nothing (required for build ↔ runtime agreement) |

## Change log

- 2026-10-12 — Created.
