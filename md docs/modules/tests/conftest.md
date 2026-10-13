# `tests/conftest.py`

## Purpose

Shared pytest fixtures.

## Fixtures

| Fixture | Scope | What |
| --- | --- | --- |
| `store` | session | `get_default_store()` — loads `data/canonical` once per run |
| `resolver` | session | `IngredientResolver(store)` — builds the fuzzy index once |
| `parser` | session | `PantryParser(store, resolver)` |
| `catalog` | session | `get_default_catalog()` — the 54K-recipe `RecipeCatalog` |
| `ctx` | session | `make_context(catalog, store)` — `PlanningContext` for the optimiser / evaluation tests |
| `optimised_week` | session | `(scenario, plan)`: one real optimiser plan (`expiry_heavy`, shortlist 50), solved once per run for the explainer tests |
| `cpsat_available` | session | whether OR-Tools CP-SAT loads here, probed in a child process (it cannot be imported next to pyarrow) |
| `today` | function | `date(2026, 10, 12)`, a Monday, so weekday cues are reproducible |

## Notes

Session scope matters for speed: loading Parquet and building the rapidfuzz candidate lists takes a few hundred
milliseconds; doing it per test would make the suite slow for no benefit (the store is read-only).

## Change log

- 2026-10-12 — Created.
- 2026-10-12 — Added the `catalog` and `ctx` fixtures for the planning path.
- 2026-10-13 — Added the `cpsat_available` fixture.
- 2026-10-13 — Added the `optimised_week` fixture (shared real plan for the explainer tests).
