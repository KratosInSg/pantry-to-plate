# `src/nlp/resolver.py`

## Purpose

Map a name phrase ("baby spinach", "tomatos", "chicken breasts") to canonical ingredient id(s), and report **how**
the match was made and **how sure** we are.

## Public API

| Name | What |
| --- | --- |
| `IngredientResolver(store, auto_accept_score=90, suggest_score=70, min_fuzzy_length=4)` | Stateless apart from the shared store |
| `resolve(name_text) -> Resolution` | Never raises |
| `Resolution` | `status`, `ingredient_ids`, `method`, `score`, `matched_alias`, `suggestions` |
| `normalise_name(text)` | Lower-case, punctuation stripped, filler words dropped |

## Strategy (cheapest and most trustworthy first)

| # | `method` | What | Score |
| --- | --- | --- | --- |
| 1 | `exact` | the normalised phrase is an alias (also with hyphens → spaces) | 1.00 |
| 2 | `normalised` | after the build's `core_name` (prep/size words, typo repair) | 0.97 |
| 3 | `singular` | plural → singular of the head noun (`tomatoes` → `tomato`, `berries` → `berry`) | 0.95 |
| 4 | `suffix` | drop leading *modifier* words (`organic free range eggs` → `eggs`) | 0.90 − 0.03·k |
| 5 | `prefix` | drop trailing *modifier* words (`spinach leaves washed` → `spinach`) | 0.88 |
| 6 | `fuzzy` | typo-tolerant match over reliable aliases (rapidfuzz) | ratio/100 |

### The guard that matters: `_DROPPABLE`

Steps 4–5 may only drop words from a fixed list of **preparation / quality / colour / size** words. That is why
"peanut butter" never degrades to "butter" and an unknown "kimchi paste" never becomes "paste" or "tomato paste": the
dropped word is not a modifier, so we fall through to fuzzy matching and, failing that, report `UNKNOWN`.

### Fuzzy acceptance

* Candidates are only aliases that are reliable (canonical names, synonyms, generated variants, and raw strings seen
  ≥ 5 times) — see `KnowledgeStore.fuzzy_candidates`.
* **MATCHED** when there is a clear winner (≥ 4 points ahead of the next *different* ingredient) **and** either the
  ratio ≥ `auto_accept_score` **or** the edit distance is ≤ 1 (≤ 2 for names of 8+ letters). The edit-distance rule
  exists because a one-letter typo in a short word scores only ~86 on a ratio scale.
* **AMBIGUOUS** when the best score ≥ `suggest_score` but it is not a clear winner; `ingredient_ids` holds the best
  guess so the UI can pre-select it, and `suggestions` lists up to 3 alternatives.
* **UNKNOWN** otherwise; `suggestions` may still list near misses for "did you mean …?".
* Names shorter than `min_fuzzy_length` are never fuzzy-matched ("oil", "tea" have too many false friends).

## How to teach it a new name

Don't edit this file. Add a row to `data/canonical/reference/ingredient_synonyms.csv` and re-run the build
(`python src/knowledge/build/run_all.py`). If the word is a harmless modifier, add it to `_DROPPABLE` here and add a
test.

## Limits

* Only knows ingredients present in Food.com's vocabulary (3.3K canonical ingredients). Anything else is UNKNOWN by
  design.
* Singularisation is rule-based; irregular plurals ("geese") are not handled (harmless: fuzzy picks them up or not).
* Quantity and urgency words must already be removed; passing "2 cups spinach" will not resolve well.

## Tests

[`tests/nlp/test_resolver.py`](../tests/nlp/test_resolver.md)

## Change log

- 2026-10-12 — Created. Added edit-distance rule so one-letter typos are accepted.
