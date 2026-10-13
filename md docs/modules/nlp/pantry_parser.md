# `src/nlp/pantry_parser.py`

## Purpose

The public entry point of the NLP package. Orchestrates segmenter → urgency → quantities → resolver and converts the
amount the user gave into **grams**, recording how each number was obtained.

## Public API

| Name | What |
| --- | --- |
| `PantryParser(store=None, resolver=None, llm_fallback=None)` | Create once, reuse. `store` defaults to the shared `KnowledgeStore` |
| `PantryParser.parse(text, today=None) -> ParseResult` | Parse a block of text. Pass `today` in tests for reproducible weekday cues |
| `LlmFallback` (Protocol) | `refine(text, result) -> ParseResult`: optional re-reader for low-confidence results |
| `PantryParser.LLM_CONFIDENCE_THRESHOLD` | Item confidence below this triggers the fallback (0.5) |

## How one fragment is processed

1. `find_urgency` — pull out the cue. If nothing but a cue is left ("they're going bad"), attach it to the previous
   item(s) according to its scope (`item` / `both` / `all`) and move on.
2. `extract_quantity` — pull out the amount and any size word.
3. `_trim_prepositional_tail` — "tuna **in olive oil**" → "tuna" (the tail is packaging, not the food).
4. `IngredientResolver.resolve` — name → ingredient id(s). Two ids only for deliberate splits (salt **and** pepper →
   two items, same quantity).
5. `_estimate_grams` — see the ladder below.
6. Preferred size: when no size was said, `defaults.PREFERRED_ITEM_SIZE` applies (eggs → "large").
7. Build a `ParsedItem` with confidence `= match score × trust(grams_source)`.

## Grams decision ladder (first rule that applies)

| # | Situation | Result | `grams_source` | Assumed? |
| --- | --- | --- | --- | --- |
| 1 | a stated mass (`500 g`, `1 lb`, `(400g)`, `2 x 400g`) | exact | `explicit_mass` | no |
| 2 | a volume (`2 cups`, `1 tbsp`, `250 ml`) | USDA weight for that unit, else via the cup weight, else 1 g/ml | `volume_unit_weight` / `volume_density_assumed` | only the latter |
| 3 | a container/informal unit (`3 cloves`, `1 can`, `a bunch`) | the ingredient's weight for the unit, else a typical container | `item_unit_weight` / `assumed_default` | only the latter |
| 4 | a count of whole items (`4 eggs`, `half a cabbage`) | weight of one item (size-aware), else typical item for the food group | `item_unit_weight` / `assumed_default` | only the latter |
| 5 | vague (`some`, `a little`) or nothing | typical pack for the food group × a factor | `assumed_default` | yes |

Counted containers with a bracketed weight multiply: `2 cans (400g)` → 800 g.

## Confidence

`confidence = match_confidence × trust(grams_source)` with trust: explicit 1.0 · volume weight 0.95 · item weight 0.9 ·
assumed density 0.7 · assumed default 0.6 · unknown 0.5. It is a *ranking signal for the UI* ("ask the user about the
lowest-confidence items"), not a probability.

## LLM fallback

`LlmFallback` is the seam for a model that re-reads the text when `unparsed` is non-empty or any item is unknown /
ambiguous / low-confidence. Rules for any implementation: it may fix or add items for the same text; it must not
invent quantities that are not in the text; it never decides the plan.

Implemented by [`LlmPantryFallback`](llm_fallback.md) (local `qwen3:8b` via Ollama). Use
`parser_with_llm(LlmClient())` to get a parser that attaches it only when the model is reachable.

## Limits

* Duplicates are not merged. "eggs, 6 eggs" yields two items.
* A fragment that is only a quantity ("2 cups") goes to `unparsed`.
* Group defaults are coarse (see [defaults.md](defaults.md)); the UI should ask for real amounts when it matters.
* Weights for sizes not on file fall back to the nearest size, labelled by `grams_source` only (not per-size).

## Tests

[`tests/nlp/test_pantry_parser.py`](../tests/nlp/test_pantry_parser.md) — includes the proposal's demo sentence as an
acceptance test, assumption labelling, urgency attachment, unknown items and the LLM-fallback trigger.

## Change log

- 2026-10-12 — Created. Added typo acceptance via edit distance (in the resolver) and preferred egg size.
- 2026-10-12 — Carries `days_left_explicit` from the urgency cue onto the item (also for bare cues attached to the previous item).
- 2026-10-12 — LLM fallback section updated: now implemented by `nlp/llm_fallback.py` (no change to this file's code).
