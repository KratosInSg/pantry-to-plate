# `src/nlp/llm_fallback.py`

## Purpose

Implements `pantry_parser.LlmFallback`: let a language model **re-read the fragments the rules could not understand**.
It is an extraction helper, not a planner, and it is built so that it *cannot* make the system believe things the
user did not say.

## How it works

```
rules parse ──▶ items that are unknown / ambiguous / low-confidence  (+ fragments nothing could parse)
                      │  only these raw fragments are sent
                      ▼
           LLM → {name, has_quantity, quantity, unit}      (schema-constrained, per-call unit enum)
                      │
                      ▼  VALIDATE against the fragment that names the food
           name words in the text?  number occurs in the text?  unit word written in the text?
                      │  anything unsupported is dropped
                      ▼
           rebuild a plain sentence ("2 pounds potatoes") ──▶ the SAME rules parser
                      │
                      ▼  only a confident (MATCHED) result replaces the original item; warning added
ParseResult (same order; untouched items identical)
```

## Why it is safe

| Risk | Defence |
| --- | --- |
| Invented food | name words must occur in the user's fragment |
| Invented / misread amount | the number must be derivable from the fragment (digits, fractions, number words, "half a dozen") |
| Wrong unit (observed live: "pounds" → `pint`) | the unit enum is **built per call from the unit words in the text**; the chosen word must be in *that fragment*; a number whose unit cannot be confirmed — or whose written unit the model ignored — is dropped, and the rules apply their labelled default |
| Model decides urgency | it cannot: urgency comes only from the rules' own cue detection (kept from the original item) |
| Model produces ids / grams | it never does: the sentence goes back through the rules (matching, grams ladder, "assumed" labels) |
| Server down / garbage | `LlmError` or malformed answer → rules result returned unchanged |

## Public API

| Name | What |
| --- | --- |
| `LlmPantryFallback(client, rules_parser)` | `refine(text, result) -> ParseResult`. `rules_parser` must be a parser *without* a fallback |
| `parser_with_llm(client, store=None, resolver=None) -> PantryParser` | Parser with the fallback attached **iff** `client.is_available()`; else the plain rules parser |
| `extraction_schema(source)`, `unit_words_in(text)` | The per-call schema and its unit vocabulary |
| `WARNING` | Text added to every item the model helped with, so the UI can ask the user to check it |
| `JsonLlm` (Protocol) | What the fallback needs: `complete_json(messages, schema)` |

## Measured behaviour (live, `qwen3:8b`, 2026-10-12)

| Input fragment | Rules alone | With fallback |
| --- | --- | --- |
| `two-ish pounds potatoes` | unknown, 250 g assumed | potato, **907 g** (2 lb) |
| `bag of the baby spinach i got yesterday` | unknown | spinach, 250 g (default for a bag, labelled) |
| `my last two carrots are getting old` | ambiguous "raw carrot", 250 g, SOON | carrot ×2 = 122 g, SOON kept |
| `~2 lbs of that purple cabbage` | unknown | cabbage, 907 g ("purple" dropped → generic cabbage) |
| `a tub of kimchi`, `some zorblax`, `that green stuff` | unknown | **unchanged** (not in the dataset / not a food name) |

Latency: 3–5 s per call on the RTX 5050 (model warm).

## Limits (read these)

* **Fixes extraction, not vocabulary.** If the dataset has no "kimchi", the re-parse is still unresolved and the item
  stays flagged for the user. Closing a vocabulary gap is curation: add a row to
  `data/canonical/reference/ingredient_synonyms.csv` and rebuild. (A "choose among the resolver's candidates" step is a
  possible later addition; it would be grounded in the candidate list, never free text.)
* **Model can drop a modifier** ("purple cabbage" → "cabbage"); the warning tells the user it was re-read.
* **Not benchmarked on a labelled set yet** — the frozen, human-labelled NLP set (precision/recall/F1) does not exist.
  The numbers above are an illustration, not an evaluation.

## Tests

[`tests/nlp/test_llm_fallback.py`](../tests/nlp/test_llm_fallback.md)

## Change log

- 2026-10-12 — Created. First live run exposed the "pounds → pint" enum failure; fixed by building the unit enum per
  call and validating unit and number against the item's own fragment. Urgency taken away from the model after review.
