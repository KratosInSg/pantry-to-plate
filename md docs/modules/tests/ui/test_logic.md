# `tests/ui/test_logic.py`

Tests [`ui/logic.py`](../../ui/logic.md). No Streamlit, no dataset.

| Group | Tests | Pins |
| --- | --- | --- |
| re-plan marks | `test_nothing_marked_…`, `test_a_leading_run_…`, `test_a_rejected_dinner_…`, `test_rejecting_todays_dinner_…`, `test_a_cooked_day_after_an_unresolved_one_…`, `test_marking_every_day_done_…`, `test_the_description_…`, `test_bad_input_…`, `test_the_marks_the_ui_offers_…` | the past is the leading Cooked/Skipped run; rejection never counts as elapsed; contradictions and "nothing left" are errors with a message |
| use-by | `test_the_choices_start_with_our_estimate_…`, `test_the_estimate_label_says_when_there_is_no_deadline`, `test_the_current_choice_follows_the_entry`, `test_picking_a_day_states_a_hard_deadline_…` | options, current selection, "not sure" restores the estimate |
| labels | `test_every_status_has_a_label` (×6), `test_only_unresolved_rows_ask_for_a_choice`, `test_weekday_label_with_an_offset`, `test_display_name_restores_the_possessive_food_com_dropped` | wording and name tidying |

## Change log

- 2026-10-13 — Created.
- 2026-10-14 — Added `test_md_escape_neutralises_markdown` and `test_md_escape_keeps_the_visible_text_and_flattens_lines`.
- 2026-10-14 — Added `local_today` tests: browser date wins (Singapore 04:30 vs 20:30 UTC), bad or malformed browser zones fall back to the configured one, and the server fallback is reported.
- 2026-10-16 — "Loved it" mark: counts as cooked and as rating evidence, and is blocked out of order.
