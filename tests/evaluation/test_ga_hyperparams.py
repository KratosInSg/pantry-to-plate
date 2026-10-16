"""Regression checks for GA hyperparameter sweep on frozen validation data."""
import pytest
from evaluation.ga_hyperparams import experiment


def test_hyperparameter_sweep_distinguishes_configs(ctx):
    raw, by_seed, summary = experiment(
        limit=8, seeds=1, generations=2, mutations=(0.1, 0.35),
        populations=(8,), ctx=ctx,
    )
    assert set(raw["mutation_rate"]) == {0.1, 0.35}
    assert len(raw) == 16  # one per scenario for each of two configs
    assert len(by_seed) == 2
    assert len(summary) == 2
    assert (raw["violations"] == 0).all()
    assert (raw["complete"] == 1).all()
    assert (raw["runtime_s"] >= 0).all()


def test_hyperparameter_sweep_rejects_invalid_inputs(ctx):
    with pytest.raises(ValueError):
        experiment(limit=0, ctx=ctx)
    with pytest.raises(ValueError):
        experiment(limit=8, seeds=0, ctx=ctx)
    with pytest.raises(ValueError):
        experiment(limit=8, seeds=1, generations=1,
                   mutations=(-0.1,), populations=(8,), ctx=ctx)
