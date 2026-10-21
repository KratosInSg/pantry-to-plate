# `tests/evaluation/test_pantry_messages.py`

Tests [`src/evaluation/pantry_messages.py`](../../evaluation/pantry_messages.md).

## What it checks

| Test | Guarantees |
| --- | --- |
| `test_rendering_is_a_pure_function_of_kitchen_and_seed` | same seed, same message; another seed, another message |
| `test_answer_key_covers_every_pantry_item_once` | one key entry per pantry ingredient; each written phrase is in the text |
| `test_stated_dates_and_cues_follow_the_kitchen` | stated dates only for known deadlines, with the right day and urgency band; qualitative cues only for estimates due within a day |
| `test_quantity_key_is_self_consistent` | mass/volume/none/count/container keys carry the fields the scorer reads |
| `test_today_has_the_kitchen_start_weekday` | weekday cues resolve to the intended day |
| `test_spelling_helpers` | plurals; a typo changes one letter (never the first) and skips short words |
| `test_names_come_from_the_vocabulary_or_the_regional_list` | `top`/`variant` names are aliases of the right ingredient; `regional` names come from the list |
| `test_freeze_and_load_verify_the_hash` | freeze refuses to overwrite; a tampered file is rejected |
| `test_committed_message_set_matches_the_v3_kitchens` | the committed m1 set: 120 messages, one per v3 kitchen, item counts agree, labelled "synthetic" |

## Change log

- 2026-10-21 — Created.
