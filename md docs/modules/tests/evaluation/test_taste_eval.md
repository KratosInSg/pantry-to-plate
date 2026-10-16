# `tests/evaluation/test_taste_eval.py`

Tests [`src/evaluation/taste_eval.py`](../../evaluation/taste_eval.md).

## What it checks

| Test | Guarantees |
| --- | --- |
| `test_auc_is_one_for_a_perfect_ranking_zero_for_a_reversed_one_and_half_for_no_information` | the AUC definition, including ties |
| `test_known_history_is_not_a_negative` | excluded (history) recipes do not count against a positive |
| `test_recall_counts_positives_inside_the_top_share` | recall at the top 1 % |
| `test_rank_metrics_refuse_empty_inputs` | no positives or no negatives raise |
| `test_negatives_are_distinct_never_positive_or_known_and_reproducible` | 99 distinct negatives per positive, never a positive or a history recipe, reproducible from the seed; too few candidates raise |
| `test_hit_rate_and_ndcg_for_best_worst_and_uninformative_scores` | perfect = 1, reversed = 0, constant = chance (HR@10 ≈ 0.10) thanks to random tie-breaking |
| `test_runs_are_reproducible` | two runs give identical rows |
| `test_run_on_the_frozen_validation_users` | when built: every method for every user, values in range, the same held-out set across methods, the paired table and the printed report |

## Change log

- 2026-10-16 — Created.
- 2026-10-16 — Added the sampled-metric tests and the reproducibility test. The frozen-set test covers every method and metric and the random row.
- 2026-10-16 — The frozen-set test now also covers the `scorer_with_history` method.
