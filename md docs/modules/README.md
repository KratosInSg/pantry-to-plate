# Module documentation

One doc per source file and per test file, mirroring the repo layout. **This index is the map.**

## The rule

```
src/nlp/quantities.py        ->  md docs/modules/nlp/quantities.md
tests/nlp/test_quantities.py ->  md docs/modules/tests/nlp/test_quantities.md
```

* New file → new doc in the same change, and a row in the tables below.
* Changed file → update its doc in the same change (API, behaviour, limits) and add a dated line to its **Change log**.
* A doc explains *what the file is for, how to use it, the decisions behind it, its limits and how it is tested*. It
  does not repeat the code.

Every doc follows the same skeleton: **Purpose · Where it sits · Public API · How it works / decisions · Limits ·
Tests · Change log**.

## Package overviews

| Package | Overview | Status |
| --- | --- | --- |
| `src/knowledge/` | [knowledge/README.md](knowledge/README.md) | runtime store + recipe catalogue + shared normaliser done; build pipeline done |
| `src/knowledge/build/` | [knowledge/build/README.md](knowledge/build/README.md) | done (steps 01-07) |
| `src/nlp/` | [nlp/README.md](nlp/README.md) | rules-based pantry parser done; optional LLM fallback done (validated) |
| `src/domain/` | [domain/README.md](domain/README.md) | done (profile, pantry, scenario, plan; NLP → pantry conversion) |
| `src/preference/` | [preference/README.md](preference/README.md) | content-based scorer done |
| `src/optimizer/` | [optimizer/README.md](optimizer/README.md) | hard rules, shortlist, inventory, baselines, weekly MILP (HiGHS + CP-SAT backends) done |
| `src/evaluation/` | [evaluation/README.md](evaluation/README.md) | benchmark v1 frozen; metrics + runner done; robustness metric pending |
| `src/explain/` | [explain/README.md](explain/README.md) | facts + templates + validated optional LLM paraphrase done |
| `src/app/` | [app/README.md](app/README.md) | service facade for a UI: pantry review, profile, plan, grocery box, re-plan |
| `src/ui/` | [ui/README.md](ui/README.md) | Streamlit prototype: pantry review, profile, week, shopping list, re-plan |
| `src/llm/` | [llm/README.md](llm/README.md) | client done (Ollama native + OpenAI-compatible); decision record `md docs/llm.md` |

## `src/` (top level)

| Source | Doc |
| --- | --- |
| `logging_setup.py` | [logging_setup.md](logging_setup.md) |

## `src/knowledge/`

| Source | Doc |
| --- | --- |
| `knowledge/store.py` | [knowledge/store.md](knowledge/store.md) |
| `knowledge/recipes.py` | [knowledge/recipes.md](knowledge/recipes.md) |
| `knowledge/ingredient_names.py` | [knowledge/ingredient_names.md](knowledge/ingredient_names.md) |

## `src/knowledge/build/` (offline data pipeline)

| Source | Doc |
| --- | --- |
| `build/config.py` | [knowledge/build/config.md](knowledge/build/config.md) |
| `build/matcher.py` | [knowledge/build/matcher.md](knowledge/build/matcher.md) |
| `build/ingredient_flags.py` | [knowledge/build/ingredient_flags.md](knowledge/build/ingredient_flags.md) |
| `build/01_usda_nutrition.py` | [knowledge/build/01_usda_nutrition.md](knowledge/build/01_usda_nutrition.md) |
| `build/02_canonical_ingredients.py` | [knowledge/build/02_canonical_ingredients.md](knowledge/build/02_canonical_ingredients.md) |
| `build/03_recipes.py` | [knowledge/build/03_recipes.md](knowledge/build/03_recipes.md) |
| `build/04_estimate_grams.py` | [knowledge/build/04_estimate_grams.md](knowledge/build/04_estimate_grams.md) |
| `build/05_shelf_life.py` | [knowledge/build/05_shelf_life.md](knowledge/build/05_shelf_life.md) |
| `build/06_finalize.py` | [knowledge/build/06_finalize.md](knowledge/build/06_finalize.md) |
| `build/07_write_readme.py` | [knowledge/build/07_write_readme.md](knowledge/build/07_write_readme.md) |
| `build/run_all.py` | [knowledge/build/run_all.md](knowledge/build/run_all.md) |

## `src/nlp/`

| Source | Doc |
| --- | --- |
| `nlp/schemas.py` | [nlp/schemas.md](nlp/schemas.md) |
| `nlp/defaults.py` | [nlp/defaults.md](nlp/defaults.md) |
| `nlp/segmenter.py` | [nlp/segmenter.md](nlp/segmenter.md) |
| `nlp/urgency.py` | [nlp/urgency.md](nlp/urgency.md) |
| `nlp/quantities.py` | [nlp/quantities.md](nlp/quantities.md) |
| `nlp/resolver.py` | [nlp/resolver.md](nlp/resolver.md) |
| `nlp/pantry_parser.py` | [nlp/pantry_parser.md](nlp/pantry_parser.md) |
| `nlp/llm_fallback.py` | [nlp/llm_fallback.md](nlp/llm_fallback.md) |

## `src/llm/`

| Source | Doc |
| --- | --- |
| `llm/client.py` | [llm/client.md](llm/client.md) |

## `src/explain/`

| Source | Doc |
| --- | --- |
| `explain/facts.py` | [explain/facts.md](explain/facts.md) |
| `explain/render.py` | [explain/render.md](explain/render.md) |
| `explain/paraphrase.py` | [explain/paraphrase.md](explain/paraphrase.md) |
| `explain/explainer.py` | [explain/explainer.md](explain/explainer.md) |

## `src/app/`

| Source | Doc |
| --- | --- |
| `app/models.py` | [app/models.md](app/models.md) |
| `app/grocery.py` | [app/grocery.md](app/grocery.md) |
| `app/service.py` | [app/service.md](app/service.md) |

## `src/ui/`

| Source | Doc |
| --- | --- |
| `ui/streamlit_app.py` | [ui/streamlit_app.md](ui/streamlit_app.md) |
| `ui/views.py` | [ui/views.md](ui/views.md) |
| `ui/logic.py` | [ui/logic.md](ui/logic.md) |
| `ui/theme.py` | [ui/theme.md](ui/theme.md) |

## `src/domain/`

| Source | Doc |
| --- | --- |
| `domain/models.py` | [domain/models.md](domain/models.md) |
| `domain/pantry.py` | [domain/pantry.md](domain/pantry.md) |

## `src/preference/`

| Source | Doc |
| --- | --- |
| `preference/scorer.py` | [preference/scorer.md](preference/scorer.md) |

## `src/optimizer/`

| Source | Doc |
| --- | --- |
| `optimizer/hard_rules.py` | [optimizer/hard_rules.md](optimizer/hard_rules.md) |
| `optimizer/inventory.py` | [optimizer/inventory.md](optimizer/inventory.md) |
| `optimizer/candidates.py` | [optimizer/candidates.md](optimizer/candidates.md) |
| `optimizer/planning.py` | [optimizer/planning.md](optimizer/planning.md) |
| `optimizer/baselines.py` | [optimizer/baselines.md](optimizer/baselines.md) |
| `optimizer/linear_model.py` | [optimizer/linear_model.md](optimizer/linear_model.md) |
| `optimizer/backends.py` | [optimizer/backends.md](optimizer/backends.md) |
| `optimizer/cpsat_worker.py` | [optimizer/cpsat_worker.md](optimizer/cpsat_worker.md) |
| `optimizer/weekly.py` | [optimizer/weekly.md](optimizer/weekly.md) |
| `optimizer/replan.py` | [optimizer/replan.md](optimizer/replan.md) |

## `src/evaluation/`

| Source | Doc |
| --- | --- |
| `evaluation/scenarios.py` | [evaluation/scenarios.md](evaluation/scenarios.md) |
| `evaluation/metrics.py` | [evaluation/metrics.md](evaluation/metrics.md) |
| `evaluation/runner.py` | [evaluation/runner.md](evaluation/runner.md) |
| `evaluation/build_benchmark.py` | [evaluation/build_benchmark.md](evaluation/build_benchmark.md) |
| `evaluation/weight_sweep.py` | [evaluation/weight_sweep.md](evaluation/weight_sweep.md) |

## `tests/`

| Test file | Doc |
| --- | --- |
| `tests/conftest.py` | [tests/conftest.md](tests/conftest.md) |
| `tests/test_docs_coverage.py` | [tests/test_docs_coverage.md](tests/test_docs_coverage.md) |
| `tests/test_logging_setup.py` | [tests/test_logging_setup.md](tests/test_logging_setup.md) |
| `tests/knowledge/test_ingredient_names.py` | [tests/knowledge/test_ingredient_names.md](tests/knowledge/test_ingredient_names.md) |
| `tests/knowledge/test_store.py` | [tests/knowledge/test_store.md](tests/knowledge/test_store.md) |
| `tests/knowledge/test_recipes.py` | [tests/knowledge/test_recipes.md](tests/knowledge/test_recipes.md) |
| `tests/nlp/test_segmenter.py` | [tests/nlp/test_segmenter.md](tests/nlp/test_segmenter.md) |
| `tests/nlp/test_urgency.py` | [tests/nlp/test_urgency.md](tests/nlp/test_urgency.md) |
| `tests/nlp/test_quantities.py` | [tests/nlp/test_quantities.md](tests/nlp/test_quantities.md) |
| `tests/nlp/test_resolver.py` | [tests/nlp/test_resolver.md](tests/nlp/test_resolver.md) |
| `tests/nlp/test_pantry_parser.py` | [tests/nlp/test_pantry_parser.md](tests/nlp/test_pantry_parser.md) |
| `tests/nlp/test_llm_fallback.py` | [tests/nlp/test_llm_fallback.md](tests/nlp/test_llm_fallback.md) |
| `tests/llm/test_client.py` | [tests/llm/test_client.md](tests/llm/test_client.md) |
| `tests/explain/test_facts.py` | [tests/explain/test_facts.md](tests/explain/test_facts.md) |
| `tests/explain/test_render.py` | [tests/explain/test_render.md](tests/explain/test_render.md) |
| `tests/explain/test_paraphrase.py` | [tests/explain/test_paraphrase.md](tests/explain/test_paraphrase.md) |
| `tests/explain/test_explainer.py` | [tests/explain/test_explainer.md](tests/explain/test_explainer.md) |
| `tests/ui/test_logic.py` | [tests/ui/test_logic.md](tests/ui/test_logic.md) |
| `tests/ui/test_app.py` | [tests/ui/test_app.md](tests/ui/test_app.md) |
| `tests/ui/test_theme.py` | [tests/ui/test_theme.md](tests/ui/test_theme.md) |
| `tests/app/test_grocery.py` | [tests/app/test_grocery.md](tests/app/test_grocery.md) |
| `tests/app/test_service.py` | [tests/app/test_service.md](tests/app/test_service.md) |
| `tests/optimizer/test_replan.py` | [tests/optimizer/test_replan.md](tests/optimizer/test_replan.md) |
| `tests/evaluation/test_weight_sweep.py` | [tests/evaluation/test_weight_sweep.md](tests/evaluation/test_weight_sweep.md) |
| `tests/domain/test_models.py` | [tests/domain/test_models.md](tests/domain/test_models.md) |
| `tests/domain/test_pantry.py` | [tests/domain/test_pantry.md](tests/domain/test_pantry.md) |
| `tests/preference/test_scorer.py` | [tests/preference/test_scorer.md](tests/preference/test_scorer.md) |
| `tests/optimizer/test_hard_rules.py` | [tests/optimizer/test_hard_rules.md](tests/optimizer/test_hard_rules.md) |
| `tests/optimizer/test_inventory.py` | [tests/optimizer/test_inventory.md](tests/optimizer/test_inventory.md) |
| `tests/optimizer/test_candidates.py` | [tests/optimizer/test_candidates.md](tests/optimizer/test_candidates.md) |
| `tests/optimizer/test_planning_and_baselines.py` | [tests/optimizer/test_planning_and_baselines.md](tests/optimizer/test_planning_and_baselines.md) |
| `tests/optimizer/test_linear_model_and_backends.py` | [tests/optimizer/test_linear_model_and_backends.md](tests/optimizer/test_linear_model_and_backends.md) |
| `tests/optimizer/test_weekly.py` | [tests/optimizer/test_weekly.md](tests/optimizer/test_weekly.md) |
| `tests/evaluation/test_scenarios.py` | [tests/evaluation/test_scenarios.md](tests/evaluation/test_scenarios.md) |
| `tests/evaluation/test_metrics.py` | [tests/evaluation/test_metrics.md](tests/evaluation/test_metrics.md) |
| `tests/evaluation/test_runner.py` | [tests/evaluation/test_runner.md](tests/evaluation/test_runner.md) |

## Repo-level files

| File | Purpose | Change when |
| --- | --- | --- |
| `CLAUDE.md` | The rulebook: non-negotiables, folder rules, code + documentation conventions | a convention changes |
| `pytest.ini` | Puts `src/` on the import path and sets `tests/` as the test root | the layout changes |
| `requirements.txt` | Python dependencies (data build, runtime, optimiser), plus security minimums for transitive ones | a dependency is added/removed, or an audit flags one |
| `.streamlit/config.toml` | Streamlit theme, and production safety (no tracebacks to visitors) | the look or deployment settings change |
| `.gitignore` | Ignores raw downloads, caches, editor files. `data/canonical/` and `data/evaluation/` are tracked on purpose | a new large/generated folder appears |
| `data/evaluation/` | The frozen benchmark (`scenarios_v1.jsonl`, `split_v1.json`, `FROZEN.json`) | never edited by hand; new version = new files |

## Change log

- 2026-10-12 — Created the module-doc tree with the first `nlp` and `knowledge` packages; backfilled the build pipeline.
- 2026-10-12 — Added `tests/test_docs_coverage.py`, which fails the suite if a file has no doc, a doc is unlisted or has
  no change log, or a doc is orphaned.
- 2026-10-12 — Added `src/llm/` (client) and `nlp/llm_fallback.py`, with tests.
- 2026-10-12 — Added the planning path: `domain`, `preference`, `optimizer`, `evaluation`, `knowledge/recipes`, and their
  tests.
- 2026-10-13 — Added `optimizer/cpsat_worker.py` (CP-SAT backend worker).
- 2026-10-13 — Added `src/explain/` (facts, render, paraphrase, explainer) and its tests.
- 2026-10-13 — Added `src/app/` (service facade, models, grocery box), `optimizer/replan.py`,
  `evaluation/weight_sweep.py` and their tests.
- 2026-10-13 — Added `src/ui/` (Streamlit prototype: streamlit_app, views, logic) and its tests.
- 2026-10-13 — Added `ui/theme.py` (UI redesign) and its tests.
- 2026-10-14 — Added `src/logging_setup.py` (project-wide logging) and its tests; log calls added across the
  runtime packages.
- 2026-10-14 — Security review (`md docs/security.md`): input limits, Markdown escaping, Streamlit config, dependency floors.
