# Tests

`tests/` mirrors `src/`: `tests/nlp/test_x.py` tests `src/nlp/x.py`. Run everything with `python -m pytest` from the
repo root (`pytest.ini` puts `src/` on the import path).

## Kinds of test

| Kind | Needs the dataset? | Where |
| --- | --- | --- |
| **Unit** — pure text/logic | no | `test_quantities` (most), `test_urgency`, `test_segmenter`, `test_ingredient_names` |
| **Integration** — uses the real `data/canonical` build | yes (session-scoped fixtures) | `test_store`, `test_resolver`, `test_pantry_parser`, `test_recipes`, `test_hard_rules`, `test_scorer`, `test_planning_and_baselines`, `test_metrics`, `test_runner` |
| **Solver integration** — real MILPs on real scenarios (a few seconds each) | yes | `test_weekly` |
| **Unit with a fake catalogue** — hand-checkable numbers | no | `test_inventory`, `test_candidates`, `test_linear_model_and_backends` |
| **Doctests** — examples inside docstrings | partly | `python -m pytest --doctest-modules src/nlp` |

Integration tests deliberately run against the real build: a regression in a reference CSV or in the build
pipeline should fail a test, not surface later as a strange plan.

## Conventions

* One behaviour per test, named for the behaviour (`test_compound_names_never_degrade_to_their_head_noun`).
* Expected numbers that come from data are *derived from the dataset* in the test (e.g. half a cabbage =
  0.5 × the store's head weight) so a data refresh does not break tests for the wrong reason.
* Anything date-related uses the `today` fixture (a fixed Monday) — never the real clock.
* A bug found by a test or by hand gets a regression test in the same change.

## Index

See [../README.md](../README.md#tests) for the full table of test docs.

## Change log

- 2026-10-12 — Created with the first 127 tests (knowledge + nlp).
- 2026-10-12 — Added the planning-path tests (domain, recipes, preference, optimizer, evaluation).
