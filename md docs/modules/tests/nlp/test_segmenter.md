# `tests/nlp/test_segmenter.py`

Tests [`nlp/segmenter.py`](../../nlp/segmenter.md). Pure logic.

| Test | Pins |
| --- | --- |
| `test_basic_list_with_lead_in` | the proposal's sentence splits into four fragments, lead-in removed |
| `test_connectors_inside_known_names_are_protected` | "salt and pepper", "half and half" stay whole |
| `test_longest_protected_phrase_wins` | "salt and black pepper" beats "salt and pepper" |
| `test_and_a_half_is_a_quantity_not_two_items` | "1 and a half", "two and a half" → one number |
| `test_numbers_are_not_split` | `1,000 g`, `1.5 kg` |
| `test_brackets_stay_whole` | commas inside brackets |
| `test_bullets_newlines_and_fridge_prefix` | list formatting and "In my fridge:" |
| `test_also_and_plus_are_separators` | `also`, `plus` |
| `test_empty_and_filler_input` | empty / connectors only → `[]` |
| `test_normalise_input_handles_unicode_fractions_and_case` | `½`, `1½`, curly quotes (regression: NFKC order bug) |

## Change log

- 2026-10-12 — Created.
