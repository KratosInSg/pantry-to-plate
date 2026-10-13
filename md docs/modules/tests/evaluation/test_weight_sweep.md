# `tests/evaluation/test_weight_sweep.py`

Tests [`evaluation/weight_sweep.py`](../../evaluation/weight_sweep.md): the pre-declared choice rule and the guard
against tuning on the test split. No solving: the rule is a pure function of a summary table.

| Test | Pins |
| --- | --- |
| `test_grid_is_small_and_contains_the_default` | 6 candidates, all ≥ the default multipliers |
| `test_multipliers_scale_the_starting_weights_and_nothing_else` | only the preference and nutrition weights move, relative to `SWEEP_BASE` |
| `test_the_adopted_default_is_the_candidate_the_recorded_sweep_chose` | `DEFAULT_WEIGHTS` = start with preference ×3 and nothing else changed — fails if the default is edited without a sweep |
| `test_multipliers_do_not_compound_when_the_default_has_moved` | "×3" stays ×3 of the starting point, not ×9 |
| `test_liked_cuisine_rate` | the visible-effect metric and its "not measurable" cases |
| `test_the_candidate_with_the_largest_visible_effect_that_passes_is_chosen` | the rule |
| `test_a_candidate_that_breaks_a_guardrail_is_rejected_however_good_it_looks` | guardrails dominate |
| `test_each_guardrail_trips_just_beyond_its_limit` (×6), `test_each_guardrail_holds_exactly_at_its_limit` | boundaries of every guardrail |
| `test_the_default_is_kept_when_nothing_beats_it` | no improvement ⇒ no change |
| `test_equal_effect_goes_to_the_smaller_change` | tie-break |
| `test_summarise_averages_per_candidate_…` | per-candidate means, undefined rates ignored |
| `test_the_test_split_is_refused` | tuning on test is a `ValueError` |
| `test_guardrail_table_documents_every_rule_the_code_checks` | table and code cannot drift |
| `test_parse_candidates_always_leads_with_the_default_and_deduplicates` | CLI candidate parsing; the default is always the baseline |
| `test_a_candidate_meeting_every_criterion_is_adoptable` | exactly at every threshold ⇒ adoptable |
| `test_each_adoption_criterion_is_enforced` (×7) | each confirmation criterion trips on its own, with its own message |

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Added the confirmation-mode tests.
