# `tests/nlp/test_pantry_parser.py`

Integration tests for [`nlp/pantry_parser.py`](../../nlp/pantry_parser.md): the whole pipeline on real data.

| Test | Pins |
| --- | --- |
| `test_demo_sentence_from_the_proposal` | the project's demo sentence → cabbage, paneer, egg, spinach; spinach is SOON/3; nothing else urgent |
| `test_half_a_cabbage_and_four_eggs_use_dataset_weights` | grams = 0.5 × head weight, 4 × large-egg weight (derived from the dataset) |
| `test_explicit_mass_is_exact_and_trusted` | 500 g, 1 lb, `1 can (400g)`, `2 x 400g` → exact, confidence 1.0 |
| `test_volume_uses_ingredient_specific_weight` | `2 cups flour` = 2 × flour's USDA cup weight |
| `test_assumptions_are_labelled_never_silent` | no quantity → `assumed_default`, `quantity_is_assumed`, a warning, confidence < 1 |
| `test_unknown_ingredient_is_kept_and_flagged` | unknown item kept (not dropped), warning, appears in `needs_attention` |
| `test_bare_cue_attaches_to_previous_item` | "eggs, they expire tomorrow" → egg URGENT/1, single item |
| `test_cue_scope_both_and_all` | "they're all going bad" / "both going bad" scope |
| `test_mouldy_food_carries_a_safety_warning` | "gone mouldy" → URGENT + unsafe warning |
| `test_salt_and_pepper_becomes_two_items` | deliberate split |
| `test_state_modifiers_set_storage_hint` | frozen → freezer; leftover → refrigerator |
| `test_prepositional_tail_is_not_part_of_the_name` | "tuna in olive oil" → tuna |
| `test_empty_and_junk_input` | empty → no items; "2 cups" → `unparsed` |
| `test_result_is_json_serialisable` | `model_dump`/`model_validate` round-trip |
| `test_llm_fallback_is_called_only_when_needed` | fake LLM is invoked only for unknown/low-confidence results |

## Change log

- 2026-10-12 — Created.
- 2026-10-12 — Added `test_days_left_explicit_is_carried_to_the_item`.
