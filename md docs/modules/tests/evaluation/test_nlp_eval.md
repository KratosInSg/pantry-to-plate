# `tests/evaluation/test_nlp_eval.py`

Tests [`src/evaluation/nlp_eval.py`](../../evaluation/nlp_eval.md).

## What it checks

| Test | Guarantees |
| --- | --- |
| `test_alignment_classifies_every_kind_of_miss_and_counts_false_alarms` | found / wrong ingredient / asked user / not recognised / no item / spurious; a confident wrong answer counts as a miss *and* a false positive; P/R/F1 arithmetic |
| `test_quantity_scoring_per_form` | mass needs an explicit weight within 1 %; volume converts units; bare counts accept the item's own unit; containers need the unit; "no amount" is right when the parser assumed one |
| `test_urgency_and_stated_dates_are_scored_on_found_items` | urgency band and stated day both checked |
| `test_parsing_the_committed_messages_end_to_end` | real parser on 12 committed messages: valid outcomes, CIs bracket the estimate |

## Change log

- 2026-10-21 — Created.
