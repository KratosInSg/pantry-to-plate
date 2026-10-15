# `tests/ui/test_app.py`

Drives the **real** Streamlit script headlessly with `streamlit.testing.v1.AppTest` (no browser) against the real
dataset and optimiser. The language model is switched off in every test (the sidebar checkbox), so nothing depends on
a local Ollama. The planned week is built once per module (planning takes seconds).

| Test | Pins |
| --- | --- |
| `test_the_first_page_loads_without_errors_and_asks_for_a_pantry` | no exception; title; the three buttons; placeholder |
| `test_the_profile_form_offers_every_diet_allergen_and_cuisine` | form options (labels as the user sees them; raw values underneath) |
| `test_reading_text_shows_honest_rows_and_asks_about_what_it_could_not_recognise` | kimchi gets a "which one?" selector offering "cabbage kimchi" |
| `test_garbage_input_is_met_with_guidance_not_a_crash` | `!!! ???` → "Nothing was recognised", no fake food row |
| `test_an_amount_the_user_corrects_is_no_longer_marked_as_assumed` | editing grams clears the assumption in the page and in state |
| `test_planning_shows_seven_days_with_reasons_ingredients_and_steps` | 7 day cards, "Why this dinner", ingredient and step expanders, metrics |
| `test_the_week_can_be_read_in_four_tabs`, `test_the_shopping_list_…` | tabs; shopping items and the "tick things off" caption |
| `test_no_replan_is_possible_until_a_day_is_marked` | the button is disabled with an explanation |
| `test_marking_days_out_of_order_is_explained_and_blocked` | "Mark days in order" and the button stays disabled |
| `test_cooking_a_day_and_rejecting_another_replans_the_rest` | 6 days left, offset 1, the rejected recipe gone, "Re-planned." shown |
| `test_a_vegan_profile_plans_only_vegan_dinners` | profile → plan: complete, 0 violations, the vegan rule stated |
| `test_an_impossible_profile_is_explained_not_shown_as_an_empty_week` | an over-constrained profile never crashes the page |

## Why this file exists

These tests found a real crash on their first run: "Use an example" raised `StreamlitAPIException` (assigning to a
widget's state after it was created). Unit tests of the logic could not have found it.

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Updated for the redesign (hero instead of `st.title`, emoji tab labels, reasons in expanders, chips).
- 2026-10-14 — The profile-form test expects the vegetarian default.
- 2026-10-14 — Added `test_typed_markdown_and_html_are_shown_as_text_not_rendered` and `test_text_boxes_have_length_limits` (security review).
- 2026-10-14 — Added `test_the_llm_switch_is_hidden_when_no_model_is_reachable`.

- 2026-10-15 — Resolve the Streamlit entry point relative to the repository root via `Path(__file__)`, not the pytest working directory.
