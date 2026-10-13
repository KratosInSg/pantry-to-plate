# `tests/explain/test_paraphrase.py`

Tests [`explain/paraphrase.py`](../../explain/paraphrase.md): the validator accepts a faithful rewording and rejects
every kind of change the facts cannot support; the paraphraser degrades to the template on any failure; safety sections
never reach the model. The model is a stub (`complete_text` returns what the test says); the real model's acceptance
rate is a measurement recorded in the module doc, not a test.

| Test | Pins |
| --- | --- |
| `test_a_faithful_rewording_is_accepted`, `test_the_facts_themselves_always_pass` | no false rejections of honest rewording |
| `test_number_words_count_as_numbers`, `test_seven_written_out_matches_7` | "seven" = 7; "one" / "no" may satisfy a number but never count as invented |
| `test_an_invented_number_is_rejected`, `test_a_dropped_number_is_rejected` | both directions |
| `test_an_invented_food_is_rejected`, `test_a_dropped_food_is_rejected`, `test_plural_and_singular_are_the_same_food` | food check and stemming |
| `test_an_invented_weekday_is_rejected_and_the_headings_weekday_is_allowed`, `test_a_dropped_deadline_day_is_rejected`, `test_relative_days_are_never_allowed` | days |
| `test_a_dropped_warning_is_rejected`, `test_a_synonym_keeps_the_warning` | "below" → "off" rejected; "below" → "under" accepted |
| `test_unsupported_claims_are_rejected` (×3) | healthy / delicious / perfect |
| `test_markup_and_line_breaks_are_rejected`, `test_padding_is_rejected`, `test_empty_answer_is_rejected` | form |
| `test_vocabulary_has_real_foods_and_excludes_ordinary_english` | `GENERIC_WORDS` excluded (e.g. *meal*) |
| `test_a_valid_rewrite_is_used`, `test_an_invalid_rewrite_is_not_used_and_says_why` | accept / reject with reasons |
| `test_the_prompt_contains_only_the_sections_own_facts` | what the model is shown |
| `test_after_a_transport_failure_the_model_is_not_called_again` | circuit breaker: one failure, one call |
| `test_safety_sections_are_never_sent_to_the_model` | `rules` / `caveats` untouched; call count = overview + days |
| `test_rejected_sections_keep_their_template_and_carry_a_note` | fallback + `note` |
| `test_build_paraphraser_is_none_when_the_model_is_unreachable` | `None` client / not available ⇒ `None` |

## Change log

- 2026-10-13 — Created.
