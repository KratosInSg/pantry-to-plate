# `tests/nlp/test_resolver.py`

Tests [`nlp/resolver.py`](../../nlp/resolver.md) against the real alias table.

| Test | Pins |
| --- | --- |
| `test_known_names` | exact aliases, hyphen-less spelling, plurals, synonyms (kosher salt → salt, scallions, paneer) |
| `test_modifier_words_are_dropped_only_when_safe` | "organic free range eggs", "spinach leaves washed" |
| `test_compound_names_never_degrade_to_their_head_noun` | peanut butter ≠ butter; unknown "kimchi paste" is never "paste"/"tomato paste" |
| `test_typos_are_accepted_with_method_fuzzy` | `spinich`, `brocoli`, `cheddr cheese` → MATCHED via fuzzy |
| `test_unknown_food_is_reported_not_guessed` | nonsense → `UNKNOWN`, no ids |
| `test_short_names_are_not_fuzzy_matched` | names under 4 letters are never fuzzed |
| `test_deliberate_split_returns_two_ids` | "salt and pepper" → two ids |
| `test_empty_input` | empty/blank → `UNKNOWN` |

## Change log

- 2026-10-12 — Created.
