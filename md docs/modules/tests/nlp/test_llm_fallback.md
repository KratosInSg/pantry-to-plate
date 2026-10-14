# `tests/nlp/test_llm_fallback.py`

Tests [`nlp/llm_fallback.py`](../../nlp/llm_fallback.md). A scripted `StubLlm` stands in for the model; the rules
parser, resolver and store are the real ones, so re-parsing, grams and labels are real.

| Test | Pins |
| --- | --- |
| `test_unit_enum_offers_only_the_unit_words_in_the_text` | the per-call enum (regression for "pounds → pint") |
| `test_no_problem_items_means_no_llm_call` | good parses never reach the model |
| `test_fragment_the_rules_could_not_read_is_fixed` | "two-ish pounds potatoes" → potato, 907 g, raw text kept, warning added |
| `test_the_model_is_only_shown_the_problem_fragments` | good fragments are not sent |
| `test_good_items_are_untouched_and_order_is_kept` | |
| `test_a_food_the_user_never_mentioned_is_rejected` | hallucinated name |
| `test_a_number_that_is_not_in_the_text_is_dropped_not_trusted` | hallucinated amount → labelled default |
| `test_a_unit_that_is_not_in_the_text_drops_the_number_too` | the live "pint" failure |
| `test_ignoring_a_unit_word_that_is_in_the_text_drops_the_number` | "2 potatoes" instead of 2 lb is refused |
| `test_a_unit_from_another_fragment_is_not_accepted` | per-fragment validation |
| `test_numbers_the_user_could_have_meant_are_recognised` (8 cases) | digits, fractions, "1½", number words, "half a dozen" |
| `test_numbers_the_user_did_not_write_are_not_recognised` | |
| `test_llm_failure_keeps_the_rules_result`, `test_garbage_answer_keeps_the_rules_result` | graceful degradation |
| `test_the_users_own_urgency_cue_is_kept`, `test_the_model_cannot_create_urgency` | urgency is the rules' |
| `test_parser_with_llm_*` (2) | attaches the fallback iff the server is reachable |

## Change log

- 2026-10-12 — Created.
- 2026-10-14 — Added `test_llm_failure_is_logged_as_a_warning`; the server-down test also checks its WARNING line.
