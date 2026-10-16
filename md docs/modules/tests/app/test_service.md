# `tests/app/test_service.py`

Tests [`app/service.py`](../../app/service.md) on the real dataset and the real optimiser (shortlist 60 for speed).
These are the flows the prototype needs; each asserts something a user would notice.

| Group | Tests | Pins |
| --- | --- | --- |
| vocabulary | `test_cuisines_…`, `test_ingredient_search_…`, `test_resolve_names_…` | sorted cuisines; "spinac" → spinach first, "chiken" → chicken; matched / ambiguous / unknown separated |
| profile | `test_build_profile_maps_names_to_ids_and_enables_dinner_only`, `…_rejects_unknown_choices_with_the_valid_options` (×3), `…_propagates_numeric_validation` | names → ids; unresolved names left out (never guessed); clear errors |
| pantry review | `test_review_turns_text_into_rows_with_honest_statuses`, `test_unrecognised_items_need_attention_and_come_with_suggestions`, `test_choosing_a_suggestion_…`, `test_editing_the_amount_clears_the_assumption`, `test_a_stated_use_by_becomes_a_known_hard_deadline`, `test_a_row_added_by_hand_…`, `test_pantry_items_keeps_usable_rows_only_and_merges_duplicates`, `test_pantry_items_carry_the_assumption_flag_…`, `test_garbage_text_does_not_raise` | assumed vs stated amounts, urgency, stated deadline; kimchi needs attention and offers "cabbage kimchi"; editing clears assumption |
| planning | `test_a_week_is_planned_complete_safe_and_dinner_only`, `test_every_day_carries_what_a_ui_needs_to_show_it`, `test_pantry_use_by_deadline_is_shown_…`, `test_the_grocery_box_is_the_sum_of_…`, `test_the_explanation_is_attached_and_traceable`, `test_assumed_quantities_are_reported_to_the_user`, `test_a_vegetarian_user_gets_no_meat_even_with_chicken_in_the_pantry` | complete + 0 violations + no non-dinner; steps and ingredient lines; box = sum of per-day buys; unusable chicken is stated |
| re-planning | `test_rejecting_a_dinner_replans_without_it_…`, `test_cooked_and_skipped_days_roll_forward_the_pantry_and_the_calendar`, `test_replanning_twice_accumulates_…`, `test_replanning_never_modifies_the_week_it_started_from`, `test_nothing_left_to_replan_is_a_clear_error` | rejected recipe excluded and carried; 5 days left, Friday first, expired stock reported and gone; offsets and rejections accumulate; input not mutated |
| LLM optional | `test_without_an_llm_everything_works_and_nothing_is_reworded`, `test_reword_uses_the_llm_only_for_overview_and_days` | no model ⇒ identical week; with a stub, overview + days are `llm`, rules/caveats stay `template`, plan untouched |

## Change log

- 2026-10-13 — Created.
- 2026-10-14 — Added `test_each_step_logs_one_info_line_that_names_its_outcome` (review, planning, plan outcome; no user text at INFO).
- 2026-10-14 — Added `test_oversized_pantry_text_is_refused_not_truncated`, `test_too_many_food_names_are_refused`, `test_autocomplete_tolerates_a_huge_query` (security review).
- 2026-10-16 — Added `test_a_substitution_shows_on_the_ingredient_line_and_leaves_the_grocery_box`.
