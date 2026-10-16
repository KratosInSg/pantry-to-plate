# `tests/preference/test_scorer.py`

Tests [`preference/scorer.py`](../../preference/scorer.md) against the real catalogue.

| Test | Pins |
| --- | --- |
| `test_scores_are_in_unit_interval_and_float32` | range and dtype |
| `test_neutral_user_only_sees_the_small_popularity_term` | with no stated preferences scores stay within 0.5 ± W_POPULAR |
| `test_unrated_recipes_are_neutral` | unrated → exactly 0.5 popularity |
| `test_disliked_ingredient_lowers_the_score_but_does_not_remove_the_recipe` | −0.35 on affected recipes only; still > 0 (eligible) |
| `test_liked_ingredient_raises_the_score_with_saturation` | one hit = half the liked bonus |
| `test_staples_can_be_ignored_for_likes` | `ignore_for_likes` cancels the effect |
| `test_cuisine_preferences_shift_scores` | liked ≥ baseline ≥ disliked within the cuisine; others unchanged |
| `test_disliked_mask_matches_dislikes` | the evaluation's mask equals the inverted-index hits |

Expected numbers are derived from `DEFAULT_WEIGHTS`, not hard-coded, so retuning weights does not break the tests for
the wrong reason.

## Change log

- 2026-10-12 — Created.
- 2026-10-16 — Added the rating-history tests: unchanged without history, loved-like dinners rise and far ones fall, one liked dinner only nudges, low ratings and unknown dinners change nothing.
