# `tests/explain/test_render.py`

Tests [`explain/render.py`](../../explain/render.md): every sentence is traceable, misses are stated as misses, and the
templates never make claims the facts do not support.

| Test | Pins |
| --- | --- |
| `test_every_statement_names_a_known_term_and_source` | each statement has a valid `term` and `source` |
| `test_section_text_is_exactly_its_statements_before_any_paraphrase` | template text = joined statements; `source="template"`, no note |
| `test_sections_come_in_a_stable_order` | overview, `day:0..6`, then optional rules, caveats |
| `test_solver_cost_term_sentences_only_exist_for_plans_that_have_cost_terms` | optimiser plan has them; a random plan does not |
| `test_the_largest_cost_term_is_the_one_named_first` | ranking in the sentence follows the objective's own decomposition |
| `test_shortfalls_are_stated_as_shortfalls` | "below your dinner range", "short of your", "15 min longer than", and none of the success phrasings |
| `test_a_small_shortfall_never_prints_as_zero` | **regression**: 0.4 g short / 0.3 kcal below are printed with a decimal, never "0" |
| `test_float_noise_is_not_reported_as_a_miss` | a 0.01 g gap reads as "meets" |
| `test_a_dinner_inside_the_band_says_so` | in-range wording; no protein sentence when no minimum is set |
| `test_unused_expiring_stock_is_named_with_its_deadline` | "400 g … will still go unused", "400 g spinach (use by Tuesday, estimated)", caveat present |
| `test_stranded_stock_is_explained_not_left_as_a_mystery` | several owned ingredients past their deadline ⇒ "they expire before the dinner that needs them, so the plan buys them again" |
| `test_grammar_agrees_with_the_count` | "1 of 1 dinners **is** inside…", a single stranded ingredient reads "it expires … buys it again" (found by reading a real explanation) |
| `test_rules_section_states_counts_and_the_safety_verdict` | second-person rule phrases, "All 7 … pass", the allergen-label limit |
| `test_a_violating_plan_is_flagged_loudly` | `WARNING … do not cook from this plan` |
| `test_an_impossible_request_explains_why_there_is_no_plan` | overview names the rule that removed everything |
| `test_templates_never_make_health_or_taste_claims` | no claim words; "best" only in "best possible" (the solver-gap sentence) |
| `test_fmt_g`, `test_lists_never_contain_two_ands` | formatting |

## Change log

- 2026-10-13 — Created. The small-shortfall regression came from running the real LLM against the output.
- 2026-10-13 — Added `test_assumed_quantities_are_flagged_in_the_caveats` and `test_grammar_agrees_with_the_count`; rules wording for `excluded_recipe` and `not_dinner` is covered through `test_service.py`.
