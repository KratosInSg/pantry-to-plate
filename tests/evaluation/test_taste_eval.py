"""Tests for ``evaluation/taste_eval.py``: the ranking metrics on hand-made scores, and the run on the frozen set."""
from __future__ import annotations

import numpy as np
import pytest

from evaluation.taste_eval import (METHODS, METRICS, N_NEGATIVES, compare, rank_metrics, report, run_taste_eval,
                                   sample_negatives, sampled_metrics, summary)
from evaluation.taste_users import DEFAULT_TASTE_DIR


# ------------------------------------------------------------------------------------------------ full ranking
def test_auc_is_one_for_a_perfect_ranking_zero_for_a_reversed_one_and_half_for_no_information():
    scores = np.arange(100, dtype=float)
    assert rank_metrics(scores, {99, 98})[0] == pytest.approx(1.0)
    assert rank_metrics(-scores, {99, 98})[0] == pytest.approx(0.0)
    assert rank_metrics(np.zeros(100), {5, 6})[0] == pytest.approx(0.5)


def test_known_history_is_not_a_negative():
    scores = np.arange(10, dtype=float)
    # positive 5 sits above 0..4 and below 6..9; excluding 6..9 (the user's history) leaves only weaker negatives
    assert rank_metrics(scores, {5})[0] == pytest.approx(5 / 9)
    assert rank_metrics(scores, {5}, exclude={6, 7, 8, 9})[0] == pytest.approx(1.0)


def test_recall_counts_positives_inside_the_top_share():
    scores = np.arange(1000, dtype=float)
    assert rank_metrics(scores, {999, 998, 0}, top_share=0.01)[1] == pytest.approx(2 / 3)


def test_rank_metrics_refuse_empty_inputs():
    with pytest.raises(ValueError, match="positives"):
        rank_metrics(np.zeros(5), set())
    with pytest.raises(ValueError, match="negatives"):
        rank_metrics(np.zeros(2), {0}, exclude={1})


# ------------------------------------------------------------------------------------------------ sampled (paper protocol)
def test_negatives_are_distinct_never_positive_or_known_and_reproducible():
    positives, exclude = {3, 7}, set(range(10, 20))
    a = sample_negatives(500, positives, exclude, np.random.default_rng(1))
    b = sample_negatives(500, positives, exclude, np.random.default_rng(1))
    assert set(a) == positives
    for p in positives:
        assert len(a[p]) == N_NEGATIVES == len(set(a[p].tolist()))
        assert not set(a[p].tolist()) & (positives | exclude)
        assert np.array_equal(a[p], b[p])
    with pytest.raises(ValueError, match="candidate negatives"):
        sample_negatives(50, {1}, set(), np.random.default_rng(1))


def test_hit_rate_and_ndcg_for_best_worst_and_uninformative_scores():
    n = 2000
    positives = set(range(0, 2000, 20))                              # 100 positives
    negatives = sample_negatives(n, positives, set(), np.random.default_rng(2))
    best = np.zeros(n)
    best[list(positives)] = 1.0
    perfect = sampled_metrics(best, negatives, np.random.default_rng(3))
    assert perfect == {"hr_5": 1.0, "hr_10": 1.0, "ndcg_5": 1.0, "ndcg_10": 1.0}
    assert sampled_metrics(-best, negatives, np.random.default_rng(3))["hr_10"] == 0.0
    # a constant score carries no information: random tie-breaking gives chance (10 of 100) in expectation
    flat = sampled_metrics(np.zeros(n), negatives, np.random.default_rng(4))
    assert flat["hr_10"] == pytest.approx(0.10, abs=0.06) and flat["hr_5"] == pytest.approx(0.05, abs=0.05)


# ------------------------------------------------------------------------------------------------ frozen set
@pytest.mark.skipif(not (DEFAULT_TASTE_DIR / "FROZEN.json").exists(), reason="frozen taste set not built here")
def test_run_on_the_frozen_validation_users(ctx, capsys):
    df = run_taste_eval("validation", ctx=ctx, limit=3)
    assert list(dict.fromkeys(df.method)) == list(METHODS) and df.user_id.nunique() == 3
    for metric in METRICS:
        assert df[metric].between(0, 1).all(), metric
    assert (df.groupby("user_id").n_heldout.nunique() == 1).all()       # same held-out set under every method
    table = summary(df)
    assert table.loc["random", "hr_10_x_random"] == pytest.approx(1.0)
    assert list(compare(df).index) == [m for m in METHODS if m != "popularity"]
    report(df)
    assert "paired difference" in capsys.readouterr().out


@pytest.mark.skipif(not (DEFAULT_TASTE_DIR / "FROZEN.json").exists(), reason="frozen taste set not built here")
def test_runs_are_reproducible(ctx):
    a = run_taste_eval("validation", ctx=ctx, limit=2, methods=("random", "nearest_dishes"))
    b = run_taste_eval("validation", ctx=ctx, limit=2, methods=("random", "nearest_dishes"))
    assert a.equals(b)
