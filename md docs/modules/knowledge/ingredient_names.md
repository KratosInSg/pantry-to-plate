# `src/knowledge/ingredient_names.py`

## Purpose

`core_name(text)` strips the words that never change *which food* an ingredient is (fresh, chopped, large …), repairs
the lemmatiser corruption in Food.com's vocabulary, and keeps words that do matter (dried, canned, cooked, whole
wheat …). It is used by the **build** (to canonicalise 231K recipes) and by the **runtime resolver** (to canonicalise
what a user types), so the two always agree.

## Public API

| Name | What |
| --- | --- |
| `core_name(name) -> str` | Normalised key. Idempotent (`core_name(core_name(x)) == core_name(x)`) |
| `TYPO_FIX` | Food.com artefacts: `flmy→flour`, `olife→olive`, `pastum→pasta`, `asparagu→asparagus`, `fetum→feta` … |
| `IDENTITY_NOISE` | Prep/size/quality words that are removed |
| `MEAT_AFTER_GROUND` | Words after which `ground` is kept (`ground beef` ≠ `ground cumin`) |

## Rules

1. Lower-case; keep letters, digits, `-`, `&`, `'`.
2. Repair known typos token by token.
3. Drop `IDENTITY_NOISE` words.
4. Drop `ground` unless the next word is a meat.
5. `garlic clove(s)` → `garlic`.

## Why it must not drift

The alias table was generated with this function. If a rule changes, aliases built earlier no longer line up with
what the resolver computes at run time. **After any change here, rebuild the dataset** (`run_all.py`) and run the
tests.

## Limits

No plural handling (the resolver does that); no synonym handling (that is `reference/ingredient_synonyms.csv`).

## Tests

[`tests/knowledge/test_ingredient_names.py`](../tests/knowledge/test_ingredient_names.md)

## Change log

- 2026-10-12 — Moved from `build/` to `knowledge/`; added typos `fetum`, `tamarus`, `slouse`, `polentum`, `manicottus`,
  `leave`, `ature`.
