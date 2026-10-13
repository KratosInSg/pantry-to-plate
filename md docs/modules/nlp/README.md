# `src/nlp/` — understanding the user's pantry text

## Purpose

Turn what a person types — *"half a cabbage, paneer, four eggs and spinach getting old"* — into structured,
quantified, canonical pantry items that the planner can use. It **understands input; it never plans** (see the
non-negotiables in `CLAUDE.md`).

## Pipeline

```
raw text
  │  segmenter.split_items          one fragment per item   (protects "salt and pepper", "1 and a half cups")
  ▼
fragment ── urgency.find_urgency    "getting old" -> SOON / 3 days     (cue removed from the fragment)
  ▼
fragment ── quantities.extract_quantity   "half a" -> 0.5 whole items   (amount removed from the fragment)
  ▼
name phrase ── resolver.IngredientResolver   "baby spinach" -> ingredient #…   (method + score reported)
  ▼
pantry_parser._estimate_grams       quantity -> grams, labelling every assumption
  ▼
ParseResult(items=[ParsedItem …], unparsed=[…])
```

## Files

| File | Role | Doc |
| --- | --- | --- |
| `schemas.py` | Typed output objects (`ParsedItem`, `ParseResult`, enums) | [schemas.md](schemas.md) |
| `defaults.py` | Named planning assumptions for vague input | [defaults.md](defaults.md) |
| `segmenter.py` | Free text → one fragment per item | [segmenter.md](segmenter.md) |
| `urgency.py` | "going bad" / "expires tomorrow" → urgency level + days | [urgency.md](urgency.md) |
| `quantities.py` | Amount + unit + size extraction | [quantities.md](quantities.md) |
| `resolver.py` | Name phrase → canonical ingredient (exact → normalised → typo-tolerant) | [resolver.md](resolver.md) |
| `pantry_parser.py` | Orchestrator and grams estimation; public entry point | [pantry_parser.md](pantry_parser.md) |
| `llm_fallback.py` | Optional LLM re-read of fragments the rules could not parse (validated; rules do the final parse) | [llm_fallback.md](llm_fallback.md) |

## Quick start

```python
from nlp import PantryParser

result = PantryParser().parse("half a cabbage, paneer, four eggs and spinach getting old")
for item in result.items:
    print(item.canonical_name, item.grams, item.grams_source.value, item.urgency.value, item.warnings)
```

## Cross-cutting rules

1. **Never guess silently.** Every inferred quantity or fuzzy match is labelled in the returned object.
2. **Rules first, LLM optional.** The parser is fully deterministic. An LLM can be attached through the
   `LlmFallback` protocol (`llm_fallback.py`) to re-read low-confidence fragments; it is never required, every answer
   is validated against the user's own words, and the rules do the final parse.
3. **The dataset is the vocabulary.** Ingredient names, spellings and weights come from `data/canonical`; to teach the
   parser a new name, add a row to `data/canonical/reference/ingredient_synonyms.csv` and rebuild — don't hard-code
   it here.

## Known limits (package level)

* English only. Metric and US units; no regional terms ("aubergine" resolves only if present in the alias table).
* Pantry text only — dietary preferences and dislikes are chosen in the UI, not parsed from prose.
* Duplicate mentions ("eggs … 6 eggs") are returned as separate items; merging is the planner's job.

## Change log

- 2026-10-12 — Package created: segmenter, urgency, quantities, resolver, parser, schemas, defaults.
- 2026-10-12 — Added `llm_fallback.py`.
