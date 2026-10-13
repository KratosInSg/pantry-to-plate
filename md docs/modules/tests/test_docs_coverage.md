# `tests/test_docs_coverage.py`

## Purpose

Makes the documentation rule in `CLAUDE.md` enforceable: **one doc per source file and per test file, listed in the
index, each with a change log.** It checks structure, not quality — review still decides whether a doc is good.

## What it checks

| Test | Fails when |
| --- | --- |
| `test_every_source_and_test_file_has_a_doc` | a `src/**/*.py` or `tests/**/*.py` file (other than `__init__.py`) has no `md docs/modules/...md` |
| `test_every_doc_is_listed_in_the_index` | a doc is not mentioned in `md docs/modules/README.md` |
| `test_every_doc_has_a_change_log` | a doc has no `## Change log` section |
| `test_no_orphan_docs` | a doc points at a source/test file that no longer exists |

## Mapping

```
src/<pkg>/<file>.py   ->  md docs/modules/<pkg>/<file>.md
tests/<…>/test_x.py   ->  md docs/modules/tests/<…>/test_x.md
```

Package `README.md` files cover `__init__.py`.

## If it fails

The assertion message lists the exact paths. Create or fix the doc in the same change as the code — that is the rule,
not a formality.

## Change log

- 2026-10-12 — Created.
